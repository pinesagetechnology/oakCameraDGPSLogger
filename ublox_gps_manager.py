import serial
import pynmea2
import glob
import os
import threading
import time
from typing import Optional, Callable
import json

class UbloxGPSManager:
    def __init__(self):
        self.running = False
        self.current_coords = None
        self.gps_thread = None
        self.serial_connection = None
        self._callback = None
        # ANN-MB typically uses 9600 baud rate
        self.baudrate = 9600
        
    def find_gps_port(self) -> Optional[str]:
        """Find the USB port for the GPS receiver"""
        patterns = [
            '/dev/ttyACM*',  # Most common for ANN-MB series
            '/dev/ttyUSB*',
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
                baudrate=self.baudrate,
                timeout=1,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            
            # Give the GPS module time to initialize
            time.sleep(1)
            
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
                if self.serial_connection.in_waiting:
                    line = self.serial_connection.readline().decode('ascii', errors='replace')
                    
                    # ANN-MB series typically provides these NMEA sentences
                    if any(line.startswith(f'${prefix}') for prefix in ['GNGGA', 'GNRMC', 'GPRMC', 'GNVTG']):
                        msg = pynmea2.parse(line)
                        
                        if hasattr(msg, 'latitude') and hasattr(msg, 'longitude'):
                            if msg.latitude and msg.longitude:  # Check if we have valid coordinates
                                self.current_coords = {
                                    'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S') if hasattr(msg, 'timestamp') else time.strftime('%Y-%m-%d %H:%M:%S'),
                                    'latitude': msg.latitude,
                                    'lat_dir': msg.lat_dir if hasattr(msg, 'lat_dir') else 'N',
                                    'longitude': msg.longitude,
                                    'lon_dir': msg.lon_dir if hasattr(msg, 'lon_dir') else 'E',
                                    'altitude': msg.altitude if hasattr(msg, 'altitude') else None,
                                    'speed': msg.spd_over_grnd if hasattr(msg, 'spd_over_grnd') else None,
                                    'num_sats': msg.num_sats if hasattr(msg, 'num_sats') else None,
                                    'fix_quality': msg.gps_qual if hasattr(msg, 'gps_qual') else None
                                }
                                
                                if self._callback:
                                    self._callback(self.current_coords)
                            
            except (pynmea2.ParseError, UnicodeDecodeError) as e:
                print(f"GPS Parse Error: {str(e)}")
                continue
            except Exception as e:
                print(f"GPS Read Error: {str(e)}")
                time.sleep(0.1)
                
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

    def get_device_info(self) -> dict:
        """Get GPS device information"""
        info = {
            'port': self.serial_connection.port if self.serial_connection else None,
            'baudrate': self.baudrate,
            'running': self.running
        }
        if self.current_coords:
            info.update({
                'fix_quality': self.current_coords.get('fix_quality'),
                'num_satellites': self.current_coords.get('num_sats')
            })
        return info
                
    def __del__(self):
        self.stop_gps()