import serial
import pynmea2
import glob
import os
import threading
import time
from typing import Optional, Callable
import json
from math import radians, sin, cos, sqrt, atan2 

class GPSManager:
    def __init__(self):
        self.running = False
        self.current_coords = None
        self.gps_thread = None
        self.serial_connection = None
        self._callback = None
        self.last_position = None
        
    def calculate_distance(self, coord1, coord2):
        """
        Calculate distance between two GPS coordinates using the Haversine formula
        Returns distance in meters
        """
        # Earth's radius in meters
        R = 6371000
        
        # Convert latitude and longitude to radians
        lat1 = radians(float(coord1['latitude']))
        lon1 = radians(float(coord1['longitude']))
        lat2 = radians(float(coord2['latitude']))
        lon2 = radians(float(coord2['longitude']))
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        distance = R * c
        
        return distance
        
    def get_distance_moved(self):
        """
        Calculate distance moved from last position
        Returns (distance_moved, current_coords)
        """
        current = self.get_current_location()
        if not current or not self.last_position:
            self.last_position = current
            return 0, current
            
        distance = self.calculate_distance(self.last_position, current)
        return distance, current

    def find_gps_port(self) -> Optional[str]:
        """Find the USB port for the GPS receiver"""
        patterns = [
            '/dev/ttyUSB*',
            '/dev/ttyACM*',
            '/dev/tty.usbserial*'
        ]
        
        for pattern in patterns:
            ports = glob.glob(pattern)
            if ports:
                return ports[0]
        return None
        
    def start_gps(self, callback: Optional[Callable] = None) -> bool:
        """Start GPS reading in a separate thread"""
        if self.running:
            return False
            
        port = self.find_gps_port()
        if not port:
            raise Exception("GPS device not found! Please check connection.")
            
        try:
            self.serial_connection = serial.Serial(
                port=port,
                baudrate=4800,
                timeout=1
            )
            
            self.running = True
            self._callback = callback
            self.gps_thread = threading.Thread(target=self._read_gps)
            self.gps_thread.daemon = True
            self.gps_thread.start()
            return True
            
        except serial.SerialException as e:
            raise Exception(f"Failed to connect to GPS: {str(e)}")
            
    def _read_gps(self):
        """GPS reading loop"""
        while self.running:
            try:
                line = self.serial_connection.readline().decode('ascii', errors='replace')
                
                if line.startswith('$GPRMC') or line.startswith('$GNRMC'):
                    msg = pynmea2.parse(line)
                    if msg.latitude and msg.longitude:
                        self.current_coords = {
                            'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                            'latitude': msg.latitude,
                            'lat_dir': msg.lat_dir,
                            'longitude': msg.longitude,
                            'lon_dir': msg.lon_dir,
                            'speed': msg.spd_over_grnd
                        }
                        
                        if self._callback:
                            self._callback(self.current_coords)
                            
            except (pynmea2.ParseError, UnicodeDecodeError):
                continue
                
    def get_current_location(self) -> Optional[dict]:
        """Get the most recent GPS coordinates"""
        return self.current_coords
        
    def stop_gps(self):
        """Stop GPS reading"""
        self.running = False
        if self.serial_connection:
            self.serial_connection.close()
        if self.gps_thread:
            self.gps_thread.join(timeout=1.0)
            
    def save_coords_to_json(self, filepath: str):
        """Save current coordinates to a JSON file"""
        if self.current_coords:
            with open(filepath, 'w') as f:
                json.dump(self.current_coords, f, indent=4)
                
    def __del__(self):
        self.stop_gps()