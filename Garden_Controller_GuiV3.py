#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk
import datetime
import time
import os
import sys
import math

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
        print("Error: Neither lgpio nor RPi.GPIO found. Please install one.")
        sys.exit(1)

# --- Configuration ---
# GPIO Pins for 4 Relays
RELAY_PINS = [17, 27, 22, 23]  # Pin assignments for Relay 1, 2, 3, 4

# Default Times in seconds (ON, OFF)
# Relay 1: 1m ON, 5m OFF
# Relay 2: 2m ON, 3m OFF
# Relay 3: 3m ON, 2m OFF
# Relay 4: 4m ON, 1m OFF
DEFAULT_TIMES = [
    {'on': 60, 'off': 300},
    {'on': 120, 'off': 180},
    {'on': 180, 'off': 120},
    {'on': 240, 'off': 60}
]

relay_configs = []
for i, t in enumerate(DEFAULT_TIMES):
    relay_configs.append({
        'id': i+1,
        'on_sec': t['on'],
        'off_sec': t['off'],
        'active': False
    })

# Global State
stop_requested = False
current_cycle = 0
TOTAL_CYCLES = 4
phase = "IDLE"
animation_objects = []

def get_seasonal_schedule():
    month = datetime.datetime.now().month
    if month == 8: return 1
    elif month in [7, 9]: return 2
    else: return 3

def calculate_next_run():
    now = datetime.datetime.now()
    interval = get_seasonal_schedule()
    target = now.replace(hour=19, minute=0, second=0, microsecond=0)
    if now >= target:
        target += datetime.timedelta(days=1)
    days_since_epoch = (now - datetime.datetime(now.year, 1, 1)).days
    if days_since_epoch % interval != 0:
        target += datetime.timedelta(days=(interval - (days_since_epoch % interval)))
    return target.strftime("%Y-%m-%d %H:%M")

def setup_gpio():
    global h_chip
    if USING_LGPIO:
        try:
            h_chip = lgpio.gpiochip_open(0)
            for pin in RELAY_PINS:
                lgpio.gpio_claim_output(h_chip, pin)
                lgpio.gpio_write(h_chip, pin, 0)
        except Exception as e:
            print(f"Critical LGPIO Error: {e}")
            sys.exit(1)
    else:
        GPIO.setmode(GPIO.BCM)
        for pin in RELAY_PINS:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

def set_relay(index, state):
    """State: True=ON, False=OFF"""
    pin = RELAY_PINS[index]
    val = 1 if state else 0
    relay_configs[index]['active'] = state
    
    if USING_LGPIO:
        lgpio.gpio_write(h_chip, pin, val)
    else:
        GPIO.output(pin, val)

def set_all_relays(state):
    for i in range(len(RELAY_PINS)):
        set_relay(i, state)

