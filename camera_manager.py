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
        self.video_writers = None
        
        # Queues for frames. Created after pipeline/device is started
        self.latest_rgb_video = None
        self.q_rgb_preview = None
        self.q_rgb_video = None
        self.q_depth = None
        self.q_left = None
        self.q_control = None

    def find_devices(self) -> List[dai.DeviceInfo]:
        """
        Find all available OAK devices, but only return PoE devices
        since we are focusing on the OAK-D Pro PoE.
        """
        self.available_devices = []
        try:
            for device in dai.Device.getAllAvailableDevices():
                # Check if device is PoE
                if device.protocol == dai.XLinkProtocol.X_LINK_TCP_IP:
                    self.available_devices.append(device)
                    print(f"Found PoE device: {device.getMxId()} at {device.name}")
                else:
                    print(f"Skipping non-PoE device: {device.getMxId()}")
        except Exception as e:
            print(f"Error finding devices: {e}")

        return self.available_devices

    def get_device_info(self, device_info: dai.DeviceInfo) -> Dict:
        """
        Get detailed information about a device.
        Note: We briefly open the device to query info, then close.
        """
        try:
            with dai.Device(device_info) as device:
                cameras = device.getConnectedCameras()
                # features = device.getConnectedFeatures()

                return {
                    'name': device_info.getMxId(),
                    'cameras': [str(cam) for cam in cameras],
                    # 'features': [str(feature) for feature in features],
                    'protocol': str(device_info.protocol),
                    'state': str(device_info.state),
                    'ip': device_info.name if device_info.protocol == dai.XLinkProtocol.X_LINK_TCP_IP else None
                }
        except Exception as e:
            print(f"Error getting device info: {str(e)}")
            return {}

    def create_pipeline(self) -> dai.Pipeline:
        """
        Create and configure the DepthAI pipeline to:
        - Align depth to the RGB camera
        - Limit depth to ~7 meters
        - Use subpixel, L-R check, and a median filter to reduce noise
        """
        pipeline = dai.Pipeline()

        # RGB camera node
        cam_rgb = pipeline.createColorCamera()
        cam_rgb.setVideoSize(1280, 720)
        cam_rgb.setPreviewSize(640, 480)
        cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_720_P)
        cam_rgb.setInterleaved(False)
        cam_rgb.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
        cam_rgb.setFps(30)

        # We'll use a control input to configure auto-exposure, etc.
        controlIn = pipeline.createXLinkIn()
        controlIn.setStreamName('control')
        controlIn.out.link(cam_rgb.inputControl)

        # Mono cameras
        mono_left = pipeline.createMonoCamera()
        mono_right = pipeline.createMonoCamera()
        mono_left.setResolution(dai.MonoCameraProperties.SensorResolution.THE_720_P)
        mono_right.setResolution(dai.MonoCameraProperties.SensorResolution.THE_720_P)
        mono_left.setBoardSocket(dai.CameraBoardSocket.LEFT)
        mono_right.setBoardSocket(dai.CameraBoardSocket.RIGHT)
        mono_left.setFps(30)
        mono_right.setFps(30)

        # Stereo depth node
        stereo = pipeline.createStereoDepth()
        stereo.setLeftRightCheck(True)
        stereo.setSubpixel(True)
        stereo.setExtendedDisparity(False)
        stereo.setDepthAlign(dai.CameraBoardSocket.RGB)
        stereo.setMedianFilter(dai.StereoDepthProperties.MedianFilter.KERNEL_5x5)
        config = stereo.initialConfig.get()
        config.postProcessing.speckleFilter.enable = True
        config.postProcessing.speckleFilter.speckleRange = 12
        config.postProcessing.temporalFilter.enable = True
        config.postProcessing.decimationFilter.decimationFactor = 2
        config.postProcessing.thresholdFilter.minRange = 400
        config.postProcessing.thresholdFilter.maxRange = 8000
        stereo.initialConfig.set(config)
        # Below is for older DepthAI versions. For newer ones, you can also do setDepthUnits, etc.


        # Link mono cameras to stereo
        mono_left.out.link(stereo.left)
        mono_right.out.link(stereo.right)

        # # Create XLink outputs
        # 1) Low-res preview for UI
        xout_rgb_preview = pipeline.createXLinkOut()
        xout_rgb_preview.setStreamName("rgb_preview")
        cam_rgb.preview.link(xout_rgb_preview.input)

        # 2) High-res video for saving
        xout_rgb_video = pipeline.createXLinkOut()
        xout_rgb_video.setStreamName("rgb_video")
        cam_rgb.video.link(xout_rgb_video.input)

        xout_depth = pipeline.createXLinkOut()
        xout_depth.setStreamName("depth")
        stereo.depth.link(xout_depth.input)

        xout_left = pipeline.createXLinkOut()
        xout_left.setStreamName("left")
        mono_left.out.link(xout_left.input)

        return pipeline

    def start_camera(
        self,
        device_info: Optional[dai.DeviceInfo] = None,
        frame_callback: Callable = None,
        device_info_callback: Callable = None
    ) -> bool:
        """
        Start the camera with PoE support, initialize queues, send auto controls.
        """
        if self.running:
            print("Camera already running.")
            return False
        try:
            self.pipeline = self.create_pipeline()

            # If a device was selected, use it. Otherwise find the first available PoE device
            if device_info:
                if device_info.protocol == dai.XLinkProtocol.X_LINK_TCP_IP:
                    self.device = dai.Device(self.pipeline, device_info)
                else:
                    raise Exception("Selected device is not a PoE device.")
            else:
                available = self.find_devices()
                if not available:
                    raise Exception("No PoE devices found.")
                self.device = dai.Device(self.pipeline, available[0])

            # Retrieve device info for UI or logging
            self.current_device_info = self.get_device_info(
                device_info if device_info else self.device.getDeviceInfo()
            )
            if device_info_callback:
                device_info_callback(self.current_device_info)

            # Get output queues
            self.q_rgb_preview = self.device.getOutputQueue(name="rgb_preview", maxSize=4, blocking=False)
            self.q_rgb_video = self.device.getOutputQueue(name="rgb_video", maxSize=4, blocking=False)
            self.q_depth = self.device.getOutputQueue(name="depth", maxSize=4, blocking=False)
            self.q_left = self.device.getOutputQueue(name="left", maxSize=4, blocking=False)

            # Control input queue
            self.q_control = self.device.getInputQueue('control')

            # Send initial auto control commands
            ctrl = dai.CameraControl()
            ctrl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.CONTINUOUS_PICTURE)
            ctrl.setAutoWhiteBalanceMode(dai.CameraControl.AutoWhiteBalanceMode.AUTO)
            ctrl.setAutoExposureEnable()  # Enables auto-exposure for the RGB camera
            self.q_control.send(ctrl)

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
        """ Continuously read frames from the queues and pass them to the callback. """
        while self.running:
            try:
                frames = {}

                if in_rgb := self.q_rgb_preview.tryGet():
                    frame_rgb = in_rgb.getCvFrame()
                    frame_rgb = self.apply_mask(frame_rgb)
                    frames['rgb'] = frame_rgb

                # Drain the high-res RGB video stream and store the latest frame
                if in_rgb_video := self.q_rgb_video.tryGet():
                    self.latest_rgb_video = in_rgb_video.getCvFrame()

                if in_depth := self.q_depth.tryGet():
                    # Depth is 16-bit data. We can colorize it for display:
                    depth_frame_16 = in_depth.getFrame()  
                    # Normalize and colorize for preview
                    depth_frame_8 = cv2.normalize(depth_frame_16, None, 0, 255, cv2.NORM_MINMAX)
                    depth_frame_8 = depth_frame_8.astype(np.uint8)
                    colorized_depth = cv2.applyColorMap(depth_frame_8, cv2.COLORMAP_JET)

                    colorized_depth = self.apply_mask(colorized_depth)
                    frames['depth'] = colorized_depth
                    # Also store the raw 16-bit if you want to save it later:
                    frames['depth_raw'] = depth_frame_16

                if in_left := self.q_left.tryGet():
                    frame_ir = in_left.getCvFrame()
                    # Normalize or equalize for better IR contrast
                    frame_ir = cv2.normalize(frame_ir, None, 0, 255, cv2.NORM_MINMAX)
                    frame_ir = cv2.equalizeHist(frame_ir)
                    frame_ir = self.apply_mask(frame_ir)
                    frames['ir'] = frame_ir

                # Send frames to the UI or whomever uses them
                if frames and self.frame_callback:
                    self.frame_callback(frames)

                if self.running and hasattr(self, 'video_writers') and self.video_writers:
                    try:
                        # Use high-res RGB video frame for recording
                        if self.latest_rgb_video is not None and self.video_writers.get('rgb'):
                            self.video_writers['rgb'].write(self.latest_rgb_video)
                            
                        if in_depth and self.video_writers.get('depth'):
                            # Use colorized depth for recording
                            depth_frame_16 = in_depth.getFrame()
                            depth_frame_8 = cv2.normalize(depth_frame_16, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
                            colorized_depth = cv2.applyColorMap(depth_frame_8, cv2.COLORMAP_JET)
                            self.video_writers['depth'].write(colorized_depth)
                            
                        if in_left and self.video_writers.get('ir'):
                            # Process and record IR frame
                            ir_frame = in_left.getCvFrame()
                            ir_frame = cv2.normalize(ir_frame, None, 0, 255, cv2.NORM_MINMAX)
                            ir_frame = cv2.equalizeHist(ir_frame)
                            ir_bgr = cv2.cvtColor(ir_frame, cv2.COLOR_GRAY2BGR)
                            self.video_writers['ir'].write(ir_bgr)
                    except Exception as e:
                        print(f"Error writing video frames: {str(e)}")
                        
            except Exception as e:
                print(f"Error in camera update: {str(e)}")
                time.sleep(1)
                continue

            time.sleep(0.001)

    def stop_camera(self):
        """ Stop camera and clean up resources. """
        self.running = False
        if self.camera_thread:
            self.camera_thread.join(timeout=1.0)

        if self.video_writers:
            for writer in self.video_writers.values():
                if writer is not None:
                    writer.release()
            self.video_writers = None
            
        if self.device:
            try:
                self.device.close()
            except Exception as e:
                print(f"Error closing device: {e}")
            finally:
                self.device = None

    def set_mask(self, coords: Tuple[int, int, int, int]):
        """ Update mask coordinates used to black out a region of the frame. """
        self.mask_coords = coords

    def apply_mask(self, frame: np.ndarray) -> np.ndarray:
        """ Apply a rectangular mask to the frame if needed. """
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
        """ Return last device info if needed. """
        return self.current_device_info

    def __del__(self):
        if self.video_writers:
            for writer in self.video_writers.values():
                if writer is not None:
                    writer.release()
        self.stop_camera()
    