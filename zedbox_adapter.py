import os
import sys
import importlib.util
import tkinter as tk
from tkinter import ttk, messagebox

def check_dependencies():
    """Check if required packages are installed."""
    missing_packages = []
    
    # Try importing required packages
    packages = {
        "pyzed": "stereolabs-zed",
        "pyubx2": "pyubx2",
        "serial": "pyserial"
    }
    
    for package, pip_name in packages.items():
        try:
            importlib.import_module(package)
        except ImportError:
            missing_packages.append(f"{pip_name}")
    
    if missing_packages:
        # Create a simple Tkinter window to show the error
        root = tk.Tk()
        root.withdraw()
        
        # Build the message
        message = "Missing required packages. Please install them using pip:\n\n"
        message += "pip install " + " ".join(missing_packages)
        message += "\n\nWould you like to install them now?"

        # Show dialog and ask if user wants to install packages
        if messagebox.askyesno("Missing Dependencies", message):
            try:
                import subprocess
                for package in missing_packages:
                    print(f"Installing {package}...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                messagebox.showinfo("Success", "Packages installed successfully. Please restart the application.")
            except Exception as e:
                messagebox.showerror("Installation Failed", f"Failed to install packages: {str(e)}")
        
        sys.exit(1)

def load_managers():
    """Import and provide ZED camera and U-BLOX GPS managers."""
    # Check if we can import required modules
    try:
        from zed_camera_manager import ZEDCameraManager
        from ublox_gps_manager import UBloxGPSManager
        
        return ZEDCameraManager, UBloxGPSManager
    except ImportError as e:
        # Create simple Tkinter window to show the error
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Import Error", 
                            f"Failed to import managers: {str(e)}\n\n"
                            "Make sure zed_camera_manager.py and ublox_gps_manager.py "
                            "are in the same directory as this script.")
        sys.exit(1)

def adapt_zed_to_main_app():
    """
    Adapt the ZED camera manager to be used in the main application.
    This function replaces the original OAK-D camera manager with the ZED camera manager.
    """
    # Import the main application
    try:
        # Make sure dependencies are installed
        check_dependencies()
        
        # Load our custom managers
        ZEDCameraManager, UBloxGPSManager = load_managers()
        
        # Try to import MainApplication
        try:
            from main import MainApplication
            print("Successfully imported MainApplication")
        except ImportError:
            # Check if main.py exists
            if not os.path.exists('main.py'):
                raise ImportError("main.py not found in the current directory")
            raise
        
        # Create a class that extends MainApplication and overrides necessary methods
        class ZEDBoxApplication(MainApplication):
            """
            Extended application class that uses ZED camera and U-BLOX GPS
            instead of the original OAK-D camera and standard GPS.
            """
            def __init__(self):
                # Initialize parent class first (this will set up the Tk root and UI)
                super().__init__()
                
                # Replace the OAK-D camera manager with the ZED camera manager
                self.camera = ZEDCameraManager()
                
                # Replace the GPS manager with the U-BLOX GPS manager
                try:
                    # Store the enabled state
                    gps_enabled = True
                    if hasattr(self, 'gps') and self.gps is not None:
                        gps_enabled = self.ui.gps_enabled.get()
                        self.gps.stop_gps()  # Stop the existing GPS manager
                    
                    # Create new U-BLOX GPS manager
                    self.gps = UBloxGPSManager()
                    self.ui.set_gps_enabled(gps_enabled)
                except Exception as e:
                    print(f"Failed to initialize U-BLOX GPS: {str(e)}")
                    self.gps = None
                    self.ui.set_gps_enabled(False)
                
                # Refresh devices to show available ZED cameras
                self.refresh_devices()
                
            def toggle_gps(self, enabled: bool):
                """ Handle GPS toggle - override to use U-BLOX GPS """
                if enabled:
                    if self.gps is None:
                        self.gps = UBloxGPSManager()
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
                """Refresh available ZED devices list."""
                devices = self.camera.find_devices()
                return devices
                
            def start_system(self, interval_settings: dict):
                """Start camera and (optionally) GPS systems with ZED camera."""
                if not self.selected_device:
                    raise ValueError("Please select a device first")

                try:
                    self.interval_type = interval_settings['type']
                    self.interval_value = interval_settings['value']

                    # Start GPS if enabled - use U-BLOX specific method
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
                    import threading
                    import time
                    self.save_thread = threading.Thread(target=self._save_loop)
                    self.save_thread.daemon = True
                    self.save_thread.start()

                except Exception as e:
                    self.stop_system()
                    raise Exception(f"Failed to start system: {str(e)}")
                    
            def check_motion(self, current_coords):
                """
                Check if the vehicle is moving based on GPS coordinates.
                Modified to handle U-BLOX GPS format.
                """
                if not self.last_gps_coords or not current_coords:
                    self.last_gps_coords = current_coords
                    return True  # Assume moving if no previous coords

                try:
                    # Access latitude and longitude based on U-BLOX format
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
                    
        # Create a main function to run the ZED Box application
        def main():
            app = ZEDBoxApplication()
            app.run()
            
        # Return the main function so it can be called
        return main
    
    except Exception as e:
        import tkinter as tk
        from tkinter import messagebox
        
        # Show error in a nice dialog
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("ZED Box Adapter Error", 
                            f"Error initializing ZED Box adapter: {str(e)}\n\n"
                            "Please check that all required files are in the correct locations.")
        
        # Re-raise for console output
        raise
        
if __name__ == "__main__":
    # Run the adapter
    try:
        zed_main = adapt_zed_to_main_app()
        zed_main()
    except Exception as e:
        print(f"Failed to run ZED Box application: {str(e)}")
        import traceback
        traceback.print_exc()