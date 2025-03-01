import serial
import pyubx2
import glob
import os
import threading
import time
from typing import Optional, Callable, Dict
import json
from math import radians, sin, cos, sqrt, atan2 

class UBloxGPSManager:
    def __init__(self):
        self.running = False
        self.current_coords = None
        self.gps_thread = None
        self.serial_connection = None
        self._callback = None
        self.last_position = None
        self.stream = None
        self.baud_rate = 9600  # Default baud rate for U-BLOX GPS
        
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
        """
        Find the USB port for the U-BLOX GPS receiver.
        For U-BLOX devices, try common USB serial patterns.
        """
        patterns = [
            '/dev/ttyACM*',      # Common for U-BLOX on Linux
            '/dev/ttyUSB*',      # USB-to-Serial converters on Linux
            '/dev/tty.usbmodem*', # U-BLOX on macOS
            '/dev/tty.usbserial*' # Serial converters on macOS
        ]
        
        for pattern in patterns:
            ports = glob.glob(pattern)
            for port in ports:
                try:
                    # Try to open the port
                    with serial.Serial(port, baudrate=self.baud_rate, timeout=1) as ser:
                        # Wait a bit for the device to initialize
                        time.sleep(0.2)
                        # Read some data to check if it's a GPS
                        data = ser.read(100)
                        # Check for UBX or NMEA signature patterns
                        if (b'\xb5\x62' in data) or (b'$GN' in data) or (b'$GP' in data):
                            print(f"Found likely U-BLOX GPS at {port}")
                            return port
                except (serial.SerialException, OSError):
                    continue
        
        # If automatic detection fails, provide common default ports for user to try
        print("No U-BLOX GPS device automatically detected.")
        return None
        
    def set_baudrate(self, baudrate: int):
        """
        Set the baudrate for the GPS device
        """
        self.baud_rate = baudrate
        
    def start_gps(self, callback: Optional[Callable] = None, port: Optional[str] = None) -> bool:
        """
        Start GPS reading in a separate thread
        
        Args:
            callback: Function to call with GPS data
            port: Optional specific port to use instead of auto-detection
        """
        if self.running:
            return False
            
        gps_port = port if port else self.find_gps_port()
        if not gps_port:
            raise Exception("U-BLOX GPS device not found! Please check connection.")
            
        try:
            self.serial_connection = serial.Serial(
                port=gps_port,
                baudrate=self.baud_rate,
                timeout=1
            )
            
            # Create UBX parser
            self.stream = pyubx2.UBXReader(self.serial_connection)
            
            # Try to configure the device to enable specific messages if needed
            self.configure_gps()
            
            self.running = True
            self._callback = callback
            self.gps_thread = threading.Thread(target=self._read_gps)
            self.gps_thread.daemon = True
            self.gps_thread.start()
            return True
            
        except serial.SerialException as e:
            raise Exception(f"Failed to connect to U-BLOX GPS: {str(e)}")
            
    def configure_gps(self):
        """
        Configure the U-BLOX GPS receiver to output the desired messages
        """
        try:
            # Create UBX message to enable NMEA GGA, RMC, and VTG messages
            # Enable GxGGA (GNSS fix data)
            cfg_msg_gga = pyubx2.UBXMessage.config_message(
                pyubx2.NMEA_PROTOCOL, "GGA", pyubx2.NMEA_PORT, 1
            )
            
            # Enable GxRMC (Recommended Minimum data)
            cfg_msg_rmc = pyubx2.UBXMessage.config_message(
                pyubx2.NMEA_PROTOCOL, "RMC", pyubx2.NMEA_PORT, 1
            )
            
            # Enable GxVTG (Course and speed over ground)
            cfg_msg_vtg = pyubx2.UBXMessage.config_message(
                pyubx2.NMEA_PROTOCOL, "VTG", pyubx2.NMEA_PORT, 1
            )
            
            # Send messages to GPS
            self.serial_connection.write(cfg_msg_gga.serialize())
            time.sleep(0.1)  # Small delay between commands
            self.serial_connection.write(cfg_msg_rmc.serialize())
            time.sleep(0.1)
            self.serial_connection.write(cfg_msg_vtg.serialize())
            
            print("U-BLOX GPS configuration sent.")
            
        except Exception as e:
            print(f"Warning: Could not configure GPS: {str(e)}")
            
    def _read_gps(self):
        """
        GPS reading loop - handles both UBX binary protocol and NMEA messages
        """
        while self.running:
            try:
                # Read data from the GPS
                (raw_data, parsed_data) = self.stream.read()
                
                # Process the parsed data based on its type
                if parsed_data:
                    if isinstance(parsed_data, pyubx2.UBXMessage):
                        # Handle UBX binary message
                        self._process_ubx_message(parsed_data)
                    else:
                        # Handle NMEA message
                        self._process_nmea_message(parsed_data)
                        
            except (pyubx2.UBXParseError, serial.SerialException) as e:
                print(f"GPS read error: {str(e)}")
                time.sleep(1)
                continue
            except Exception as e:
                print(f"Unexpected GPS error: {str(e)}")
                time.sleep(1)
                continue
                
    def _process_ubx_message(self, message):
        """
        Process UBX binary messages
        """
        try:
            # Process NAV-PVT message (contains position, velocity, time)
            if message.identity == "NAV-PVT":
                lat = message.lat / 10000000.0  # Scaled to degrees
                lon = message.lon / 10000000.0  # Scaled to degrees
                
                # Only update if we have a valid fix
                if hasattr(message, 'fixType') and message.fixType >= 2:
                    self.current_coords = {
                        'timestamp': message.time.isoformat() if hasattr(message, 'time') else time.strftime('%Y-%m-%d %H:%M:%S'),
                        'latitude': lat,
                        'lat_dir': 'N' if lat >= 0 else 'S',
                        'longitude': lon,
                        'lon_dir': 'E' if lon >= 0 else 'W',
                        'speed': message.gSpeed / 1000.0 if hasattr(message, 'gSpeed') else 0,  # Convert mm/s to m/s
                        'altitude': message.height / 1000.0 if hasattr(message, 'height') else 0,  # Convert mm to m
                        'fix_type': message.fixType if hasattr(message, 'fixType') else 0,
                        'satellites': message.numSV if hasattr(message, 'numSV') else 0
                    }
                    
                    if self._callback:
                        self._callback(self.current_coords)
                        
        except Exception as e:
            print(f"Error processing UBX message: {str(e)}")
            
    def _process_nmea_message(self, message):
        """
        Process NMEA messages
        """
        try:
            # Only update coordinates if this is a position message with valid data
            if message.msgID in ('GGA', 'RMC') and hasattr(message, 'lat'):
                if message.lat and message.lon:  # Check if not empty
                    
                    # Convert from DDMM.MMMMM format if needed
                    lat = self._convert_nmea_to_decimal(message.lat) if isinstance(message.lat, str) else message.lat
                    lon = self._convert_nmea_to_decimal(message.lon) if isinstance(message.lon, str) else message.lon
                    
                    lat_dir = message.NS if hasattr(message, 'NS') else ('N' if lat >= 0 else 'S')
                    lon_dir = message.EW if hasattr(message, 'EW') else ('E' if lon >= 0 else 'W')
                    
                    # Get speed if available
                    speed = 0
                    if hasattr(message, 'spd_over_grnd'):
                        speed = message.spd_over_grnd
                    elif hasattr(message, 'sogk'):
                        speed = message.sogk  # Speed over ground in km/h
                        
                    # Get timestamp
                    timestamp = None
                    if hasattr(message, 'datetime') and message.datetime:
                        timestamp = message.datetime.isoformat() 
                    else:
                        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                        
                    self.current_coords = {
                        'timestamp': timestamp,
                        'latitude': lat,
                        'lat_dir': lat_dir,
                        'longitude': lon,
                        'lon_dir': lon_dir,
                        'speed': speed,
                        'fix_quality': message.quality if hasattr(message, 'quality') else None,
                        'satellites': message.num_sats if hasattr(message, 'num_sats') else None
                    }
                    
                    if self._callback:
                        self._callback(self.current_coords)
                        
        except Exception as e:
            print(f"Error processing NMEA message: {str(e)}")
            
    def _convert_nmea_to_decimal(self, nmea_val):
        """
        Convert NMEA coordinate format (DDMM.MMMMM) to decimal degrees
        """
        try:
            if not nmea_val:
                return 0.0
                
            # Split into degrees and minutes parts
            deg_part = float(nmea_val[:2])  # First 2 chars are degrees
            min_part = float(nmea_val[2:])  # Rest is minutes
            
            # Convert to decimal degrees
            return deg_part + (min_part / 60.0)
        except Exception:
            return 0.0
        
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
                
    def get_device_info(self) -> Dict:
        """
        Get information about the GPS device
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return {"status": "Disconnected"}
            
        info = {
            "status": "Connected",
            "port": self.serial_connection.port,
            "baud_rate": self.serial_connection.baudrate
        }
        
        # Add GPS status if available
        if self.current_coords:
            info.update({
                "fix_quality": self.current_coords.get('fix_quality', 'Unknown'),
                "satellites": self.current_coords.get('satellites', 'Unknown'),
                "last_update": self.current_coords.get('timestamp', 'Unknown')
            })
            
        return info
                
    def __del__(self):
        self.stop_gps()