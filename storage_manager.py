import os
import cv2
from datetime import datetime
from typing import Dict, Any
import json

class StorageManager:
    def __init__(self, base_path: str = "result"):
        """Initialize storage manager with base path"""
        self.base_path = base_path
        self._ensure_directory_exists()
        
    def _ensure_directory_exists(self):
        """Ensure the storage directory exists"""
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)
            
    def set_base_path(self, path: str):
        """Set new base path for storage"""
        self.base_path = path
        self._ensure_directory_exists()
        
    def get_base_path(self) -> str:
        """Get current base path"""
        return self.base_path
        
    def save_frame(self, frame: Any, frame_type: str, timestamp: datetime) -> str:
        """Save a frame with timestamp"""
        filename = f'{frame_type}_{timestamp.strftime("%Y%m%d_%H%M%S")}.jpg'
        filepath = os.path.join(self.base_path, filename)
        cv2.imwrite(filepath, frame)
        return filepath
        
    def save_metadata(self, metadata: Dict, filepath: str):
        """Save metadata to JSON file"""
        json_path = filepath.rsplit('.', 1)[0] + '.json'
        with open(json_path, 'w') as f:
            json.dump(metadata, f, indent=4)
            
    def save_frames_with_metadata(self, 
                                frames: Dict[str, Any], 
                                metadata: Dict,
                                timestamp: datetime = None,
                                capture_type: str = "auto"):
        """Save multiple frames with associated metadata"""
        if timestamp is None:
            timestamp = datetime.now()
            
        # Add capture type to metadata
        metadata['capture_type'] = capture_type
            
        saved_files = []
        for frame_type, frame in frames.items():
            filepath = self.save_frame(frame, frame_type, timestamp)
            self.save_metadata(metadata, filepath)
            saved_files.append(filepath)
            
        return saved_files