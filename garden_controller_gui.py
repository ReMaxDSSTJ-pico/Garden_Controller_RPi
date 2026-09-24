#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk
import datetime
import time
import os
import sys
import random

# Try to import PIL for image handling
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Warning: PIL (Pillow) not found. Install with: sudo apt install python3-pil")

# --- GPIO Library Detection (Pi 5 vs Pi 3/4) ---
USING_LGPIO = False
h_chip = None

try:
    import lgpio
    USING_LGPIO = True
    print("Detected lgpio library (Raspberry Pi 5 mode)")
except ImportError:
    try:
        import RPi.GPIO as GPIO
        USING_LGPIO = False
        print("Detected RPi.GPIO library (Pi 3/4 mode)")
    except ImportError:
        print("Error: Neither lgpio nor RPi.GPIO found.")
        sys.exit(1)

# --- Configuration ---
RELAY_PINS = [17, 27, 22, 23]  # GPIO pins for Relays 1-4
DEFAULT_ON_TIMES = [60, 120, 180, 240]  # Default ON times in seconds
OFF_TIMES = [300, 180, 120, 60]  # Fixed OFF times in seconds
NUM_ZONES = 4

# Global State
stop_requested = False
zone_active = [False] * NUM_ZONES
zone_on_times = DEFAULT_ON_TIMES.copy()

def setup_gpio():
    global h_chip
    if USING_LGPIO:
        try:
            h_chip = lgpio.gpiochip_open(0)
            for pin in RELAY_PINS:
                lgpio.gpio_claim_output(h_chip, pin)
                lgpio.gpio_write(h_chip, pin, 1)
        except Exception as e:
            print(f"Critical LGPIO Error: {e}")
            sys.exit(1)
    else:
        GPIO.setmode(GPIO.BCM)
        for pin in RELAY_PINS:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH)

def set_relay(zone_idx, state):
    pin = RELAY_PINS[zone_idx]
    val = 0 if state else 1
    if USING_LGPIO:
        lgpio.gpio_write(h_chip, pin, val)
    else:
        GPIO.output(pin, val)
    zone_active[zone_idx] = state

def cleanup_gpio():
    global h_chip
    for i in range(NUM_ZONES):
        set_relay(i, False)
    if USING_LGPIO:
        try:
            if h_chip is not None:
                lgpio.gpiochip_close(h_chip)
        except Exception as e:
            if "unknown handle" not in str(e).lower():
                print(f"Cleanup Warning: {e}")
    else:
        GPIO.cleanup()

