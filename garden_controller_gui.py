#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk
import datetime
import time
import os
import sys

# Try to import lgpio (Pi 5), fallback to RPi.GPIO (Pi 3/4)
try:
    import lgpio
    USING_LGPIO = True
except ImportError:
    try:
        import RPi.GPIO as GPIO
        USING_LGPIO = False
    except ImportError:
        print("Error: Neither lgpio nor RPi.GPIO found.")
        sys.exit(1)

# --- Configuration ---
PUMP_1_PIN = 17
PUMP_2_PIN = 27
CYCLE_ON_MIN = 5
CYCLE_OFF_MIN = 5
TOTAL_CYCLES = 4

# Global variables
h_chip = None
pump_active = False
stop_requested = False
current_cycle = 0
phase = "IDLE"  # IDLE, WATERING, WAITING
next_run_time = None

def get_seasonal_schedule():
    """Returns days interval based on month"""
    month = datetime.datetime.now().month
    if month == 8: return 1  # August: Daily
    elif month in [7, 9]: return 2  # July, Sept: Every 2 days
    else: return 3  # Others: Every 3 days

def calculate_next_run():
    """Calculate next run time based on seasonal rules"""
    now = datetime.datetime.now()
    interval = get_seasonal_schedule()
    
    # Find next 19:00 that matches interval logic
    # Simplified: Just add 'interval' days to today at 19:00 if passed
    target = now.replace(hour=19, minute=0, second=0, microsecond=0)
    if now >= target:
        target += datetime.timedelta(days=1)
    
    # Adjust for interval (simple modulo logic for demo)
    days_since_epoch = (now - datetime.datetime(now.year, 1, 1)).days
    if days_since_epoch % interval != 0:
        # Skip to next valid day
        target += datetime.timedelta(days=(interval - (days_since_epoch % interval)))
        
    return target.strftime("%Y-%m-%d %H:%M")

def setup_gpio():
    global h_chip
    if USING_LGPIO:
        try:
            h_chip = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_output(h_chip, PUMP_1_PIN)
            lgpio.gpio_claim_output(h_chip, PUMP_2_PIN)
            lgpio.gpio_write(h_chip, PUMP_1_PIN, 0)
            lgpio.gpio_write(h_chip, PUMP_2_PIN, 0)
            print(f"Detected lgpio library (Raspberry Pi 5 mode)")
            print(f"lgpio initialized on chip 0. Pins {PUMP_1_PIN}, {PUMP_2_PIN} set to LOW.")
        except Exception as e:
            print(f"Critical LGPIO Error: {e}")
            sys.exit(1)
    else:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PUMP_1_PIN, GPIO.OUT)
        GPIO.setup(PUMP_2_PIN, GPIO.OUT)
        GPIO.output(PUMP_1_PIN, GPIO.LOW)
        GPIO.output(PUMP_2_PIN, GPIO.LOW)
        print("Detected RPi.GPIO library (Pi 3/4 mode)")

def set_pumps(state):
    """State: True=ON, False=OFF"""
    global pump_active
    pump_active = state
    val = 1 if state else 0
    
    if USING_LGPIO:
        lgpio.gpio_write(h_chip, PUMP_1_PIN, val)
        lgpio.gpio_write(h_chip, PUMP_2_PIN, val)
    else:
        GPIO.output(PUMP_1_PIN, val)
        GPIO.output(PUMP_2_PIN, val)

def cleanup_gpio():
    global h_chip
    set_pumps(False)
    if USING_LGPIO:
        try:
            if h_chip is not None:
                lgpio.gpiochip_close(h_chip)
                print("lgpio cleanup complete.")
        except Exception as e:
            # Ignore 'unknown handle' errors on close
            if "unknown handle" not in str(e).lower():
                print(f"Warning during lgpio cleanup: {e}")
    else:
        GPIO.cleanup()
        print("RPi.GPIO cleanup complete.")

