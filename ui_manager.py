import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import cv2
from typing import Callable, Dict, Any
import os

class UIManager:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("OAK-D Camera with GPS")
        
        # Callbacks
        self.start_callback = None
        self.stop_callback = None
        self.mask_callback = None
        self.directory_callback = None
        
        # State
        self.running = False
        
        # Create UI elements
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup all UI elements"""
        # Main frames
        self.settings_frame = ttk.LabelFrame(self.root, text="Settings")
        self.settings_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        self.control_frame = ttk.Frame(self.root)
        self.control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        self.display_frame = ttk.Frame(self.root)
        self.display_frame.pack(side=tk.TOP, expand=True, fill=tk.BOTH, padx=5, pady=5)
        
        # Settings
        # Directory selection
        ttk.Label(self.settings_frame, text="Save Directory:").grid(row=0, column=0, padx=5, pady=5)
        self.dir_var = tk.StringVar(value=os.path.join(os.getcwd(), "result"))
        self.dir_entry = ttk.Entry(self.settings_frame, textvariable=self.dir_var, width=50)
        self.dir_entry.grid(row=0, column=1, padx=5, pady=5)
        self.dir_btn = ttk.Button(self.settings_frame, text="Browse", command=self._select_directory)
        self.dir_btn.grid(row=0, column=2, padx=5, pady=5)

        # Interval setting
        ttk.Label(self.settings_frame, text="Save Interval (seconds):").grid(row=1, column=0, padx=5, pady=5)
        self.interval_var = tk.StringVar(value="30")
        self.interval_entry = ttk.Entry(self.settings_frame, textvariable=self.interval_var, width=10)
        self.interval_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        # Mask coordinates
        ttk.Label(self.settings_frame, text="Mask (x1,y1,x2,y2):").grid(row=2, column=0, padx=5, pady=5)
        self.mask_var = tk.StringVar(value="0,0,100,100")
        self.mask_entry = ttk.Entry(self.settings_frame, textvariable=self.mask_var, width=20)
        self.mask_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        self.mask_btn = ttk.Button(self.settings_frame, text="Apply Mask", command=self._update_mask)
        self.mask_btn.grid(row=2, column=2, padx=5, pady=5)

        # Control buttons
        self.start_btn = ttk.Button(self.control_frame, text="Start Camera", command=self._toggle_camera)
        self.start_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.exit_btn = ttk.Button(self.control_frame, text="Exit", command=self._exit_application)
        self.exit_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        # GPS Status
        self.gps_label = ttk.Label(self.control_frame, text="GPS: Not Connected")
        self.gps_label.pack(side=tk.LEFT, padx=20, pady=5)

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
                     directory_callback: Callable = None):
        """Set callback functions"""
        self.start_callback = start_callback
        self.stop_callback = stop_callback
        self.mask_callback = mask_callback
        self.directory_callback = directory_callback

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

    def _enable_settings(self):
        """Enable settings when camera is stopped"""
        self.dir_entry.config(state='normal')
        self.dir_btn.config(state='normal')
        self.interval_entry.config(state='normal')
        self.mask_entry.config(state='normal')
        self.mask_btn.config(state='normal')

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