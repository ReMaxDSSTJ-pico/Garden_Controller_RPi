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
        print("Error: Neither lgpio nor RPi.GPIO found.")
        sys.exit(1)

# --- Configuration ---
# GPIO Pins for 4 Relays
PINS = [17, 27, 22, 23]  # Relay 1, 2, 3, 4

# Default ON times in seconds
DEFAULT_ON_TIMES = [60, 120, 180, 240]  # 1m, 2m, 3m, 4m

# Fixed OFF times in seconds
OFF_TIMES = [240, 180, 120, 60]  # 5m, 3m, 2m, 1m

# Global State
relay_states = [False] * 4  # Current physical state of relays
stop_requested = False
current_cycle = 0
TOTAL_CYCLES = 4
phase = "IDLE"

# Mutable ON times (seconds)
on_times = DEFAULT_ON_TIMES.copy()

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
            for pin in PINS:
                lgpio.gpio_claim_output(h_chip, pin)
                lgpio.gpio_write(h_chip, pin, 0)
        except Exception as e:
            print(f"Critical LGPIO Error: {e}")
            sys.exit(1)
    else:
        GPIO.setmode(GPIO.BCM)
        for pin in PINS:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

def set_relay(index, state):
    """Set specific relay state (True=ON, False=OFF)"""
    val = 1 if state else 0
    if USING_LGPIO:
        lgpio.gpio_write(h_chip, PINS[index], val)
    else:
        GPIO.output(PINS[index], val)
    relay_states[index] = state