def cleanup_gpio():
    global h_chip
    set_all_relays(False)
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
        self.root.title("Smart Garden Controller - 4 Zones")
        self.root.geometry("800x700")
        self.root.configure(bg="#f0f8ff")
        
        # Header
        header = tk.Frame(root, bg="#2E8B57", height=70)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="🍅 Multi-Zone Tomato Garden", font=("Arial", 22, "bold"), 
                 bg="#2E8B57", fg="white").pack(pady=15)
        
        # Status Panel
        status_frame = tk.Frame(root, bg="white", pady=10, relief=tk.RAISED, bd=2)
        status_frame.pack(fill=tk.X, padx=20, pady=5)
        
        self.lbl_status = tk.Label(status_frame, text="Status: IDLE", font=("Arial", 16, "bold"), bg="white", fg="#333")
        self.lbl_status.pack()
        
        self.lbl_timer = tk.Label(status_frame, text="Time: --:--:--", font=("Arial", 14), bg="white", fg="#666")
        self.lbl_timer.pack()
        
        self.lbl_cycle = tk.Label(status_frame, text="Cycle: 0 / 4", font=("Arial", 14), bg="white", fg="#666")
        self.lbl_cycle.pack()
        
        # Animation Canvas
        self.canvas_frame = tk.Frame(root, bg="#e0f7fa", relief=tk.SUNKEN, bd=2)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="#e0f7fa", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.drops = []
        self.anim_job = None
        self.draw_scene(False)
        
        # Main Controls
        ctrl_frame = tk.Frame(root, bg="#f0f8ff")
        ctrl_frame.pack(pady=10)
        
        btn_style = {"font": ("Arial", 12, "bold"), "width": 12, "height": 2, "fg": "white"}
        
        tk.Button(ctrl_frame, text="START AUTO", command=self.start_auto, bg="#4CAF50", **btn_style).grid(row=0, column=0, padx=5)
        tk.Button(ctrl_frame, text="STOP", command=self.stop_system, bg="#f44336", **btn_style).grid(row=0, column=1, padx=5)
        tk.Button(ctrl_frame, text="ALL ON", command=lambda: set_all_relays(True), bg="#2196F3", **btn_style).grid(row=0, column=2, padx=5)
        tk.Button(ctrl_frame, text="ALL OFF", command=lambda: set_all_relays(False), bg="#9E9E9E", **btn_style).grid(row=0, column=3, padx=5)
        
        # Relay Configuration Panel
        relay_frame = tk.Frame(root, bg="white", relief=tk.RIDGE, bd=2)
        relay_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(relay_frame, text="Zone Timing Configuration (Simultaneous Start)", font=("Arial", 12, "bold"), bg="white").pack(pady=5)
        
        # Grid for 4 relays
        grid_frame = tk.Frame(relay_frame, bg="white")
        grid_frame.pack(padx=10, pady=5)
        
        self.time_labels = []
        
        for i in range(4):
            row = i
            zone_name = f"Zone {i+1}"
            current_on = relay_configs[i]['on_sec']
            current_off = relay_configs[i]['off_sec']
            
            # Label
            lbl = tk.Label(grid_frame, text=f"{zone_name}: {current_on}s ON / {current_off}s OFF", 
                          font=("Arial", 11), bg="white", width=35, anchor='w')
            lbl.grid(row=row, column=0, padx=5, pady=2)
            self.time_labels.append(lbl)
            
            # Decrease Button
            btn_dec = tk.Button(grid_frame, text="-", width=3, 
                               command=lambda idx=i: self.adjust_time(idx, -10), bg="#FF9800", fg="white")
            btn_dec.grid(row=row, column=1, padx=2)
            
            # Increase Button
            btn_inc = tk.Button(grid_frame, text="+", width=3, 
                               command=lambda idx=i: self.adjust_time(idx, 10), bg="#4CAF50", fg="white")
            btn_inc.grid(row=row, column=2, padx=2)
            
            tk.Label(grid_frame, text="(10s steps)", font=("Arial", 9), bg="white", fg="#777").grid(row=row, column=3, padx=5)

        # Footer Info
        info_lbl = tk.Label(root, text=f"Season: Every {get_seasonal_schedule()} days | Next: {calculate_next_run()}", 
                          font=("Arial", 10), bg="#f0f8ff", fg="#555")
        info_lbl.pack(side=tk.BOTTOM, pady=5)
        
        self.running = False
        self.root.update_idletasks() # Ensure layout is calculated
        self.draw_scene(False)

    def adjust_time(self, index, delta):
        new_time = relay_configs[index]['on_sec'] + delta
        # Limit between 10s and 600s (10 mins)
        if new_time < 10: new_time = 10
        if new_time > 600: new_time = 600
        
        relay_configs[index]['on_sec'] = new_time
        off_time = relay_configs[index]['off_sec']
        
        self.time_labels[index].config(text=f"Zone {index+1}: {new_time}s ON / {off_time}s OFF")

    def draw_scene(self, watering):
        self.canvas.delete("all")
        self.drops = []
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10 or h < 10: return

        # Sky Color
        sky_color = "#87CEEB" if not watering else "#B0E0E6"
        self.canvas.create_rectangle(0, 0, w, h, fill=sky_color, outline="")
        
        # Draw Soil
        soil_color = "#5D4037" if watering else "#8D6E63"
        self.canvas.create_rectangle(0, h-40, w, h, fill=soil_color, outline="")
        
        # Draw 4 Tomato Plants (one per zone roughly)
        spacing = w // 5
        ground_y = h - 40
        
        for i in range(4):
            x = spacing * (i + 1)
            # Stake
            self.canvas.create_line(x, ground_y, x, ground_y-100, fill="#8B4513", width=3)
            # Leaves
            self.canvas.create_oval(x-15, ground_y-50, x+15, ground_y-15, fill="#228B22", outline="")
            # Tomatoes
            self.canvas.create_oval(x-8, ground_y-40, x, ground_y-32, fill="#FF4444", outline="#CC0000")
            self.canvas.create_oval(x+2, ground_y-60, x+10, ground_y-52, fill="#FF6666", outline="#CC0000")

        # Create 50 Water Drops
        if watering:
            for i in range(50):
                dx = (i * (w // 50)) % w
                dy = (i * 37) % h
                speed = 5 + (i % 5)
                drop = self.canvas.create_line(dx, dy, dx, dy+18, fill="#00BFFF", width=4, capstyle=tk.ROUND)
                self.drops.append({'id': drop, 'x': dx, 'y': dy, 'speed': speed})

    def animate_water(self):
        if not any(r['active'] for r in relay_configs):
            return
            
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        
        for drop in self.drops:
            self.canvas.move(drop['id'], 0, drop['speed'])
            drop['y'] += drop['speed']
            if drop['y'] > h:
                drop['y'] = -20
                self.canvas.coords(drop['id'], drop['x'], drop['y'], drop['x'], drop['y']+18)
        
        if any(r['active'] for r in relay_configs):
            self.anim_job = self.root.after(33, self.animate_water)

    def start_auto(self):
        global stop_requested, current_cycle, phase
        stop_requested = False
        current_cycle = 0
        phase = "STARTING"
        self.running = True
        self.lbl_status.config(text="Status: STARTING...", fg="blue")
        self.run_cycle_loop()

    def stop_system(self):
        global stop_requested
        stop_requested = True
        set_all_relays(False)
        if self.anim_job:
            self.root.after_cancel(self.anim_job)
        self.draw_scene(False)
        self.lbl_status.config(text="Status: STOPPED BY USER", fg="red")

    def run_cycle_loop(self):
        global current_cycle, phase, stop_requested
        
        if stop_requested or current_cycle >= TOTAL_CYCLES:
            self.running = False
            phase = "IDLE"
            set_all_relays(False)
            msg = "Status: CYCLE COMPLETE" if not stop_requested else "Status: STOPPED"
            self.lbl_status.config(text=msg, fg="green")
            self.draw_scene(False)
            return

        # Calculate Simultaneous Run Time
        # All relays start NOW. They turn off individually when their time is up.
        # The "Phase" ends when the LONGEST relay turns off.
        max_on_time = max(r['on_sec'] for r in relay_configs)
        # Find a common OFF time? Or just wait for the longest ON to finish, then wait for the shortest OFF?
        # Simplified Logic: All ON for Max(ON). Then ALL OFF for Min(OFF) to ensure at least one rests?
        # Better Logic for "Cycle": 
        # 1. Turn ALL ON.
        # 2. Wait for Max(ON_TIME). During this, some turn off earlier.
        # 3. Turn ALL OFF (ensure clean state).
        # 4. Wait for Min(OFF_TIME) or Max(OFF_TIME)? 
        # Let's use the Max(OFF_TIME) to ensure everyone has rested enough before next cycle.
        
        max_off_time = max(r['off_sec'] for r in relay_configs)
        
        phase = "WATERING"
        self.lbl_status.config(text=f"Status: WATERING (Cycle {current_cycle+1}/{TOTAL_CYCLES})", fg="blue")
        self.draw_scene(True)
        
        # Turn ALL on
        set_all_relays(True)
        self.animate_water()
        
        # Wait for the longest zone to finish
        duration_ms = max_on_time * 1000
        self.root.after(duration_ms, lambda: self.wait_phase(max_off_time))

    def wait_phase(self, wait_time_sec):
        global current_cycle, phase, stop_requested
        if stop_requested: return
        
        set_all_relays(False) # Ensure all are off
        if self.anim_job: self.root.after_cancel(self.anim_job)
        
        phase = "WAITING"
        self.lbl_status.config(text=f"Status: WAITING ({wait_time_sec}s)...", fg="orange")
        self.draw_scene(False)
        
        duration_ms = wait_time_sec * 1000
        self.root.after(duration_ms, self.next_cycle)

    def next_cycle(self):
        global current_cycle
        if not stop_requested:
            current_cycle += 1
            self.lbl_cycle.config(text=f"Cycle: {current_cycle} / {TOTAL_CYCLES}")
            self.run_cycle_loop()

    def update_clock(self):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.lbl_timer.config(text=f"Time: {now}")
        self.root.after(1000, self.update_clock)

if __name__ == "__main__":
    setup_gpio()
    root = tk.Tk()
    app = GardenApp(root)
    app.update_clock()
    
    def on_close():
        cleanup_gpio()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
