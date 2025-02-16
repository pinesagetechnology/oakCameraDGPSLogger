import tkinter as tk
from datetime import datetime
import time
import threading
from typing import Dict, Any

from ui_manager import UIManager
from camera_manager import CameraManager
from gps_manager import GPSManager
from storage_manager import StorageManager

class MainApplication:
    def __init__(self):
        self.root = tk.Tk()
        self.ui = UIManager(self.root)
        self.camera = CameraManager()
        self.interval_type = "time"
        self.interval_value = 30
        self.distance_moved = 0
        # Initialize GPS since it's enabled by default
        try:
            self.gps = GPSManager()
        except Exception as e:
            print(f"Failed to initialize GPS: {str(e)}")
            self.gps = None
            self.ui.set_gps_enabled(False)  # Disable GPS button
            
        self.storage = StorageManager()
        self.last_gps_coords = None
        self.gps_threshold = 0.0001  # About 11 meters threshold
        self.is_moving = False
        
        # Set up callbacks
        self.ui.set_callbacks(
            start_callback=self.start_system,
            stop_callback=self.stop_system,
            mask_callback=self.update_mask,
            directory_callback=self.update_directory,
            device_select_callback=self.select_device,
            refresh_devices_callback=self.refresh_devices,
            gps_toggle_callback=self.toggle_gps
        )
        
        # State variables
        self.running = False
        self.last_save_time = 0
        self.save_interval = 30
        self.save_thread = None
        self.selected_device = None
        
        # Bind manual capture key
        self.root.bind('c', self.manual_capture)
        self.root.bind('C', self.manual_capture)
        
        # Initial device refresh
        self.refresh_devices()
        
    def toggle_gps(self, enabled: bool):
        """Handle GPS toggle"""
        if enabled:
            if self.gps is None:
                self.gps = GPSManager()
                if self.running:  # If camera is already running, start GPS too
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
        """Refresh available devices list"""
        devices = self.camera.find_devices()
        return devices
        
    def select_device(self, device_info):
        """Handle device selection"""
        self.selected_device = device_info
        device_details = self.camera.get_device_info(device_info)
        self.ui.update_device_info(device_details)
        
    def start_system(self, interval_settings: dict):
        """Start camera and GPS systems"""
        if not self.selected_device:
            raise ValueError("Please select a device first")
            
        try:
            # Update interval settings
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
            self.save_thread = threading.Thread(target=self._save_loop)
            self.save_thread.daemon = True
            self.save_thread.start()
            
        except Exception as e:
            self.stop_system()
            raise Exception(f"Failed to start system: {str(e)}")
            
    def stop_system(self):
        """Stop camera and GPS systems"""
        self.running = False
        if self.save_thread:
            self.save_thread.join(timeout=1.0)
        self.camera.stop_camera()
        if self.gps is not None:
            self.gps.stop_gps()
        
    def update_mask(self, coords: tuple):
        """Update camera mask"""
        self.camera.set_mask(coords)
        
    def update_directory(self, path: str):
        """Update storage directory"""
        self.storage.set_base_path(path)
        
    def manual_capture(self, event=None):
        """Handle manual capture when 'C' key is pressed"""
        if self.running:
            try:
                # Get current frames from camera
                frames = {
                    'rgb': self.camera.q_rgb.get().getCvFrame(),
                    'depth': self.camera.q_depth.get().getCvFrame(),
                    'ir': self.camera.q_left.get().getCvFrame()
                }
                
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
        """Check if the vehicle is moving based on GPS coordinates"""
        if not self.last_gps_coords or not current_coords:
            self.last_gps_coords = current_coords
            return True  # Assume moving if no previous coordinates
            
        try:
            # Calculate distance between current and last coordinates
            lat_diff = abs(float(current_coords['latitude']) - float(self.last_gps_coords['latitude']))
            lon_diff = abs(float(current_coords['longitude']) - float(self.last_gps_coords['longitude']))
            
            # Check if movement exceeds threshold
            is_moving = lat_diff > self.gps_threshold or lon_diff > self.gps_threshold
            
            # Update last coordinates if moving
            if is_moving:
                self.last_gps_coords = current_coords
            
            # Update UI with motion status
            self.ui.update_motion_status(is_moving)
            
            return is_moving
            
        except (KeyError, ValueError) as e:
            print(f"Error checking motion: {str(e)}")
            return True  # Assume moving if error occurs
            
    def _save_loop(self):
        """Loop for saving frames and GPS data"""
        while self.running:
            try:
                current_time = time.time()
                should_capture = False
                
                # Get GPS coordinates if available
                coords = None
                if self.gps is not None:
                    if self.interval_type == "distance":
                        distance_moved, coords = self.gps.get_distance_moved()
                        if distance_moved >= self.interval_value:
                            should_capture = True
                            # Reset last position after capture
                            self.gps.last_position = coords
                    else:  # time-based interval
                        coords = self.gps.get_current_location()
                        if current_time - self.last_save_time >= self.interval_value:
                            should_capture = True
                
                # Check if vehicle is moving
                if coords and not self.check_motion(coords):
                    time.sleep(0.1)
                    continue
                
                # Capture if conditions are met
                if should_capture:
                    # Get current frames from camera
                    frames = {
                        'rgb': self.camera.q_rgb.get().getCvFrame(),
                        'depth': self.camera.q_depth.get().getCvFrame(),
                        'ir': self.camera.q_left.get().getCvFrame()
                    }
                    
                    # Save frames
                    timestamp = datetime.now()
                    self.storage.save_frames_with_metadata(
                        frames=frames,
                        metadata=coords if coords else {"gps": "disabled"},
                        timestamp=timestamp,
                        capture_type="auto"
                    )
                    self.last_save_time = current_time
                    
            except Exception as e:
                print(f"Error in save loop: {str(e)}")
                
            time.sleep(0.1)  # Prevent busy waiting
            
    def run(self):
        """Start the application"""
        self.root.protocol("WM_DELETE_WINDOW", self.ui._exit_application)
        self.root.mainloop()

def main():
    app = MainApplication()
    app.run()

if __name__ == "__main__":
    main()