# OAK-D Camera with GPS Logger

This application combines OAK-D camera functionality with GPS logging capabilities. It captures RGB, depth, and IR images along with GPS coordinates at configurable intervals.

## Requirements

- Ubuntu 22.04 or later
- Python 3.8 or later
- OAK-D Camera
- GPS receiver 353N5

## Installation

1. Install required Python packages:
```bash
pip install depthai opencv-python pillow pyserial pynmea2 numpy
```

2. Ensure you have proper permissions for the GPS device:
```bash
sudo chmod a+rw /dev/ttyUSB*  # Adjust device path if needed
```

## Usage

1. Start the application:
```bash
python main.py
```

2. Configure the settings:
   - Save Directory: Choose where to save images and GPS data
   - Save Interval: Set how often to capture (in seconds)
   - Mask: Set region of interest (x1,y1,x2,y2)

3. Controls:
   - Start/Stop Camera: Toggle camera operation
   - Apply Mask: Update the region of interest
   - Browse: Change save directory

4. File Output:
   - Images are saved as JPG files
   - GPS data is saved as JSON files with matching names
   - Example:
     ```
     rgb_20250119_143000.jpg
     rgb_20250119_143000.json
     depth_20250119_143000.jpg
     depth_20250119_143000.json
     ir_20250119_143000.jpg
     ir_20250119_143000.json
     ```

## Troubleshooting

1. GPS Connection Issues:
   - Check if device is recognized: `ls -l /dev/ttyUSB*`
   - Verify permissions: `ls -l /dev/ttyUSB0`
   - Try running: `sudo chmod a+rw /dev/ttyUSB0`

2. Camera Issues:
   - Ensure OAK-D is properly connected
   - Check if device is recognized: `lsusb`
   - Try unplugging and reconnecting the camera

## Features

- Real-time display of RGB, depth, and IR feeds
- Configurable save interval
- Adjustable region of interest mask
- GPS coordinate logging
- Automatic file naming and organization
- GPS status display
- Clean shutdown handling