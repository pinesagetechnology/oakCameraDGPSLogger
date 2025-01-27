import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import cv2
from typing import Callable, Dict, Any, List
import os
import depthai as dai

class UIManager:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("OAK-D Camera with GPS")
        
        # Callbacks
        self.start_callback = None
        self.stop_callback = None
        self.mask_callback = None
        self.directory_callback = None
        self.device_select_callback = None
        self.refresh_devices_callback = None
        
        # State
        self.running = False
        self.available_devices = []
        
        # Create UI elements
        self.setup_ui()
        
    def setup_ui(self):
        """Setup all UI elements"""
        # Device Selection Frame
        self.device_frame = ttk.LabelFrame(self.root, text="Device Selection")
        self.device_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        # Device dropdown
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(self.device_frame, 
                                       textvariable=self.device_var,
                                       state='readonly',
                                       width=50)
        self.device_combo.pack(side=tk.LEFT, padx=5, pady=5)
        self.device_combo.bind('<<ComboboxSelected>>', self._on_device_selected)
        
        # Refresh button
        self.refresh_btn = ttk.Button(
            self.device_frame,
            text="Refresh Devices",
            command=self._refresh_devices
        )
        self.refresh_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Device info label
        self.device_info_label = ttk.Label(self.device_frame, text="No device selected")
        self.device_info_label.pack(side=tk.LEFT, padx=20, pady=5)

        # Settings Frame
        self.settings_frame = ttk.LabelFrame(self.root, text="Settings")
        self.settings_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        # GPS Enable/Disable
        ttk.Label(self.settings_frame, text="GPS Module:").grid(row=0, column=0, padx=5, pady=5)
        self.gps_enabled = tk.BooleanVar(value=False)
        self.gps_toggle = ttk.Checkbutton(
            self.settings_frame, 
            text="Enable GPS",
            variable=self.gps_enabled,
            command=self._toggle_gps
        )
        self.gps_toggle.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        
        # Directory selection
        ttk.Label(self.settings_frame, text="Save Directory:").grid(row=1, column=0, padx=5, pady=5)
        self.dir_var = tk.StringVar(value=os.path.join(os.getcwd(), "result"))
        self.dir_entry = ttk.Entry(self.settings_frame, textvariable=self.dir_var, width=50)
        self.dir_entry.grid(row=1, column=1, padx=5, pady=5)
        self.dir_btn = ttk.Button(self.settings_frame, text="Browse", command=self._select_directory)
        self.dir_btn.grid(row=1, column=2, padx=5, pady=5)

        # Interval setting
        ttk.Label(self.settings_frame, text="Save Interval (seconds):").grid(row=2, column=0, padx=5, pady=5)
        self.interval_var = tk.StringVar(value="30")
        self.interval_entry = ttk.Entry(self.settings_frame, textvariable=self.interval_var, width=10)
        self.interval_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        # Mask coordinates
        ttk.Label(self.settings_frame, text="Mask (x1,y1,x2,y2):").grid(row=3, column=0, padx=5, pady=5)
        self.mask_var = tk.StringVar(value="0,0,100,100")
        self.mask_entry = ttk.Entry(self.settings_frame, textvariable=self.mask_var, width=20)
        self.mask_entry.grid(row=3, column=1, sticky="w", padx=5, pady=5)
        self.mask_btn = ttk.Button(self.settings_frame, text="Apply Mask", command=self._update_mask)
        self.mask_btn.grid(row=3, column=2, padx=5, pady=5)

        # Control frame
        self.control_frame = ttk.Frame(self.root)
        self.control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        # Control buttons
        self.start_btn = ttk.Button(self.control_frame, text="Start Camera", command=self._toggle_camera)
        self.start_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.exit_btn = ttk.Button(self.control_frame, text="Exit", command=self._exit_application)
        self.exit_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        # GPS Status
        self.gps_label = ttk.Label(self.control_frame, text="GPS: Not Connected")
        self.gps_label.pack(side=tk.LEFT, padx=20, pady=5)

        # Display frame
        self.display_frame = ttk.Frame(self.root)
        self.display_frame.pack(side=tk.TOP, expand=True, fill=tk.BOTH, padx=5, pady=5)

        # Display labels
        self.rgb_label = ttk.Label(self.display_frame)
        self.rgb_label.grid(row=1, column=0, padx=5, pady=5)
        
        self.depth_label = ttk.Label(self.display_frame)
        self.depth_label.grid(row=1, column=1, padx=5, pady=5)
        
        self.ir_label = ttk.Label(self.display_frame)
        self.ir_label.grid(row=2, column=0, columnspan=2, padx=5, pady=5)

        ttk.Label(self.display_frame, text="RGB Feed").grid(row=0, column=0)
        ttk.Label(self.display_frame, text="Depth Feed").grid(row=0, column=1)
        ttk.Label(self.display_frame, text="IR Feed").grid(row=2, column=0, columnspan=2)

    def set_callbacks(self,
                     start_callback: Callable = None,
                     stop_callback: Callable = None,
                     mask_callback: Callable = None,
                     directory_callback: Callable = None,
                     device_select_callback: Callable = None,
                     refresh_devices_callback: Callable = None,
                     gps_toggle_callback: Callable = None):
        """Set callback functions"""
        self.start_callback = start_callback
        self.stop_callback = stop_callback
        self.mask_callback = mask_callback
        self.directory_callback = directory_callback
        self.device_select_callback = device_select_callback
        self.refresh_devices_callback = refresh_devices_callback
        self.gps_toggle_callback = gps_toggle_callback

    def _on_device_selected(self, event=None):
        """Handle device selection"""
        if self.device_select_callback and self.device_var.get():
            selected_idx = self.device_combo.current()
            if 0 <= selected_idx < len(self.available_devices):
                self.device_select_callback(self.available_devices[selected_idx])

    def _refresh_devices(self):
        """Handle device refresh"""
        if self.refresh_devices_callback:
            self.available_devices = self.refresh_devices_callback()
            self._update_device_list()

    def _update_device_list(self):
        """Update the device dropdown list"""
        device_list = []
        for device in self.available_devices:
            # Create a readable device name
            device_name = f"OAK {device.getMxId()} ({device.state.name})"
            device_list.append(device_name)
        
        self.device_combo['values'] = device_list
        if device_list:
            self.device_combo.set(device_list[0])
            self._on_device_selected()

    def update_device_info(self, info: Dict):
        """Update device information display"""
        if info:
            info_text = f"Cameras: {', '.join(info['cameras'])} | USB: {info['usb_speed']}"
            self.device_info_label.config(text=info_text)
        else:
            self.device_info_label.config(text="No device selected")

    def _select_directory(self):
        """Handle directory selection"""
        dir_path = filedialog.askdirectory(initialdir=self.dir_var.get())
        if dir_path:
            self.dir_var.set(dir_path)
            if self.directory_callback:
                self.directory_callback(dir_path)

    def _update_mask(self):
        """Handle mask update"""
        try:
            coords = [int(x) for x in self.mask_var.get().split(',')]
            if len(coords) != 4:
                raise ValueError("Need exactly 4 coordinates")
            if self.mask_callback:
                self.mask_callback(coords)
        except Exception as e:
            messagebox.showerror("Error", f"Invalid mask coordinates: {str(e)}")

    def _toggle_camera(self):
        """Handle camera toggle"""
        if not self.running:
            try:
                if not self.device_var.get():
                    messagebox.showerror("Error", "Please select a device first")
                    return

                interval = int(self.interval_var.get())
                if interval < 1:
                    raise ValueError("Interval must be at least 1 second")
                
                if self.start_callback:
                    self.start_callback(interval)
                    
                self.running = True
                self.start_btn.config(text="Stop Camera")
                self._disable_settings()
                
            except ValueError as e:
                messagebox.showerror("Error", str(e))
        else:
            if self.stop_callback:
                self.stop_callback()
                
            self.running = False
            self.start_btn.config(text="Start Camera")
            self._enable_settings()

    def _disable_settings(self):
        """Disable settings while camera is running"""
        self.dir_entry.config(state='disabled')
        self.dir_btn.config(state='disabled')
        self.interval_entry.config(state='disabled')
        self.mask_entry.config(state='disabled')
        self.mask_btn.config(state='disabled')
        self.device_combo.config(state='disabled')
        self.refresh_btn.config(state='disabled')

    def _enable_settings(self):
        """Enable settings when camera is stopped"""
        self.dir_entry.config(state='normal')
        self.dir_btn.config(state='normal')
        self.interval_entry.config(state='normal')
        self.mask_entry.config(state='normal')
        self.mask_btn.config(state='normal')
        self.device_combo.config(state='readonly')
        self.refresh_btn.config(state='normal')
        
    def _toggle_gps(self):
        """Handle GPS toggle"""
        if self.gps_toggle_callback:
            self.gps_toggle_callback(self.gps_enabled.get())

    def set_gps_enabled(self, enabled: bool):
        """Set GPS toggle state"""
        self.gps_enabled.set(enabled)

    def show_error(self, title: str, message: str):
        """Show error message"""
        messagebox.showerror(title, message)
    
    def update_gps_status(self, coords: Dict[str, Any]):
        """Update GPS status display"""
        if coords:
            status = f"GPS: {coords['latitude']}°{coords['lat_dir']}, {coords['longitude']}°{coords['lon_dir']}"
            self.gps_label.config(text=status)
        else:
            self.gps_label.config(text="GPS: No Fix")

    def update_frames(self, frames: Dict[str, Any]):
        """Update camera feed displays"""
        if 'rgb' in frames:
            frame_rgb = cv2.cvtColor(frames['rgb'], cv2.COLOR_BGR2RGB)
            img_rgb = ImageTk.PhotoImage(Image.fromarray(frame_rgb))
            self.rgb_label.configure(image=img_rgb)
            self.rgb_label.image = img_rgb

        if 'depth' in frames:
            frame_depth = cv2.cvtColor(frames['depth'], cv2.COLOR_BGR2RGB)
            img_depth = ImageTk.PhotoImage(Image.fromarray(frame_depth))
            self.depth_label.configure(image=img_depth)
            self.depth_label.image = img_depth

        if 'ir' in frames:
            frame_ir = cv2.cvtColor(frames['ir'], cv2.COLOR_GRAY2RGB)
            img_ir = ImageTk.PhotoImage(Image.fromarray(frame_ir))
            self.ir_label.configure(image=img_ir)
            self.ir_label.image = img_ir

    def _exit_application(self):
        """Handle application exit"""
        if messagebox.askokcancel("Exit", "Are you sure you want to exit?"):
            if self.stop_callback:
                self.stop_callback()
            self.root.quit()

    def get_save_directory(self) -> str:
        """Get current save directory"""
        return self.dir_var.get()

    def get_save_interval(self) -> int:
        """Get current save interval"""
        try:
            return int(self.interval_var.get())
        except ValueError:
            return 30  # Default value