# --- GUI Application ---
class GardenApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Tomato Garden Controller")
        self.root.geometry("800x700")
        self.root.configure(bg="#f0f8ff")
        
        # Header
        header = tk.Frame(root, bg="#2E8B57", height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        # Using Unicode escape for compatibility
        tk.Label(header, text="\U0001F345 Smart Tomato Garden", font=("Arial", 20, "bold"), 
                 bg="#2E8B57", fg="white").pack(pady=10)
        
        # Status Panel
        status_frame = tk.Frame(root, bg="white", pady=10, relief=tk.RAISED, bd=2)
        status_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.lbl_status = tk.Label(status_frame, text="Status: IDLE", font=("Arial", 16, "bold"), bg="white", fg="#333")
        self.lbl_status.pack()
        
        self.lbl_timer = tk.Label(status_frame, text="Time: --:--:--", font=("Arial", 14), bg="white", fg="#666")
        self.lbl_timer.pack()
        
        # Animation Canvas
        self.canvas_frame = tk.Frame(root, bg="#e0f7fa", relief=tk.SUNKEN, bd=2)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        self.canvas = tk.Canvas(self.canvas_frame, bg="gray20", highlightthickness=0, width=800, height=250)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.zone_drops = [[] for _ in range(NUM_ZONES)]
        self.bg_image_id = None
        
        # Load and Draw Background Image
        self.load_background_image()
        
        # Controls
        ctrl_frame = tk.Frame(root, bg="#f0f8ff")
        ctrl_frame.pack(pady=10)
        
        btn_style = {"font": ("Arial", 11, "bold"), "width": 12, "height": 1, "fg": "white"}
        
        tk.Button(ctrl_frame, text="START ALL", command=self.start_all, bg="#4CAF50", **btn_style).grid(row=0, column=0, padx=5)
        tk.Button(ctrl_frame, text="STOP", command=self.stop_system, bg="#f44336", **btn_style).grid(row=0, column=1, padx=5)
        
        # Zone Control Panels
        zones_frame = tk.Frame(root, bg="#f0f8ff")
        zones_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.zone_leds = []
        self.time_labels = []
        
        for i in range(NUM_ZONES):
            z_frame = tk.Frame(zones_frame, bg="white", relief=tk.RIDGE, bd=2, padx=10, pady=5)
            z_frame.grid(row=0, column=i, sticky="nsew", padx=5)
            zones_frame.grid_columnconfigure(i, weight=1)
            
            tk.Label(z_frame, text=f"Zone {i+1}", font=("Arial", 12, "bold"), bg="white").pack()
            
            led = tk.Label(z_frame, text="\u25CF", font=("Arial", 16), bg="white", fg="#ccc") # Bullet character
            led.pack()
            self.zone_leds.append(led)
            
            time_lbl = tk.Label(z_frame, text=f"{zone_on_times[i]}s ON", font=("Arial", 10), bg="white")
            time_lbl.pack()
            self.time_labels.append(time_lbl)
            
            btn_frame = tk.Frame(z_frame, bg="white")
            btn_frame.pack()
            
            tk.Button(btn_frame, text="-", command=lambda idx=i: self.adjust_time(idx, -10), width=3, bg="#FF9800", fg="white").grid(row=0, column=0, padx=2)
            tk.Button(btn_frame, text="+", command=lambda idx=i: self.adjust_time(idx, 10), width=3, bg="#2196F3", fg="white").grid(row=0, column=1, padx=2)
            
            info = tk.Label(z_frame, text=f"Off: {OFF_TIMES[i]}s", font=("Arial", 9), bg="white", fg="#666")
            info.pack()

        # Footer
        info_lbl = tk.Label(root, text="Relays start together, stop individually based on time.", font=("Arial", 9), bg="#f0f8ff", fg="#555")
        info_lbl.pack(side=tk.BOTTOM, pady=5)
        
        self.running = False

    def load_background_image(self):
        self.canvas.delete("all")
        w, h = 760, 250
        
# 1. Get the absolute path to the directory this controller.py file lives in
        SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Safely join that path with your image filename
        image_path = os.path.join(SCRIPT_DIR, "TomatoGarden.jpg")        
        
        if HAS_PIL and os.path.exists(image_path):
            try:
                img = Image.open(image_path)
                # Resize to fit canvas while maintaining aspect ratio or stretching to fill
                img_resized = img.resize((w, h), Image.Resampling.LANCZOS)
                self.photo = ImageTk.PhotoImage(img_resized)
                self.bg_image_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
                print(f"Loaded image: {image_path}")
            except Exception as e:
                print(f"Error loading image: {e}")
                self.draw_fallback_background()
        else:
            print(f"Image not found: {image_path}. Ensure you downloaded it to /home/spiderman/workspace/")
            self.draw_fallback_background()

    def draw_fallback_background(self):
        """Draws a simple blue/brown background if image fails"""
        self.canvas.create_rectangle(0, 0, 800, 180, fill="#87CEEB", outline="")
        self.canvas.create_rectangle(0, 180, 800, 250, fill="#5D4037", outline="")
        self.canvas.create_text(400, 125, text="Image Not Found", font=("Arial", 20), fill="white")
        self.canvas.create_text(400, 150, text="Download TomatoGarden.jpg", font=("Arial", 12), fill="white")

    def init_water_drops(self):
        """Initialize 10 drops per zone based on approximate plant positions"""
        # Assuming 4 zones evenly spaced across 800px width
        # Zones centers approx: 100, 300, 500, 700
        zone_centers = [100, 300, 500, 700]
        ground_y = 240 # Approximate ground level based on standard image
        
        for i in range(NUM_ZONES):
            self.zone_drops[i] = []
            center_x = zone_centers[i]
            
            for j in range(10):
                dx = center_x - 20 + (j * 4)
                dy = -20 - (j * 10)
                # Create drop but hide initially
                drop = self.canvas.create_line(dx, dy, dx, dy+12, fill="#00BFFF", width=3, capstyle=tk.ROUND, state='hidden')
                self.zone_drops[i].append({'id': drop, 'x': dx, 'y': dy, 'speed': 4 + (j % 3)})

    def animate_zone(self, zone_idx):
        if not zone_active[zone_idx]:
            return

        for drop_data in self.zone_drops[zone_idx]:
            self.canvas.itemconfig(drop_data['id'], state='normal')
            self.canvas.move(drop_data['id'], 0, drop_data['speed'])
            drop_data['y'] += drop_data['speed']
            
            # Reset if hits ground (approx y=220)
            if drop_data['y'] > 220:
                drop_data['y'] = -20 - random.randint(0, 20)
                # Keep X within the zone area roughly
                base_x = [100, 300, 500, 700][zone_idx]
                drop_data['x'] = base_x - 20 + random.randint(0, 40)
                self.canvas.coords(drop_data['id'], drop_data['x'], drop_data['y'], drop_data['x'], drop_data['y']+12)
        
        if zone_active[zone_idx]:
            self.root.after(50, lambda: self.animate_zone(zone_idx))

    def update_led(self, idx, state):
        color = "#00FF00" if state else "#cccccc"
        self.zone_leds[idx].config(fg=color)

    def adjust_time(self, idx, delta):
        new_time = zone_on_times[idx] + delta
        if 10 <= new_time <= 600:
            zone_on_times[idx] = new_time
            self.time_labels[idx].config(text=f"{new_time}s ON")

    def start_all(self):
        global stop_requested
        stop_requested = False
        self.lbl_status.config(text="Status: WATERING ALL ZONES", fg="blue")
        
        # Initialize drops if not already done (in case image loaded late)
        if not self.zone_drops[0]:
            self.init_water_drops()

        # Start all relays
        for i in range(NUM_ZONES):
            set_relay(i, True)
            self.update_led(i, True)
            self.animate_zone(i)
        
        # Schedule individual turn-offs
        for i in range(NUM_ZONES):
            delay_ms = zone_on_times[i] * 1000
            self.root.after(delay_ms, lambda idx=i: self.stop_zone(idx))

    def stop_zone(self, idx):
        if stop_requested: return
        set_relay(idx, False)
        self.update_led(idx, False)
        for drop_data in self.zone_drops[idx]:
            self.canvas.itemconfig(drop_data['id'], state='hidden')
        
        if not any(zone_active):
            self.lbl_status.config(text="Status: CYCLE COMPLETE", fg="green")

    def stop_system(self):
        global stop_requested
        stop_requested = True
        for i in range(NUM_ZONES):
            set_relay(i, False)
            self.update_led(i, False)
            for drop_data in self.zone_drops[i]:
                self.canvas.itemconfig(drop_data['id'], state='hidden')
        self.lbl_status.config(text="Status: STOPPED BY USER", fg="red")

    def update_clock(self):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.lbl_timer.config(text=f"Time: {now}")
        self.root.after(1000, self.update_clock)

if __name__ == "__main__":
    setup_gpio()
    root = tk.Tk()
    app = GardenApp(root)
    
    # Initialize drops after UI is ready
    app.init_water_drops()
    
    app.update_clock()
    
    def on_close():
        cleanup_gpio()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
