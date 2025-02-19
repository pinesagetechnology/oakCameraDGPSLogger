import tkinter as tk
from datetime import datetime
import time
import threading
from typing import Dict, Any
from ui_manager import UIManager
from camera_manager import CameraManager
from gps_manager import GPSManager
from storage_manager import StorageManager
import cv2
import numpy as np
import os

class MainApplication:
    def __init__(self):
        self.root = tk.Tk()
        self.ui = UIManager(self.root)
        self.camera = CameraManager()

        self.interval_type = "time"
        self.interval_value = 30
        self.distance_moved = 0

        self.recording_state = {
            'active': False,
            'type': None,  # 'interval' or 'continuous'
            'video': False
        }

        # Initialize GPS
        try:
            self.gps = GPSManager()
        except Exception as e:
            print(f"Failed to initialize GPS: {str(e)}")
            self.gps = None
            self.ui.set_gps_enabled(False)

        self.storage = StorageManager()
        self.last_gps_coords = None
        self.gps_threshold = 0.0001  # ~11 meters threshold
        self.is_moving = False

        # Initialize video path
        video_path = os.path.join(self.storage.get_base_path(), 'videos')
        if not os.path.exists(video_path):
            os.makedirs(video_path)
        self.ui.video_dir_var.set(video_path)

        # Set up UI callbacks
        self.ui.set_callbacks(
            start_callback=self.start_system,
            stop_callback=self.stop_system,
            mask_callback=self.update_mask,
            directory_callback=self.update_directory,
            device_select_callback=self.select_device,
            refresh_devices_callback=self.refresh_devices,
            gps_toggle_callback=self.toggle_gps,
            video_callback=self.toggle_recording
        )

        self.running = False
        self.last_save_time = 0
        self.save_thread = None
        self.selected_device = None

        # Bind manual capture key
        self.root.bind('c', self.manual_capture)
        self.root.bind('C', self.manual_capture)

        # Initial device refresh
        self.refresh_devices()

    def toggle_gps(self, enabled: bool):
        """ Handle GPS toggle """
        if enabled:
            if self.gps is None:
                self.gps = GPSManager()
                if self.running:
                    try:
                        self.gps.start_gps(callback=self.ui.update_gps_status)
                    except Exception as e:
                        self.ui.show_error("GPS Error", f"Failed to start GPS: {str(e)}")
                        self.gps = None
                        self.ui.set_gps_enabled(False)
        else:
            if self.gps is not None:
                self.gps.stop_gps()
                self.gps = None
                self.ui.update_gps_status(None)

    def refresh_devices(self):
        """Refresh available devices list (PoE only)."""
        devices = self.camera.find_devices()
        return devices

    def select_device(self, device_info):
        """Handle device selection from UI."""
        self.selected_device = device_info
        device_details = self.camera.get_device_info(device_info)
        self.ui.update_device_info(device_details)

    def start_system(self, interval_settings: dict):
        """Start camera and (optionally) GPS systems."""
        if not self.selected_device:
            raise ValueError("Please select a device first")

        try:
            self.interval_type = interval_settings['type']
            self.interval_value = interval_settings['value']

            # Start GPS if enabled
            if self.gps is not None:
                try:
                    self.gps.start_gps(callback=self.ui.update_gps_status)
                except Exception as e:
                    self.ui.show_error("GPS Error", f"Failed to start GPS: {str(e)}")
                    self.gps = None
                    self.ui.set_gps_enabled(False)

            # Start camera with selected device
            self.camera.start_camera(
                device_info=self.selected_device,
                frame_callback=self.ui.update_frames,
                device_info_callback=self.ui.update_device_info
            )

            self.running = True
            self.last_save_time = time.time()

            # Start the background thread that periodically saves frames
            self.save_thread = threading.Thread(target=self._save_loop)
            self.save_thread.daemon = True
            self.save_thread.start()

        except Exception as e:
            self.stop_system()
            raise Exception(f"Failed to start system: {str(e)}")

    def stop_system(self):
        """Stop camera and GPS systems."""
        # Stop recording if active
        if self.recording_state['active']:
            self.toggle_recording(self.recording_state['type'], False)
            
        self.running = False
        if self.save_thread:
            self.save_thread.join(timeout=1.0)

        self.camera.stop_camera()
        self.ui.control_btn.config(text="Start Camera")  # Update button text

        if self.gps is not None:
            self.gps.stop_gps()

    def update_mask(self, coords: tuple):
        """Update camera mask (applied in camera_manager)."""
        self.camera.set_mask(coords)

    def update_directory(self, path: str):
        """Update storage directory"""
        self.storage.set_base_path(path)
        # Update video path as well
        video_path = os.path.join(path, 'videos')
        if not os.path.exists(video_path):
            os.makedirs(video_path)
        self.storage.set_video_path(video_path)
        self.ui.video_dir_var.set(video_path)


    def manual_capture(self, event=None):
        """Handle manual capture when 'C' key is pressed."""
        if self.running:
            try:
                # Get current frames from camera queues
                # Use blocking get() to retrieve the most recent frames
                frames = {}
                if self.camera.latest_rgb_video is not None: 
                    frames['rgb'] = self.camera.latest_rgb_video 
                else: 
                    print("Warning: No high-res RGB frame available for capture.")

                if self.camera.q_depth:
                    depth_data = self.camera.q_depth.get()
                    depth_raw = depth_data.getFrame()  # 16-bit
                    depth_8 = cv2.normalize(depth_raw, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
                    frames['depth'] = cv2.applyColorMap(depth_8, cv2.COLORMAP_JET)
                    # Save raw as well if needed
                    frames['depth_raw'] = depth_raw
                if self.camera.q_left:
                    ir_data = self.camera.q_left.get().getCvFrame()
                    ir_data = cv2.normalize(ir_data, None, 0, 255, cv2.NORM_MINMAX)
                    ir_data = cv2.equalizeHist(ir_data)
                    frames['ir'] = ir_data

                # Get GPS coordinates if available
                coords = None
                if self.gps is not None:
                    coords = self.gps.get_current_location()

                # Save frames
                timestamp = datetime.now()
                self.storage.save_frames_with_metadata(
                    frames=frames,
                    metadata=coords if coords else {"gps": "disabled"},
                    timestamp=timestamp,
                    capture_type="manual"
                )

                # Update UI to show capture confirmation
                self.ui.show_capture_notification("Manual capture successful")

            except Exception as e:
                print(f"Error in manual capture: {str(e)}")

    def check_motion(self, current_coords):
        """Check if the vehicle is moving based on GPS coordinates."""
        if not self.last_gps_coords or not current_coords:
            self.last_gps_coords = current_coords
            return True  # Assume moving if no previous coords

        try:
            lat_diff = abs(float(current_coords['latitude']) - float(self.last_gps_coords['latitude']))
            lon_diff = abs(float(current_coords['longitude']) - float(self.last_gps_coords['longitude']))

            is_moving = lat_diff > self.gps_threshold or lon_diff > self.gps_threshold

            if is_moving:
                self.last_gps_coords = current_coords

            self.ui.update_motion_status(is_moving)
            return is_moving

        except (KeyError, ValueError) as e:
            print(f"Error checking motion: {str(e)}")
            return True  # default to True if error

    def _save_loop(self):
        """
        Background thread that saves frames at either time intervals or distance intervals.
        """
        while self.running:
            try:
                current_time = time.time()
                should_capture = False
                coords = None

                if self.gps is not None:
                    if self.interval_type == "distance":
                        distance_moved, coords = self.gps.get_distance_moved()
                        should_capture = distance_moved >= self.interval_value
                        if should_capture:
                            self.gps.last_position = coords
                    else:
                        coords = self.gps.get_current_location()
                        should_capture = (current_time - self.last_save_time) >= self.interval_value
                else:
                    # If no GPS, only do time-based
                    should_capture = self.interval_type == "time" and (current_time - self.last_save_time) >= self.interval_value

                # Check motion status if we have GPS coordinates
                if coords and not self.check_motion(coords):
                    time.sleep(0.1)
                    continue

                if should_capture:
                    frames = {}
                    save_success = False

                    # Try to get each frame type
                    try:
                        if self.camera.latest_rgb_video is not None: 
                            frames['rgb'] = self.camera.latest_rgb_video 
                        else: 
                            print("Warning: No high-res RGB frame available for capture.")
                    except Exception as e:
                        print(f"Error capturing RGB frame: {str(e)}")

                    try:
                        if self.camera.q_depth:
                            depth_data = self.camera.q_depth.get()
                            depth_raw = depth_data.getFrame()  # 16-bit
                            depth_8 = cv2.normalize(depth_raw, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
                            frames['depth'] = cv2.applyColorMap(depth_8, cv2.COLORMAP_JET)
                            # Save raw as well if needed
                            frames['depth_raw'] = depth_raw
                    except Exception as e:
                        print(f"Error capturing depth frame: {str(e)}")

                    try:
                        if self.camera.q_left:
                            ir_data = self.camera.q_left.get().getCvFrame()
                            ir_data = cv2.normalize(ir_data, None, 0, 255, cv2.NORM_MINMAX)
                            ir_data = cv2.equalizeHist(ir_data)
                            frames['ir'] = ir_data
                    except Exception as e:
                        print(f"Error capturing IR frame: {str(e)}")

                    # Only save if we have at least one frame
                    if frames:
                        try:
                            saved_files = self.storage.save_frames_with_metadata(
                                frames=frames,
                                metadata=coords if coords else {"gps": "disabled"},
                                timestamp=datetime.now(),
                                capture_type="auto"
                            )
                            save_success = True
                            print(f"Saved frames: {', '.join([os.path.basename(f) for f in saved_files])}")
                        except Exception as e:
                            print(f"Error saving frames: {str(e)}")

                    if save_success:
                        self.last_save_time = current_time

                time.sleep(0.1)

            except Exception as e:
                print(f"Error in save loop: {str(e)}")
                time.sleep(0.1)

    def toggle_recording(self, record_type='interval', include_video=False):
        """
        Toggle recording state
        :param record_type: 'interval' or 'continuous'
        :param include_video: whether to record video
        """
        if not self.recording_state['active']:
            # Start recording
            try:
                if include_video:
                    video_path = self.ui.video_dir_var.get()
                    if not os.path.exists(video_path):
                        os.makedirs(video_path)
                    self.camera.video_writers = self.storage.start_video_recording(video_path)
                
                self.recording_state = {
                    'active': True,
                    'type': record_type,
                    'video': include_video
                }
                
                self.last_save_time = time.time()
                self.ui.show_capture_notification(
                    f"Started {'video ' if include_video else ''}recording ({record_type})"
                )
                                
            except Exception as e:
                self.ui.show_error("Recording Error", f"Failed to start recording: {str(e)}")
                self.recording_state['active'] = False
                
        else:
            # Stop recording
            if self.recording_state['video']:
                if self.camera.video_writers:
                    self.storage.stop_video_recording(self.camera.video_writers)
                    self.camera.video_writers = None
                    
            self.recording_state = {
                'active': False,
                'type': None,
                'video': False
            }
            self.ui.show_capture_notification("Stopped recording")

    def run(self):
        """Start the Tkinter main loop."""
        self.root.protocol("WM_DELETE_WINDOW", self.ui._exit_application)
        self.root.mainloop()


def main():
    app = MainApplication()
    app.run()


if __name__ == "__main__":
    main()
