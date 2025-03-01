import pyzed.sl as sl
import cv2
import numpy as np
import threading
import time
from typing import Optional, Tuple, Callable, List, Dict
from datetime import datetime


class ZEDCameraManager:
    def __init__(self):
        self.running = False
        self.camera = None
        self.camera_thread = None
        self.frame_callback = None
        self.mask_coords = [0, 0, 0, 0]
        self.available_devices = []
        self.current_device_info = None
        self.device_info_callback = None
        self.video_writers = None
        
        # ZED specific parameters
        self.init_params = None
        self.runtime_params = None
        
        # Latest frames
        self.latest_rgb_video = None
        self.latest_depth = None
        self.latest_left = None
        self.latest_right = None
        
        # Camera resolution
        self.camera_resolution = sl.RESOLUTION.HD720  # Default resolution
        self.camera_fps = 30  # Default FPS
        
    def find_devices(self) -> List[sl.DeviceProperties]:
        """
        Find all available ZED cameras.
        """
        self.available_devices = []
        try:
            device_list = sl.Camera.get_device_list()
            for device in device_list:
                self.available_devices.append(device)
                print(f"Found ZED device: {device.serial_number} - {device.camera_model}")
        except Exception as e:
            print(f"Error finding ZED devices: {e}")

        return self.available_devices

    def get_device_info(self, device_info: sl.DeviceProperties) -> Dict:
        """
        Get detailed information about a device.
        """
        try:
            return {
                'name': f"ZED {sl.get_camera_model(device_info.camera_model)}",
                'serial': str(device_info.serial_number),
                'model': str(device_info.camera_model),
                'state': "Available"
            }
        except Exception as e:
            print(f"Error getting device info: {str(e)}")
            return {}
            
    def create_camera_parameters(self) -> None:
        """
        Create and configure the ZED camera parameters.
        """
        # Initialize camera parameters
        self.init_params = sl.InitParameters()
        self.init_params.camera_resolution = self.camera_resolution
        self.init_params.camera_fps = self.camera_fps
        self.init_params.depth_mode = sl.DEPTH_MODE.ULTRA  # Use ULTRA for best quality
        self.init_params.coordinate_units = sl.UNIT.METER  # Set units in meters
        self.init_params.depth_minimum_distance = 0.3  # Minimum depth in meters
        self.init_params.depth_maximum_distance = 20.0  # Maximum depth in meters
        self.init_params.coordinate_system = sl.COORDINATE_SYSTEM.RIGHT_HANDED_Y_UP
        self.init_params.depth_stabilization = True
        
        # Runtime parameters for depth sensing
        self.runtime_params = sl.RuntimeParameters()
        self.runtime_params.sensing_mode = sl.SENSING_MODE.STANDARD
        self.runtime_params.enable_depth = True
        self.runtime_params.enable_point_cloud = True
        
    def start_camera(
        self,
        device_info: Optional[sl.DeviceProperties] = None,
        frame_callback: Callable = None,
        device_info_callback: Callable = None
    ) -> bool:
        """
        Start the ZED camera, initialize parameters.
        """
        if self.running:
            print("Camera already running.")
            return False
            
        try:
            self.create_camera_parameters()
            
            # Initialize ZED camera
            self.camera = sl.Camera()
            
            # If a specific device was selected, set its serial number
            if device_info:
                self.init_params.set_from_serial_number(device_info.serial_number)
                
            # Open the camera
            status = self.camera.open(self.init_params)
            if status != sl.ERROR_CODE.SUCCESS:
                raise Exception(f"Failed to open camera: {status}")
                
            # Enable positional tracking if needed
            # tracking_params = sl.PositionalTrackingParameters()
            # status = self.camera.enable_positional_tracking(tracking_params)
            # if status != sl.ERROR_CODE.SUCCESS:
            #     print(f"Warning: Positional tracking could not be enabled: {status}")
                
            # Store camera info for UI
            camera_info = self.camera.get_camera_information()
            self.current_device_info = {
                'name': f"ZED {camera_info.camera_model}",
                'serial': str(camera_info.serial_number),
                'model': str(camera_info.camera_model),
                'firmware': str(camera_info.firmware_version),
                'resolution': f"{camera_info.camera_resolution.width}x{camera_info.camera_resolution.height}"
            }
            
            if device_info_callback:
                device_info_callback(self.current_device_info)
                
            # Create image containers
            self.image_size = self.camera.get_camera_information().camera_configuration.resolution
            self.width = self.image_size.width
            self.height = self.image_size.height

            # Mark as running and start thread
            self.running = True
            self.frame_callback = frame_callback
            self.camera_thread = threading.Thread(target=self._update_camera)
            self.camera_thread.daemon = True
            self.camera_thread.start()
            
            return True
            
        except Exception as e:
            print(f"Failed to start camera: {str(e)}")
            return False
            
    def _update_camera(self):
        """
        Continuously grab frames from the ZED camera and pass them to the callback.
        """
        # Create ZED image objects
        left_image = sl.Mat()
        right_image = sl.Mat()
        depth_image = sl.Mat()
        point_cloud = sl.Mat()
        
        last_write_time = time.time()
        frame_interval = 1.0 / 15  # For 15 FPS output
        
        while self.running:
            try:
                current_time = time.time()
                if current_time - last_write_time < frame_interval:
                    time.sleep(0.001)
                    continue
                    
                # Grab a new frame from the ZED
                if self.camera.grab(self.runtime_params) == sl.ERROR_CODE.SUCCESS:
                    # Retrieve left image
                    self.camera.retrieve_image(left_image, sl.VIEW.LEFT)
                    left_np = left_image.get_data()
                    left_np = self.apply_mask(left_np)
                    self.latest_left = left_np.copy()
                    
                    # Retrieve right image (if needed)
                    self.camera.retrieve_image(right_image, sl.VIEW.RIGHT) 
                    right_np = right_image.get_data()
                    self.latest_right = right_np.copy()
                    
                    # Retrieve depth map
                    self.camera.retrieve_image(depth_image, sl.VIEW.DEPTH)
                    depth_np = depth_image.get_data()
                    depth_np = self.apply_mask(depth_np)
                    
                    # Create a more visually pleasing colorized depth map
                    normalized_depth = cv2.normalize(depth_np, None, 0, 255, cv2.NORM_MINMAX)
                    colorized_depth = cv2.applyColorMap(normalized_depth.astype(np.uint8), cv2.COLORMAP_JET)
                    self.latest_depth = colorized_depth.copy()
                    
                    # Retrieve point cloud for 3D data (if needed)
                    self.camera.retrieve_measure(point_cloud, sl.MEASURE.XYZRGBA)
                    
                    # Create a frames dictionary for the callback
                    frames = {
                        'rgb': left_np,  # Use left image as RGB
                        'depth': colorized_depth,
                        'ir': self.latest_right  # Use right image as IR equivalent
                    }
                    
                    # Send frames to UI
                    if frames and self.frame_callback:
                        self.frame_callback(frames)
                        
                    # Handle video recording if active
                    if self.running and hasattr(self, 'video_writers') and self.video_writers:
                        try:
                            if self.latest_left is not None and self.video_writers.get('rgb'):
                                self.video_writers['rgb'].write(self.latest_left)
                                
                            if self.latest_depth is not None and self.video_writers.get('depth'):
                                self.video_writers['depth'].write(self.latest_depth)
                                
                            if self.latest_right is not None and self.video_writers.get('ir'):
                                # Convert to BGR for OpenCV video writer
                                right_bgr = cv2.cvtColor(self.latest_right, cv2.COLOR_RGB2BGR) 
                                self.video_writers['ir'].write(right_bgr)
                                
                            last_write_time = current_time
                        except Exception as e:
                            print(f"Error writing video frames: {str(e)}")
                
                time.sleep(0.001)  # Small sleep to prevent CPU overload
                
            except Exception as e:
                print(f"Error in camera update: {str(e)}")
                time.sleep(1)
                continue
                
    def stop_camera(self):
        """
        Stop the ZED camera and clean up resources.
        """
        self.running = False
        if self.camera_thread:
            self.camera_thread.join(timeout=1.0)
            
        if self.video_writers:
            for writer in self.video_writers.values():
                if writer is not None:
                    writer.release()
            self.video_writers = None
            
        if self.camera:
            # Disable positional tracking if it was enabled
            # self.camera.disable_positional_tracking()
            
            # Close the camera
            self.camera.close()
            self.camera = None
            
    def set_mask(self, coords: Tuple[int, int, int, int]):
        """
        Update mask coordinates used to black out a region of the frame.
        """
        self.mask_coords = coords
        
    def apply_mask(self, frame: np.ndarray) -> np.ndarray:
        """
        Apply a rectangular mask to the frame if needed.
        """
        if frame is None:
            return None
            
        # (x1, y1, x2, y2)
        x1, y1, x2, y2 = self.mask_coords
        if x2 <= x1 or y2 <= y1:
            # No valid mask area, just return original
            return frame
            
        mask = np.ones(frame.shape[:2], dtype=np.uint8) * 255
        cv2.rectangle(mask, (x1, y1), (x2, y2), 0, -1)
        
        if len(frame.shape) == 3:  # If color
            mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            
        return cv2.bitwise_and(frame, mask)
        
    def get_current_device_info(self) -> Optional[Dict]:
        """
        Return last device info if needed.
        """
        return self.current_device_info
        
    def set_resolution(self, resolution):
        """
        Set camera resolution for next startup.
        """
        resolutions = {
            'HD720': sl.RESOLUTION.HD720,
            'HD1080': sl.RESOLUTION.HD1080,
            'HD2K': sl.RESOLUTION.HD2K,
            'VGA': sl.RESOLUTION.VGA
        }
        
        if resolution in resolutions:
            self.camera_resolution = resolutions[resolution]
            
    def set_fps(self, fps):
        """
        Set camera FPS for next startup.
        """
        self.camera_fps = fps
        
    def __del__(self):
        if self.video_writers:
            for writer in self.video_writers.values():
                if writer is not None:
                    writer.release()
        self.stop_camera()