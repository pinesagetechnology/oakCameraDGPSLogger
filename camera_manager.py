import depthai as dai
import cv2
import numpy as np
import threading
import time
from typing import Optional, Tuple, Callable, List, Dict
from datetime import datetime

class CameraManager:
    def __init__(self):
        self.running = False
        self.device = None
        self.pipeline = None
        self.camera_thread = None
        self.frame_callback = None
        self.mask_coords = [0, 0, 0, 0]
        self.available_devices = []
        self.current_device_info = None
        self.device_info_callback = None
        
    def find_devices(self) -> List[dai.DeviceInfo]:
        """Find all available OAK devices"""
        try:
            # Find all available devices
            self.available_devices = dai.Device.getAllAvailableDevices()
            
            print(f"Found {len(self.available_devices)} devices")
            for device in self.available_devices:
                print(f"Device: {device.getMxId()} - State: {device.state}")
                
            return self.available_devices
        except Exception as e:
            print(f"Error finding devices: {e}")
            return []
        
    def get_device_info(self, device_info: dai.DeviceInfo) -> Dict:
        """Get detailed information about a device"""
        try:
            with dai.Device(device_info) as device:
                cameras = device.getConnectedCameras()
                usb_speed = device.getUsbSpeed()

                # Check if IMU is available
                has_imu = device.getConnectedIMU() is not None

                return {
                    'name': device_info.getMxId(),
                    'cameras': [str(cam) for cam in cameras],
                    'usb_speed': str(usb_speed),
                    'has_imu': has_imu,
                    'state': device_info.state,
                    'protocol': device_info.protocol
                }
        except Exception as e:
            print(f"Error getting device info: {str(e)}")
            return None
            
    def create_pipeline(self) -> dai.Pipeline:
        """Create and configure the camera pipeline"""
        pipeline = dai.Pipeline()

        # RGB camera node
        cam_rgb = pipeline.createColorCamera()
        cam_rgb.setPreviewSize(640, 480)
        cam_rgb.setInterleaved(False)
        cam_rgb.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
        cam_rgb.initialControl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.CONTINUOUS_PICTURE)
        cam_rgb.initialControl.setAutoExposureEnable()
        cam_rgb.initialControl.setAutoWhiteBalanceMode(dai.CameraControl.AutoWhiteBalanceMode.AUTO)

        # Mono cameras
        mono_left = pipeline.createMonoCamera()
        mono_right = pipeline.createMonoCamera()
        mono_left.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
        mono_right.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
        mono_left.setBoardSocket(dai.CameraBoardSocket.LEFT)
        mono_right.setBoardSocket(dai.CameraBoardSocket.RIGHT)
        mono_left.initialControl.setAutoExposureEnable()
        mono_right.initialControl.setAutoExposureEnable()

        # Stereo depth
        stereo = pipeline.createStereoDepth()
        mono_left.out.link(stereo.left)
        mono_right.out.link(stereo.right)

        # Create outputs
        xout_rgb = pipeline.createXLinkOut()
        xout_depth = pipeline.createXLinkOut()
        xout_left = pipeline.createXLinkOut()
        
        xout_rgb.setStreamName("rgb")
        xout_depth.setStreamName("depth")
        xout_left.setStreamName("left")

        cam_rgb.preview.link(xout_rgb.input)
        stereo.depth.link(xout_depth.input)
        mono_left.out.link(xout_left.input)

        return pipeline
        
    def start_camera(self, device_info: Optional[dai.DeviceInfo] = None, 
                    frame_callback: Callable = None,
                    device_info_callback: Callable = None) -> bool:
        """Start the camera with optional device selection"""
        if self.running:
            return False
            
        try:
            self.pipeline = self.create_pipeline()
            
            # Create device with specific device_info if provided
            if device_info:
                self.device = dai.Device(self.pipeline, device_info)
            else:
                self.device = dai.Device(self.pipeline)
            
            self.current_device_info = self.get_device_info(device_info if device_info else self.device.getDeviceInfo())
            if device_info_callback:
                device_info_callback(self.current_device_info)
            
            # Get output queues
            self.q_rgb = self.device.getOutputQueue(name="rgb", maxSize=4, blocking=False)
            self.q_depth = self.device.getOutputQueue(name="depth", maxSize=4, blocking=False)
            self.q_left = self.device.getOutputQueue(name="left", maxSize=4, blocking=False)
            
            self.running = True
            self.frame_callback = frame_callback
            self.camera_thread = threading.Thread(target=self._update_camera)
            self.camera_thread.daemon = True
            self.camera_thread.start()
            return True
            
        except Exception as e:
            raise Exception(f"Failed to start camera: {str(e)}")
            
    def _update_camera(self):
        """Camera update loop"""
        while self.running:
            try:
                frames = {}
                
                if in_rgb := self.q_rgb.tryGet():
                    frame_rgb = in_rgb.getCvFrame()
                    frame_rgb = self.apply_mask(frame_rgb)
                    frames['rgb'] = frame_rgb

                if in_depth := self.q_depth.tryGet():
                    frame_depth = in_depth.getFrame()
                    frame_depth = cv2.normalize(frame_depth, None, 0, 255, cv2.NORM_MINMAX)
                    frame_depth = frame_depth.astype(np.uint8)
                    frame_depth = cv2.applyColorMap(frame_depth, cv2.COLORMAP_JET)
                    frame_depth = self.apply_mask(frame_depth)
                    frames['depth'] = frame_depth

                if in_left := self.q_left.tryGet():
                    frame_ir = in_left.getCvFrame()
                    frame_ir = cv2.normalize(frame_ir, None, 0, 255, cv2.NORM_MINMAX)
                    frame_ir = cv2.equalizeHist(frame_ir)
                    frame_ir = self.apply_mask(frame_ir)
                    frames['ir'] = frame_ir

                if frames and self.frame_callback:
                    self.frame_callback(frames)
                    
            except Exception as e:
                print(f"Error in camera update: {str(e)}")
                
            time.sleep(0.001)  # Small sleep to prevent busy waiting
                
    def stop_camera(self):
        """Stop the camera"""
        self.running = False
        if self.camera_thread:
            self.camera_thread.join(timeout=1.0)
        if self.device:
            self.device.close()
            self.device = None
            
    def set_mask(self, coords: Tuple[int, int, int, int]):
        """Set mask coordinates"""
        self.mask_coords = coords
        
    def apply_mask(self, frame):
        """Apply mask to frame"""
        mask = np.ones(frame.shape[:2], dtype=np.uint8) * 255
        cv2.rectangle(mask, 
                     (self.mask_coords[0], self.mask_coords[1]),
                     (self.mask_coords[2], self.mask_coords[3]), 
                     0, -1)
        
        if len(frame.shape) == 3:
            mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        
        return cv2.bitwise_and(frame, mask)
        
    def get_current_device_info(self) -> Optional[Dict]:
        """Get current device information"""
        return self.current_device_info
        
    def __del__(self):
        self.stop_camera()