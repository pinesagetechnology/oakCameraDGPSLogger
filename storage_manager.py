import os
import cv2
from datetime import datetime
from typing import Dict, Any, Optional, List
import json
import numpy as np

class StorageManager:
    def __init__(self, base_path: str = "result"):
        """Initialize storage manager with base path"""
        self.base_path = base_path
        self.jpeg_quality = 100  # Maximum JPEG quality
        self.png_compression = 0  # No PNG compression for maximum quality
        self._ensure_directory_exists()

    def _ensure_directory_exists(self):
        """Ensure the storage directory exists with date-based organization."""
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)

        # Create date-based subdirectory
        today = datetime.now().strftime("%Y%m%d")
        self.current_path = os.path.join(self.base_path, today)
        if not os.path.exists(self.current_path):
            os.makedirs(self.current_path)

    def set_base_path(self, path: str):
        """Set new base path for storage"""
        self.base_path = path
        self._ensure_directory_exists()

    def get_base_path(self) -> str:
        """Get current base path"""
        return self.base_path

    def set_image_quality(self, jpeg_quality: int = 100, png_compression: int = 0):
        """
        Set image quality parameters
        :param jpeg_quality: 0-100, higher is better quality
        :param png_compression: 0-9, lower is better quality
        """
        self.jpeg_quality = max(0, min(100, jpeg_quality))
        self.png_compression = max(0, min(9, png_compression))

    def save_frame(self, frame: np.ndarray, frame_type: str, timestamp: datetime) -> str:
        """
        Save a frame with timestamp in high quality.
        If frame_type is "depth_raw", we store as 16-bit PNG to preserve actual distance data.
        For normal color frames or colorized depth, store as JPG or PNG.
        Returns the saved filepath.
        """
        if frame is None:
            raise ValueError("Cannot save None frame")

        if not isinstance(frame, np.ndarray):
            raise TypeError("Frame must be a numpy array")

        # Create timestamp-based filename to avoid collisions
        # e.g. "depth_20230218_153025" or "depth_raw_20230218_153025"
        filename = f"{frame_type}_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}"

        if frame_type == 'depth_raw':
            # We store 16-bit PNG
            filepath = os.path.join(self.current_path, f"{filename}.png")
            # Make sure frame is 16-bit
            if frame.dtype != np.uint16:
                # If your pipeline yields 16-bit, it should be np.uint16. Otherwise, convert if needed:
                frame = frame.astype(np.uint16)
            cv2.imwrite(filepath, frame, [cv2.IMWRITE_PNG_COMPRESSION, self.png_compression])

        elif frame_type == 'depth':
            # This is likely colorized depth (8-bit). We can store as PNG or JPG:
            filepath = os.path.join(self.current_path, f"{filename}.png")
            cv2.imwrite(filepath, frame, [cv2.IMWRITE_PNG_COMPRESSION, self.png_compression])

        else:
            # For RGB or IR, store as high-quality JPEG
            filepath = os.path.join(self.current_path, f"{filename}.jpg")
            cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])

        return filepath

    def save_metadata(self, metadata: Dict, filepath: str):
        """
        Save metadata to a JSON file with additional information.
        """
        enhanced_metadata = {
            **metadata,
            'save_timestamp': datetime.now().isoformat(),
            'image_quality': {
                'jpeg_quality': self.jpeg_quality,
                'png_compression': self.png_compression
            },
            'file_info': {
                'original_path': filepath,
                'filename': os.path.basename(filepath)
            }
        }

        # Save metadata with the same base name as the image
        json_path = filepath.rsplit('.', 1)[0] + '.json'
        with open(json_path, 'w') as f:
            json.dump(enhanced_metadata, f, indent=4)

    def save_frames_with_metadata(
        self,
        frames: Dict[str, np.ndarray],
        metadata: Dict,
        timestamp: Optional[datetime] = None,
        capture_type: str = "auto"
    ) -> List[str]:
        """
        Save multiple frames with associated metadata.
        Potentially includes RGB, IR, depth (colorized), and depth_raw (16-bit).
        Returns list of saved file paths.
        """
        if timestamp is None:
            timestamp = datetime.now()

        self._ensure_directory_exists()

        # Prepare extended metadata
        enhanced_metadata = {
            **metadata,
            'capture_type': capture_type,
            'capture_timestamp': timestamp.isoformat(),
            'storage_info': {
                'base_path': self.base_path,
                'capture_date': timestamp.strftime("%Y%m%d")
            }
        }

        saved_files = []
        try:
            for frame_type, frame in frames.items():
                if frame is not None:
                    filepath = self.save_frame(frame, frame_type, timestamp)
                    self.save_metadata(enhanced_metadata, filepath)
                    saved_files.append(filepath)
                else:
                    print(f"Warning: Skipping None frame for {frame_type}")

        except Exception as e:
            print(f"Error saving frames: {str(e)}")
            # Optional cleanup if partial saves occurred
            for fp in saved_files:
                try:
                    os.remove(fp)
                    json_path = fp.rsplit('.', 1)[0] + '.json'
                    if os.path.exists(json_path):
                        os.remove(json_path)
                except:
                    pass
            raise

        return saved_files

    def cleanup_old_files(self, days_to_keep: int = 30):
        """
        Delete files older than 'days_to_keep' in the base_path.
        """
        try:
            current_time = datetime.now()
            for root, dirs, files in os.walk(self.base_path):
                for file in files:
                    filepath = os.path.join(root, file)
                    file_time = datetime.fromtimestamp(os.path.getctime(filepath))
                    if (current_time - file_time).days > days_to_keep:
                        os.remove(filepath)
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")

    def get_storage_stats(self) -> Dict:
        """
        Return a dictionary with total size and file count.
        """
        total_size = 0
        file_count = 0
        for root, dirs, files in os.walk(self.base_path):
            for file in files:
                filepath = os.path.join(root, file)
                total_size += os.path.getsize(filepath)
                file_count += 1

        return {
            'total_size_mb': total_size / (1024 * 1024),
            'file_count': file_count,
            'base_path': self.base_path
        }

    def start_video_recording(self, video_path: str) -> dict:
        """
        Initialize video writers for RGB, Depth, and IR streams
        Returns dictionary of video writers
        """
        # Create date-based subdirectory
        timestamp = datetime.now()
        date_subdir = timestamp.strftime("%Y%m%d")
        video_subdir = os.path.join(video_path, date_subdir)
        
        if not os.path.exists(video_subdir):
            os.makedirs(video_subdir)
        
        time_str = timestamp.strftime("%H%M%S")
        video_writers = {}
        
        # Define video formats and paths
        formats = {
            'rgb': {
                'path': os.path.join(video_subdir, f'rgb_{time_str}.avi'),
                'fourcc': cv2.VideoWriter_fourcc(*'XVID'),
                'fps': 30,
                'size': (1280, 720)
            },
            'depth': {
                'path': os.path.join(video_subdir, f'depth_{time_str}.avi'),
                'fourcc': cv2.VideoWriter_fourcc(*'XVID'),
                'fps': 30,
                'size': (1280, 720)
            },
            'ir': {
                'path': os.path.join(video_subdir, f'ir_{time_str}.avi'),
                'fourcc': cv2.VideoWriter_fourcc(*'XVID'),
                'fps': 30,
                'size': (1280, 720)
            }
        }
        
        # Create video writers
        for stream, config in formats.items():
            video_writers[stream] = cv2.VideoWriter(
                config['path'],
                config['fourcc'],
                config['fps'],
                config['size']
            )
        
        return video_writers

    def stop_video_recording(self, video_writers: dict):
        """Release all video writers"""
        for writer in video_writers.values():
            if writer is not None:
                writer.release()

    def set_video_path(self, path: str):
        """Set path for video storage"""
        if not os.path.exists(path):
            os.makedirs(path)
        self.video_path = path

    def get_video_path(self) -> str:
        """Get current video storage path"""
        return getattr(self, 'video_path', os.path.join(self.base_path, 'videos'))