def set_all_relays(state):
    for i in range(4):
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
        self.root.geometry("800x800")
        self.root.configure(bg="#f0f8ff")
        
        # Header
        header = tk.Frame(root, bg="#2E8B57", height=70)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="🍅 Multi-Zone Garden Controller", font=("Arial", 22, "bold"), 
                 bg="#2E8B57", fg="white").pack(pady=15)
        
        # Status Panel
        status_frame = tk.Frame(root, bg="white", pady=10, relief=tk.RAISED, bd=2)
        status_frame.pack(fill=tk.X, padx=20, pady=10)
        
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
        self.soil_rect = None
        self.relay_indicators = []
        
        # Force layout update before drawing
        self.root.update_idletasks()
        self.draw_scene(False)
        
        # Relay Control Panels
        control_frame = tk.Frame(root, bg="#f0f8ff")
        control_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Create 4 columns for 4 relays
        self.relay_labels = []
        for i in range(4):
            frame = tk.Frame(control_frame, bg="white", relief=tk.RIDGE, bd=2)
            frame.grid(row=0, column=i, padx=5, sticky="nsew")
            control_frame.columnconfigure(i, weight=1)
            
            lbl = tk.Label(frame, text=f"Zone {i+1}\nON: {on_times[i]}s\nOFF: {OFF_TIMES[i]//60}m", 
                          font=("Arial", 10), bg="white", fg="#333")
            lbl.pack(pady=5)
            self.relay_labels.append(lbl)
            
            # +/- Buttons
            btn_frame = tk.Frame(frame, bg="white")
            btn_frame.pack(pady=5)
            
            tk.Button(btn_frame, text="-", width=3, command=lambda idx=i: self.adjust_time(idx, -10), bg="#ffcccb").pack(side=tk.LEFT, padx=2)
            tk.Button(btn_frame, text="+", width=3, command=lambda idx=i: self.adjust_time(idx, 10), bg="#ccffcc").pack(side=tk.LEFT, padx=2)

        # Main Controls
        main_ctrl_frame = tk.Frame(root, bg="#f0f8ff")
        main_ctrl_frame.pack(pady=15)
        
        btn_style = {"font": ("Arial", 12, "bold"), "width": 14, "height": 2, "fg": "white"}
        
        tk.Button(main_ctrl_frame, text="START AUTO", command=self.start_auto, bg="#4CAF50", **btn_style).grid(row=0, column=0, padx=10)
        tk.Button(main_ctrl_frame, text="STOP", command=self.stop_system, bg="#f44336", **btn_style).grid(row=0, column=1, padx=10)
        tk.Button(main_ctrl_frame, text="ALL ON", command=lambda: set_all_relays(True), bg="#2196F3", **btn_style).grid(row=0, column=2, padx=10)
        tk.Button(main_ctrl_frame, text="ALL OFF", command=lambda: set_all_relays(False), bg="#9E9E9E", **btn_style).grid(row=0, column=3, padx=10)
        
        # Footer Info
        info_lbl = tk.Label(root, text=f"Season: Every {get_seasonal_schedule()} days | Next: {calculate_next_run()}", 
                          font=("Arial", 10), bg="#f0f8ff", fg="#555")
        info_lbl.pack(side=tk.BOTTOM, pady=5)
        
        self.running = False
        self.anim_job = None
        self.cycle_jobs = []

    def adjust_time(self, idx, delta):
        """Adjust ON time for specific relay"""
        new_time = on_times[idx] + delta
        if new_time < 10: new_time = 10  # Min 10 seconds
        if new_time > 600: new_time = 600 # Max 10 minutes
        on_times[idx] = new_time
        
        # Update label
        off_min = OFF_TIMES[idx] // 60
        self.relay_labels[idx].config(text=f"Zone {idx+1}\nON: {new_time}s\nOFF: {off_min}m")

    def draw_scene(self, watering):
        self.canvas.delete("all")
        self.drops = []
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10 or h < 10: return

        # Sky Gradient (Simple Blue)
        self.canvas.create_rectangle(0, 0, w, h, fill="#87CEEB", outline="")
        
        # Soil
        soil_color = "#5D4037" if watering else "#8D6E63"
        self.soil_rect = self.canvas.create_rectangle(0, h-50, w, h, fill=soil_color, outline="")
        
        # Draw 4 Plants corresponding to zones
        spacing = w // 5
        for i in range(4):
            x = spacing * (i + 1)
            ground_y = h - 50
            
            # Pot
            self.canvas.create_rectangle(x-25, ground_y-30, x+25, ground_y, fill="#8B4513", outline="#5D4037")
            
            # Plant Stem
            self.canvas.create_line(x, ground_y-30, x, ground_y-80, fill="#228B22", width=3)
            
            # Leaves
            self.canvas.create_oval(x-20, ground_y-70, x, ground_y-40, fill="#32CD32", outline="")
            self.canvas.create_oval(x, ground_y-80, x+20, ground_y-50, fill="#32CD32", outline="")
            
            # Fruit (Tomato)
            color = "#FF4444" if watering else "#FF6347"
            self.canvas.create_oval(x-10, ground_y-65, x+10, ground_y-45, fill=color, outline="#CC0000")
            
            # Zone Label
            self.canvas.create_text(x, ground_y-95, text=f"Z{i+1}", font=("Arial", 10, "bold"), fill="#333")

        # Water Drops (50 drops)
        if watering:
            for i in range(50):
                dx = (i * (w // 50)) % w
                dy = (i * 37) % (h//2) # Only in sky area
                speed = 5 + (i % 5)
                drop = self.canvas.create_line(dx, dy, dx, dy+12, fill="#00BFFF", width=3, capstyle=tk.ROUND)
                self.drops.append({'id': drop, 'x': dx, 'y': dy, 'speed': speed})

    def animate_water(self):
        if not any(relay_states):
            return
            
        h = self.canvas.winfo_height()
        
        if self.soil_rect:
            self.canvas.itemconfig(self.soil_rect, fill="#5D4037")

        for drop in self.drops:
            self.canvas.move(drop['id'], 0, drop['speed'])
            drop['y'] += drop['speed']
            if drop['y'] > h:
                drop['y'] = -20
                self.canvas.coords(drop['id'], drop['x'], drop['y'], drop['x'], drop['y']+12)
        
        if any(relay_states):
            self.anim_job = self.root.after(33, self.animate_water)

    def start_auto(self):
        global stop_requested, current_cycle, phase
        stop_requested = False
        current_cycle = 0
        phase = "STARTING"
        self.running = True
        self.lbl_status.config(text="Status: STARTING SEQUENCE...", fg="blue")
        self.run_cycle_loop()

    def stop_system(self):
        global stop_requested
        stop_requested = True
        # Cancel all pending jobs
        for job in self.cycle_jobs:
            self.root.after_cancel(job)
        self.cycle_jobs = []
        
        set_all_relays(False)
        if self.anim_job:
            self.root.after_cancel(self.anim_job)
        self.draw_scene(False)
        self.lbl_status.config(text="Status: STOPPED BY USER", fg="red")
        for lbl in self.relay_labels:
            lbl.config(bg="white")

    def run_cycle_loop(self):
        global current_cycle, phase, stop_requested
        if stop_requested or current_cycle >= TOTAL_CYCLES:
            self.running = False
            phase = "IDLE"
            set_all_relays(False)
            msg = "Status: ALL CYCLES COMPLETE" if not stop_requested else "Status: STOPPED"
            self.lbl_status.config(text=msg, fg="green")
            self.draw_scene(False)
            return

        phase = "RUNNING CYCLE"
        self.lbl_status.config(text=f"Status: Cycle {current_cycle+1}/{TOTAL_CYCLES}", fg="blue")
        self.lbl_cycle.config(text=f"Cycle: {current_cycle+1} / {TOTAL_CYCLES}")
        
        # Start sequential relay logic
        self.run_relay_sequence(0)

    def run_relay_sequence(self, relay_idx):
        if stop_requested or current_cycle >= TOTAL_CYCLES:
            return

        if relay_idx >= 4:
            # All relays done for this cycle, wait a bit then next cycle
            job = self.root.after(2000, self.next_cycle)
            self.cycle_jobs.append(job)
            return

        # Turn ON this relay
        set_relay(relay_idx, True)
        self.relay_labels[relay_idx].config(bg="#90EE90") # Light green indicator
        self.draw_scene(True)
        self.animate_water()
        
        duration_ms = on_times[relay_idx] * 1000
        
        # Schedule OFF
        job_off = self.root.after(duration_ms, lambda idx=relay_idx: self.turn_off_relay(idx))
        self.cycle_jobs.append(job_off)

    def turn_off_relay(self, idx):
        if stop_requested: return
        
        set_relay(idx, False)
        self.relay_labels[idx].config(bg="white")
        
        # Check if all off to stop animation
        if not any(relay_states):
            if self.anim_job:
                self.root.after_cancel(self.anim_job)
            self.draw_scene(False)
        
        # Schedule next relay or finish
        next_idx = idx + 1
        if next_idx < 4:
            # Wait OFF time before starting next relay? 
            # Requirement says: Relay 1 ON 1m, OFF 5m. 
            # Interpretation: The cycle for Relay 1 is 1m ON + 5m OFF.
            # But we are running them sequentially in one "Garden Cycle".
            # Let's make them sequential: Relay 1 runs (ON+OFF), then Relay 2 runs.
            
            wait_time = OFF_TIMES[idx] * 1000
            job_wait = self.root.after(wait_time, lambda: self.run_relay_sequence(next_idx))
            self.cycle_jobs.append(job_wait)
        else:
            # All relays finished their individual cycles
            job_next = self.root.after(1000, self.next_cycle)
            self.cycle_jobs.append(job_next)

    def next_cycle(self):
        global current_cycle
        if not stop_requested:
            current_cycle += 1
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
