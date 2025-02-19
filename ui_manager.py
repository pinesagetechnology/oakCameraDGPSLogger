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
        self.root.title("OAK-D Camera with GPS V1.1")
        
        # Set minimum window size (width x height)
        self.root.minsize(1024, 768)
        
        # Set initial window size if not fullscreen
        self.root.geometry("1280x960")
        
        # Make window resizable
        self.root.resizable(True, True)
        
        # Bind Escape key to toggle fullscreen
        self.root.bind('<Escape>', self._toggle_fullscreen)
        
        # Create main container
        self.main_container = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # Set minimum width for left menu
        self.left_menu = ttk.Frame(self.main_container, width=250)
        self.left_menu.pack_propagate(False)  # Prevent frame from shrinking
        self.main_container.add(self.left_menu, weight=0)
        
        # Create right content frame with minimum width
        self.right_content = ttk.Frame(self.main_container)
        self.main_container.add(self.right_content, weight=1)
        
        # Initialize fullscreen state
        self.is_fullscreen = True
        
        # Callbacks
        self.start_callback = None
        self.stop_callback = None
        self.mask_callback = None
        self.directory_callback = None
        self.device_select_callback = None
        self.refresh_devices_callback = None
        self.gps_toggle_callback = None
        self._manual_capture_callback = None
        
        # State
        self.running = False
        self.available_devices = []
        
        # Create UI elements
        self.setup_ui()
        
        # Bind manual capture key
        self.root.bind('c', lambda e: self._manual_capture_callback() if self._manual_capture_callback else None)
        self.root.bind('C', lambda e: self._manual_capture_callback() if self._manual_capture_callback else None)
            
    def setup_ui(self):
        """Setup all UI elements"""
        self._setup_left_menu()
        self._setup_right_content()
        
    def _setup_left_menu(self):
        """Setup left menu components"""
        # Style configuration
        style = ttk.Style()
        style.configure('LeftMenu.TLabelframe', padding=5)
        
        # Device Selection Frame
        self.device_frame = ttk.LabelFrame(self.left_menu, text="Device Selection", style='LeftMenu.TLabelframe')
        self.device_frame.pack(fill=tk.X, padx=5, pady=2)
        
        # Device dropdown
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(
            self.device_frame, 
            textvariable=self.device_var,
            state='readonly',
            width=30
        )
        self.device_combo.pack(fill=tk.X, padx=5, pady=2)
        self.device_combo.bind('<<ComboboxSelected>>', self._on_device_selected)
        
        # Refresh button
        self.refresh_btn = ttk.Button(
            self.device_frame,
            text="Refresh Devices",
            command=self._refresh_devices
        )
        self.refresh_btn.pack(fill=tk.X, padx=5, pady=2)
        
        # Device info label
        self.device_info_label = ttk.Label(
            self.device_frame, 
            text="No device selected",
            wraplength=240
        )
        self.device_info_label.pack(fill=tk.X, padx=5, pady=2)

        # Settings Frame
        self.settings_frame = ttk.LabelFrame(self.left_menu, text="Settings", style='LeftMenu.TLabelframe')
        self.settings_frame.pack(fill=tk.X, padx=5, pady=2)
        
        # GPS Settings
        self.gps_enabled = tk.BooleanVar(value=True)
        self.gps_toggle = ttk.Checkbutton(
            self.settings_frame,
            text="Enable GPS",
            variable=self.gps_enabled,
            command=self._toggle_gps
        )
        self.gps_toggle.pack(fill=tk.X, padx=5, pady=2)
        
        # Save Directory
        ttk.Label(self.settings_frame, text="Save Directory:").pack(fill=tk.X, padx=5, pady=(2,0))
        self.dir_var = tk.StringVar(value=os.path.join(os.getcwd(), "result"))
        self.dir_entry = ttk.Entry(self.settings_frame, textvariable=self.dir_var)
        self.dir_entry.pack(fill=tk.X, padx=5, pady=2)
        self.dir_btn = ttk.Button(self.settings_frame, text="Browse", command=self._select_directory)
        self.dir_btn.pack(fill=tk.X, padx=5, pady=2)

        # Video Save Directory
        ttk.Label(self.settings_frame, text="Video Save Directory:").pack(fill=tk.X, padx=5, pady=(2,0))
        self.video_dir_var = tk.StringVar(value=os.path.join(os.getcwd(), "videos"))
        self.video_dir_entry = ttk.Entry(self.settings_frame, textvariable=self.video_dir_var)
        self.video_dir_entry.pack(fill=tk.X, padx=5, pady=2)
        self.video_dir_btn = ttk.Button(self.settings_frame, text="Browse Video Path", command=self._select_video_directory)
        self.video_dir_btn.pack(fill=tk.X, padx=5, pady=2)

        # Interval Settings Frame
        interval_frame = ttk.LabelFrame(self.settings_frame, text="Interval Settings")
        interval_frame.pack(fill=tk.X, padx=5, pady=2)
        self.interval_type = tk.StringVar(value="time")
        ttk.Radiobutton(
            interval_frame,
            text="Time-based",
            variable=self.interval_type,
            value="time",
            command=self._update_interval_label
        ).pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Radiobutton(
            interval_frame,
            text="Distance-based",
            variable=self.interval_type,
            value="distance",
            command=self._update_interval_label
        ).pack(fill=tk.X, padx=5, pady=2)

        # Interval Value
        self.interval_label = ttk.Label(interval_frame, text="Interval (seconds):")
        self.interval_label.pack(fill=tk.X, padx=5, pady=(2,0))
        
        self.interval_var = tk.StringVar(value="30")
        self.interval_entry = ttk.Entry(interval_frame, textvariable=self.interval_var)
        self.interval_entry.pack(fill=tk.X, padx=5, pady=2)


        # Mask coordinates
        ttk.Label(self.settings_frame, text="Mask (x1,y1,x2,y2):").pack(fill=tk.X, padx=5, pady=(2,0))
        self.mask_var = tk.StringVar(value="0,0,100,100")
        self.mask_entry = ttk.Entry(self.settings_frame, textvariable=self.mask_var)
        self.mask_entry.pack(fill=tk.X, padx=5, pady=2)
        self.mask_btn = ttk.Button(self.settings_frame, text="Apply Mask", command=self._update_mask)
        self.mask_btn.pack(fill=tk.X, padx=5, pady=2)

        # Control Buttons Frame
        self.control_frame = ttk.LabelFrame(self.left_menu, text="Controls", style='LeftMenu.TLabelframe')
        self.control_frame.pack(fill=tk.X, padx=5, pady=2)
        
        # Start/Stop Button
        self.control_btn = ttk.Button(
            self.control_frame,
            text="Start Camera",
            command=self._toggle_camera_and_recording
        )
        self.control_btn.pack(fill=tk.X, padx=5, pady=2)

        # Manual Capture Button
        self.capture_btn = ttk.Button(
            self.control_frame,
            text="Manual Capture (C)",
            command=lambda: self._manual_capture_callback() if self._manual_capture_callback else None
        )
        self.capture_btn.pack(fill=tk.X, padx=5, pady=2)

        # Status Frame
        self.status_frame = ttk.LabelFrame(self.left_menu, text="Status", style='LeftMenu.TLabelframe')
        self.status_frame.pack(fill=tk.X, padx=5, pady=2)

        # GPS Status
        self.gps_label = ttk.Label(
            self.status_frame, 
            text="GPS: Not Connected",
            wraplength=240
        )
        self.gps_label.pack(fill=tk.X, padx=5, pady=2)

        # Motion Status
        self.motion_label = ttk.Label(
            self.status_frame,
            text="Motion Status: Unknown",
            wraplength=250
        )
        self.motion_label.pack(fill=tk.X, pady=5)

        # Exit Button
        self.exit_btn = ttk.Button(
            self.control_frame, 
            text="Exit", 
            command=self._exit_application
        )
        self.exit_btn.pack(fill=tk.X, padx=5, pady=2)

    def _update_interval_label(self):
        """Update interval label based on selected type"""
        if self.interval_type.get() == "time":
            self.interval_label.config(text="Interval (seconds):")
        else:
            self.interval_label.config(text="Interval (meters):")
    
    def get_interval_settings(self):
        """Get current interval settings"""
        return {
            'type': self.interval_type.get(),
            'value': float(self.interval_var.get())
        }

    def _setup_right_content(self):
        """Setup right content with camera feeds in a compact layout"""
        # Camera Feeds Container
        self.feeds_container = ttk.Frame(self.right_content)
        self.feeds_container.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
        
        # Configure grid with 2 columns
        self.feeds_container.grid_columnconfigure((0, 1), weight=1, uniform="col")
        self.feeds_container.grid_rowconfigure((0, 1), weight=1, uniform="row")
        
        # Create camera feed labels with new grid layout
        self.rgb_label = ttk.Label(self.feeds_container)
        self.rgb_label.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=2, pady=2)
        
        self.depth_label = ttk.Label(self.feeds_container)
        self.depth_label.grid(row=1, column=0, sticky="nsew", padx=2, pady=2)
        
        self.ir_label = ttk.Label(self.feeds_container)
        self.ir_label.grid(row=1, column=1, sticky="nsew", padx=2, pady=2)

    def update_frames(self, frames: Dict[str, Any]):
        """Update camera feed displays with balanced scaling"""
        container_width = self.feeds_container.winfo_width() - 10
        container_height = (self.feeds_container.winfo_height() - 10) // 2  # Divide by 2 rows
        
        if 'rgb' in frames:
            frame_rgb = cv2.cvtColor(frames['rgb'], cv2.COLOR_BGR2RGB)
            # RGB gets full width
            img_rgb = self._resize_frame_balanced(frame_rgb, container_width, container_height)
            self.rgb_label.configure(image=img_rgb)
            self.rgb_label.image = img_rgb

        if 'depth' in frames:
            frame_depth = cv2.cvtColor(frames['depth'], cv2.COLOR_BGR2RGB)
            # Depth gets half width
            img_depth = self._resize_frame_balanced(frame_depth, container_width // 2, container_height)
            self.depth_label.configure(image=img_depth)
            self.depth_label.image = img_depth

        if 'ir' in frames:
            frame_ir = cv2.cvtColor(frames['ir'], cv2.COLOR_GRAY2RGB)
            # IR gets half width
            img_ir = self._resize_frame_balanced(frame_ir, container_width // 2, container_height)
            self.ir_label.configure(image=img_ir)
            self.ir_label.image = img_ir

    def _resize_frame_balanced(self, frame, target_width, target_height):
        """Resize frame to fit target dimensions while maintaining aspect ratio"""
        height, width = frame.shape[:2]
        width_scale = target_width / width
        height_scale = target_height / height
        scale = min(width_scale, height_scale) * 0.95  # Use 95% of available space
        
        new_width = int(width * scale)
        new_height = int(height * scale)
        
        frame = cv2.resize(frame, (new_width, new_height))
        return ImageTk.PhotoImage(Image.fromarray(frame))
    
    def _resize_frame_compact(self, frame, target_width, target_height):
        """Resize frame to fit target dimensions while maintaining aspect ratio"""
        height, width = frame.shape[:2]
        width_scale = target_width / width
        height_scale = target_height / height
        scale = min(width_scale, height_scale) * 0.9  # Use 90% of available space
        
        new_width = int(width * scale)
        new_height = int(height * scale)
        
        frame = cv2.resize(frame, (new_width, new_height))
        return ImageTk.PhotoImage(Image.fromarray(frame))
    
    def _toggle_fullscreen(self, event=None):
        """Toggle fullscreen mode while maintaining minimum size"""
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes('-fullscreen', self.is_fullscreen)
        
        if not self.is_fullscreen:
            # When exiting fullscreen, ensure window has good default size
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            
            # Set window size to 75% of screen size or minimum size, whichever is larger
            default_width = max(int(screen_width * 0.75), 1024)
            default_height = max(int(screen_height * 0.75), 768)
            
            # Calculate position to center the window
            x = (screen_width - default_width) // 2
            y = (screen_height - default_height) // 2
            
            # Set size and position
            self.root.geometry(f"{default_width}x{default_height}+{x}+{y}")
            
        return "break"  # Prevent the event from propagating
        
    def show_capture_notification(self, message: str):
        """Show temporary capture notification"""
        if hasattr(self, 'notification_label'):
            self.notification_label.destroy()
            
        self.notification_label = ttk.Label(
            self.status_frame,
            text=message,
            foreground='green'
        )
        self.notification_label.pack(fill=tk.X, padx=5, pady=2)
    
        # Schedule notification removal after 2 seconds
        self.root.after(2000, lambda: self.notification_label.destroy() if hasattr(self, 'notification_label') else None)

    def update_motion_status(self, is_moving: bool):
        """Update motion status display"""
        status = "Moving" if is_moving else "Stopped"
        color = "green" if is_moving else "red"
        self.motion_label.config(
            text=f"Motion Status: {status}",
            foreground=color
        )
        
    def set_callbacks(self,
                    start_callback: Callable = None,
                    stop_callback: Callable = None,
                    mask_callback: Callable = None,
                    directory_callback: Callable = None,
                    device_select_callback: Callable = None,
                    refresh_devices_callback: Callable = None,
                    gps_toggle_callback: Callable = None,
                    video_callback: Callable = None): 
        """Set callback functions"""
        self.start_callback = start_callback
        self.stop_callback = stop_callback
        self.mask_callback = mask_callback
        self.directory_callback = directory_callback
        self.device_select_callback = device_select_callback
        self.refresh_devices_callback = refresh_devices_callback
        self.gps_toggle_callback = gps_toggle_callback
        self.video_callback = video_callback  

    def set_manual_capture_callback(self, callback: Callable):
        """Set callback for manual capture"""
        self._manual_capture_callback = callback
    
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
        device_list = [f"OAK {device.getMxId()} ({device.state.name})" 
                    for device in self.available_devices]
        
        self.device_combo['values'] = device_list
        if device_list:
            self.device_combo.set(device_list[0])
            self._on_device_selected()

    def update_device_info(self, info: Dict):
        """Update device information display"""
        if info:
            info_text = f"Cameras: {', '.join(info['cameras'])}"
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

    def _disable_settings(self):
        """Disable settings while camera is running"""
        self.dir_entry.config(state='disabled')
        self.dir_btn.config(state='disabled')
        self.interval_entry.config(state='disabled')
        # self.mask_entry.config(state='disabled')
        # self.mask_btn.config(state='disabled')
        self.device_combo.config(state='disabled')
        self.refresh_btn.config(state='disabled')

    def _enable_settings(self):
        """Enable settings when camera is stopped"""
        self.dir_entry.config(state='normal')
        self.dir_btn.config(state='normal')
        self.interval_entry.config(state='normal')
        # self.mask_entry.config(state='normal')
        # self.mask_btn.config(state='normal')
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

    def _select_video_directory(self):
        """Handle video directory selection"""
        dir_path = filedialog.askdirectory(initialdir=self.video_dir_var.get())
        if dir_path:
            self.video_dir_var.set(dir_path)
            # Create directory if it doesn't exist
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)

    def _toggle_camera_and_recording(self):
        """Handle camera and recording toggle"""
        if not self.running:
            try:
                if not self.device_var.get():
                    messagebox.showerror("Error", "Please select a device first")
                    return

                # Show recording options dialog
                self.recording_dlg = tk.Toplevel(self.root)
                self.recording_dlg.title("Recording Options")
                self.recording_dlg.geometry("300x200")
                
                # Recording type
                type_frame = ttk.LabelFrame(self.recording_dlg, text="Recording Type")
                type_frame.pack(fill=tk.X, padx=5, pady=5)
                
                record_type = tk.StringVar(value="interval")
                ttk.Radiobutton(
                    type_frame, 
                    text="Interval-based", 
                    variable=record_type, 
                    value="interval"
                ).pack(fill=tk.X, padx=5, pady=2)
                
                ttk.Radiobutton(
                    type_frame, 
                    text="Continuous", 
                    variable=record_type, 
                    value="continuous"
                ).pack(fill=tk.X, padx=5, pady=2)
                
                # Video option
                video_var = tk.BooleanVar(value=True)  # Default to true
                ttk.Checkbutton(
                    self.recording_dlg,
                    text="Include Video Recording",
                    variable=video_var
                ).pack(fill=tk.X, padx=5, pady=5)
                
                # Get interval settings
                interval_settings = self.get_interval_settings()
                if interval_settings['value'] < 1:
                    raise ValueError("Interval must be at least 1 second")

                def start_camera_and_recording():
                    if self.start_callback:
                        self.start_callback(interval_settings)
                    if self.video_callback:
                        self.video_callback(
                            record_type.get(),
                            video_var.get()
                        )
                    self.running = True
                    self.control_btn.config(text="Stop Camera")
                    self._disable_settings()
                    self.recording_dlg.destroy()
                    
                # Buttons
                btn_frame = ttk.Frame(self.recording_dlg)
                btn_frame.pack(fill=tk.X, padx=5, pady=5)
                
                ttk.Button(
                    btn_frame,
                    text="Start",
                    command=start_camera_and_recording
                ).pack(side=tk.LEFT, padx=5)
                
                ttk.Button(
                    btn_frame,
                    text="Cancel",
                    command=self.recording_dlg.destroy
                ).pack(side=tk.LEFT, padx=5)
                
                self.recording_dlg.protocol("WM_DELETE_WINDOW", lambda: [self.recording_dlg.destroy(), delattr(self, 'recording_dlg')])
            except ValueError as e:
                messagebox.showerror("Error", str(e))
        else:
            if self.stop_callback:
                self.stop_callback()
                
            self.running = False
            self.control_btn.config(text="Start Camera")
            self._enable_settings()