import depthai as dai
import cv2
import numpy as np
import threading
import time
from typing import Optional, Tuple, Callable
from datetime import datetime

class CameraManager:
    def __init__(self):
        self.running = False
        self.device = None
        self.pipeline = None
        self.camera_thread = None
        self.frame_callback = None
        self.mask_coords = [0, 0, 0, 0]
        
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
        
    def start_camera(self, frame_callback: Callable) -> bool:
        """Start the camera with frame callback"""
        if self.running:
            return False
            
        try:
            self.pipeline = self.create_pipeline()
            self.device = dai.Device(self.pipeline)
            
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
        
    def __del__(self):
        self.stop_camera()