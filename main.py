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
        self.gps = None  # Initialize GPS as None
        self.storage = StorageManager()
        
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
        
    def start_system(self, interval: int):
        """Start camera and GPS systems"""
        if not self.selected_device:
            raise ValueError("Please select a device first")
            
        try:
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
            
            # Set up saving
            self.save_interval = interval
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
        
    def _save_loop(self):
        """Loop for saving frames and GPS data"""
        while self.running:
            current_time = time.time()
            
            if current_time - self.last_save_time >= self.save_interval:
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
                        timestamp=timestamp
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