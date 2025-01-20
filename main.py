import tkinter as tk
from datetime import datetime
import time
import threading
from typing import Dict, Any

from ui_manager import UIManager
from camera_manager import CameraManager
# from gps_manager import GPSManager
from ublox_gps_manager import UbloxGPSManager
from storage_manager import StorageManager

class MainApplication:
    def __init__(self):
        self.root = tk.Tk()
        self.ui = UIManager(self.root)
        self.camera = CameraManager()
        # self.gps = GPSManager()
        self.gps = UbloxGPSManager()
        self.storage = StorageManager()
        
        # Set up callbacks
        self.ui.set_callbacks(
            start_callback=self.start_system,
            stop_callback=self.stop_system,
            mask_callback=self.update_mask,
            directory_callback=self.update_directory
        )
        
        # State variables
        self.running = False
        self.last_save_time = 0
        self.save_interval = 30
        self.save_thread = None
        
    def start_system(self, interval: int):
        """Start camera and GPS systems"""
        try:
            # Start GPS
            self.gps.start_gps(callback=self.ui.update_gps_status)
            
            # Start camera
            self.camera.start_camera(frame_callback=self.ui.update_frames)
            
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
                    
                    # Get GPS coordinates
                    coords = self.gps.get_current_location()
                    
                    # Save everything
                    if frames and coords:
                        timestamp = datetime.now()
                        self.storage.save_frames_with_metadata(
                            frames=frames,
                            metadata=coords,
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