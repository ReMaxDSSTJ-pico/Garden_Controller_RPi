#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk
import datetime
import time
import os
import sys
import math

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
phase = "IDLE"

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
            lgpio.gpio_claim_output(h_chip, PUMP_1_PIN)
            lgpio.gpio_claim_output(h_chip, PUMP_2_PIN)
            lgpio.gpio_write(h_chip, PUMP_1_PIN, 0)
            lgpio.gpio_write(h_chip, PUMP_2_PIN, 0)
            print(f"Detected lgpio library (Raspberry Pi 5 mode)")
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
        except Exception as e:
            if "unknown handle" not in str(e).lower():
                print(f"Warning during lgpio cleanup: {e}")
    else:
        GPIO.cleanup()

# --- GUI Logic ---
class GardenApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Garden Controller - Pi 5")
        self.root.geometry("800x480")
        self.root.configure(bg="#f0f8ff")
        
        # Header
        header = tk.Frame(root, bg="#2E8B57", height=60)
        header.pack(fill=tk.X)
        tk.Label(header, text="🍅 Smart Tomato Garden", font=("Arial", 22, "bold"), bg="#2E8B57", fg="white").pack(pady=10)
        
        # Status Frame
        status_frame = tk.Frame(root, bg="white", pady=15)
        status_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.lbl_status = tk.Label(status_frame, text="Status: IDLE", font=("Arial", 16, "bold"), bg="white", fg="#333")
        self.lbl_status.pack()
        
        self.lbl_timer = tk.Label(status_frame, text="Time: --:--:--", font=("Arial", 14), bg="white", fg="#666")
        self.lbl_timer.pack()
        
        self.lbl_cycle = tk.Label(status_frame, text="Cycle: 0 / 4", font=("Arial", 14), bg="white", fg="#666")
        self.lbl_cycle.pack()
        
        # Animation Canvas
        self.canvas = tk.Canvas(root, width=800, height=220, bg="#87CEEB", highlightthickness=0)
        self.canvas.pack(pady=5)
        
        # Draw static background elements once
        self.draw_background()
        
        # Animation variables
        self.drops = []
        self.animating = False
        
        # Controls
        ctrl_frame = tk.Frame(root, bg="#f0f8ff")
        ctrl_frame.pack(pady=15)
        
        btn_style = {"font": ("Arial", 12, "bold"), "width": 14, "height": 2, "relief": tk.RAISED}
        
        tk.Button(ctrl_frame, text="START AUTO", command=self.start_auto, bg="#4CAF50", fg="white", **btn_style).grid(row=0, column=0, padx=10)
        tk.Button(ctrl_frame, text="STOP", command=self.stop_system, bg="#f44336", fg="white", **btn_style).grid(row=0, column=1, padx=10)
        tk.Button(ctrl_frame, text="MANUAL ON", command=lambda: set_pumps(True), bg="#2196F3", fg="white", **btn_style).grid(row=0, column=2, padx=10)
        tk.Button(ctrl_frame, text="MANUAL OFF", command=lambda: set_pumps(False), bg="#9E9E9E", fg="white", **btn_style).grid(row=0, column=3, padx=10)
        
        # Info
        self.lbl_info = tk.Label(root, text=f"Season: Every {get_seasonal_schedule()} days | Next: {calculate_next_run()}", font=("Arial", 10), bg="#f0f8ff", fg="#555")
        self.lbl_info.pack(side=tk.BOTTOM, pady=10)
        
        self.running = False
        
    def draw_background(self):
        self.canvas.delete("all")
        # Sky
        self.canvas.create_rectangle(0, 0, 800, 220, fill="#87CEEB", outline="")
        # Sun
        self.canvas.create_oval(700, 20, 760, 80, fill="#FFD700", outline="#FFA500", width=2)
        # Ground
        self.soil_id = self.canvas.create_rectangle(0, 180, 800, 220, fill="#8B4513", outline="")
        
        # Draw 3 Tomato Plants
        positions = [200, 400, 600]
        for x in positions:
            self.draw_tomato_plant(x, 180)

    def draw_tomato_plant(self, x, y):
        # Stake
        self.canvas.create_line(x, y-100, x, y, fill="#8B4513", width=4)
        self.canvas.create_line(x-2, y-100, x+2, y-100, fill="#8B4513", width=2) # Top bar
        
        # Main Stem
        self.canvas.create_line(x, y, x, y-90, fill="#228B22", width=6)
        
        # Leaves
        self.canvas.create_polygon(x-20, y-60, x-40, y-50, x-20, y-40, fill="#006400", outline="")
        self.canvas.create_polygon(x+20, y-70, x+45, y-60, x+20, y-50, fill="#006400", outline="")
        self.canvas.create_polygon(x-15, y-30, x-35, y-20, x-15, y-10, fill="#006400", outline="")
        self.canvas.create_polygon(x+25, y-40, x+50, y-30, x+25, y-20, fill="#006400", outline="")
        
        # Tomatoes (Red and Yellow)
        self.canvas.create_oval(x-15, y-55, x-5, y-45, fill="#FF4500", outline="#8B0000")
        self.canvas.create_oval(x+10, y-65, x+20, y-55, fill="#FFD700", outline="#DAA520")
        self.canvas.create_oval(x-10, y-25, x, y-15, fill="#FF0000", outline="#8B0000")
        self.canvas.create_oval(x+15, y-35, x+25, y-25, fill="#FF4500", outline="#8B0000")

    def create_drop(self):
        # Create drops above each plant
        positions = [200, 400, 600]
        for x in positions:
            # Randomize slightly
            offset = (time.time() * 100) % 50
            dx = x - 20 + (offset % 40)
            d = self.canvas.create_oval(dx, -10, dx+4, -6, fill="#00BFFF", outline="")
            self.drops.append({'id': d, 'x': dx, 'y': -10, 'speed': 3 + (hash(str(dx)) % 3)})

    def animate_water(self):
        if not self.animating:
            return
            
        # Move drops
        for drop in self.drops[:]:
            self.canvas.move(drop['id'], 0, drop['speed'])
            drop['y'] += drop['speed']
            
            # Reset if hits ground (y > 180)
            if drop['y'] > 180:
                self.canvas.coords(drop['id'], drop['x'], -10, drop['x']+4, -6)
                drop['y'] = -10
        
        # Schedule next frame
        self.root.after(30, self.animate_water)

    def start_watering_animation(self):
        if not self.animating:
            self.animating = True
            self.drops = []
            self.create_drop()
            self.animate_water()
            # Change soil color to wet
            self.canvas.itemconfig(self.soil_id, fill="#5D4037")

    def stop_watering_animation(self):
        self.animating = False
        self.canvas.delete("all")
        self.draw_background()

    def start_auto(self):
        global stop_requested, current_cycle, phase
        stop_requested = False
        current_cycle = 0
        phase = "STARTING"
        self.running = True
        self.run_cycle_loop()

    def stop_system(self):
        global stop_requested
        stop_requested = True
        set_pumps(False)
        self.stop_watering_animation()
        self.lbl_status.config(text="Status: STOPPED BY USER", fg="red")

    def run_cycle_loop(self):
        global current_cycle, phase, stop_requested
        if stop_requested or current_cycle >= TOTAL_CYCLES:
            self.running = False
            phase = "IDLE"
            self.stop_watering_animation()
            msg = "Status: CYCLE COMPLETE" if not stop_requested else "Status: STOPPED"
            self.lbl_status.config(text=msg, fg="green")
            return

        phase = "WATERING"
        self.lbl_status.config(text=f"Status: WATERING (Cycle {current_cycle+1}/{TOTAL_CYCLES})", fg="blue")
        set_pumps(True)
        self.start_watering_animation()
        
        duration_ms = CYCLE_ON_MIN * 60 * 1000
        self.root.after(duration_ms, self.wait_phase)

    def wait_phase(self):
        global current_cycle, phase, stop_requested
        if stop_requested: return
        
        set_pumps(False)
        self.stop_watering_animation()
        phase = "WAITING"
        self.lbl_status.config(text="Status: WAITING...", fg="orange")
        
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