# --- GUI Logic ---
class GardenApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Garden Controller - Pi 5 Edition")
        self.root.geometry("800x480")
        self.root.configure(bg="#f0f8ff")
        
        # Header
        header = tk.Frame(root, bg="#2E8B57", height=60)
        header.pack(fill=tk.X)
        tk.Label(header, text="🌱 Automatic Garden System", font=("Arial", 20, "bold"), bg="#2E8B57", fg="white").pack(pady=10)
        
        # Status Frame
        status_frame = tk.Frame(root, bg="white", pady=20)
        status_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.lbl_status = tk.Label(status_frame, text="Status: IDLE", font=("Arial", 16, "bold"), bg="white", fg="#333")
        self.lbl_status.pack()
        
        self.lbl_timer = tk.Label(status_frame, text="Next Action: --:--", font=("Arial", 14), bg="white", fg="#666")
        self.lbl_timer.pack()
        
        self.lbl_cycle = tk.Label(status_frame, text="Cycle: 0 / 4", font=("Arial", 14), bg="white", fg="#666")
        self.lbl_cycle.pack()
        
        # Animation Canvas
        self.canvas = tk.Canvas(root, width=800, height=200, bg="#e0f7fa", highlightthickness=0)
        self.canvas.pack(pady=10)
        self.draw_scene(False)
        
        # Controls
        ctrl_frame = tk.Frame(root, bg="#f0f8ff")
        ctrl_frame.pack(pady=20)
        
        tk.Button(ctrl_frame, text="START AUTO", command=self.start_auto, bg="#4CAF50", fg="white", font=("Arial", 12, "bold"), width=15, height=2).grid(row=0, column=0, padx=10)
        tk.Button(ctrl_frame, text="STOP", command=self.stop_system, bg="#f44336", fg="white", font=("Arial", 12, "bold"), width=15, height=2).grid(row=0, column=1, padx=10)
        tk.Button(ctrl_frame, text="MANUAL ON", command=lambda: set_pumps(True), bg="#2196F3", fg="white", font=("Arial", 12), width=12).grid(row=0, column=2, padx=10)
        tk.Button(ctrl_frame, text="MANUAL OFF", command=lambda: set_pumps(False), bg="#9E9E9E", fg="white", font=("Arial", 12), width=12).grid(row=0, column=3, padx=10)
        
        # Info
        info_lbl = tk.Label(root, text=f"Season Rule: Every {get_seasonal_schedule()} days | Next: {calculate_next_run()}", font=("Arial", 10), bg="#f0f8ff", fg="#555")
        info_lbl.pack(side=tk.BOTTOM, pady=10)
        
        self.running = False
        self.thread = None
        
    def draw_scene(self, watering):
        self.canvas.delete("all")
        # Pot
        self.canvas.create_rectangle(350, 150, 450, 190, fill="#8B4513", outline="")
        # Plant
        self.canvas.create_oval(360, 100, 440, 150, fill="#228B22", outline="")
        
        if watering:
            # Rain drops
            for i in range(0, 800, 50):
                self.canvas.create_line(i, 0, i, 40, fill="#00BFFF", width=2)
            self.canvas.create_text(400, 20, text="💧 WATERING 💧", font=("Arial", 20, "bold"), fill="#0066cc")
        else:
            self.canvas.create_text(400, 20, text="☀️ System Ready", font=("Arial", 20), fill="#555")

    def start_auto(self):
        global stop_requested, current_cycle, phase
        stop_requested = False
        current_cycle = 0
        phase = "STARTING"
        self.running = True
        self.run_cycle_loop()

    def stop_system(self):
        global stop_requested, pump_active
        stop_requested = True
        set_pumps(False)
        self.lbl_status.config(text="Status: STOPPED BY USER", fg="red")
        self.draw_scene(False)

    def run_cycle_loop(self):
        global current_cycle, phase, stop_requested
        if stop_requested or current_cycle >= TOTAL_CYCLES:
            self.running = False
            phase = "IDLE"
            self.lbl_status.config(text="Status: CYCLE COMPLETE" if not stop_requested else "Status: STOPPED", fg="green")
            self.draw_scene(False)
            return

        # Watering Phase
        phase = "WATERING"
        self.lbl_status.config(text=f"Status: WATERING (Cycle {current_cycle+1}/{TOTAL_CYCLES})", fg="blue")
        self.draw_scene(True)
        set_pumps(True)
        
        # Wait ON time (using after for non-blocking GUI)
        duration_ms = CYCLE_ON_MIN * 60 * 1000
        self.root.after(duration_ms, self.wait_phase)

    def wait_phase(self):
        global current_cycle, phase, stop_requested
        if stop_requested: return
        
        set_pumps(False)
        phase = "WAITING"
        self.lbl_status.config(text="Status: WAITING...", fg="orange")
        self.draw_scene(False)
        
        # Wait OFF time
        duration_ms = CYCLE_OFF_MIN * 60 * 1000
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
