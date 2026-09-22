#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk
import datetime
import time
import os
import sys

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
PUMP_1_PIN = 17
PUMP_2_PIN = 27
CYCLE_ON_MIN = 5
CYCLE_OFF_MIN = 5
TOTAL_CYCLES = 4

# Global State
pump_active = False
stop_requested = False
current_cycle = 0
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
            lgpio.gpio_claim_output(h_chip, PUMP_1_PIN)
            lgpio.gpio_claim_output(h_chip, PUMP_2_PIN)
            lgpio.gpio_write(h_chip, PUMP_1_PIN, 0)
            lgpio.gpio_write(h_chip, PUMP_2_PIN, 0)
        except Exception as e:
            print(f"Critical LGPIO Error: {e}")
            sys.exit(1)
    else:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PUMP_1_PIN, GPIO.OUT)
        GPIO.setup(PUMP_2_PIN, GPIO.OUT)
        GPIO.output(PUMP_1_PIN, GPIO.LOW)
        GPIO.output(PUMP_2_PIN, GPIO.LOW)

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
                print(f"Cleanup Warning: {e}")
    else:
        GPIO.cleanup()

# --- GUI Application ---
class GardenApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Garden Controller - Pi 5")
        self.root.geometry("800x640")
        self.root.configure(bg="#f0f8ff")
        
        # Header
        header = tk.Frame(root, bg="#2E8B57", height=70)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="🍅 Automatic Tomato Garden", font=("Arial", 22, "bold"), 
                 bg="#2E8B57", fg="white").pack(pady=15)
        
        # Status Panel
        status_frame = tk.Frame(root, bg="white", pady=15, relief=tk.RAISED, bd=2)
        status_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.lbl_status = tk.Label(status_frame, text="Status: IDLE", font=("Arial", 16, "bold"), bg="white", fg="#333")
        self.lbl_status.pack()
        
        self.lbl_timer = tk.Label(status_frame, text="Time: --:--:--", font=("Arial", 14), bg="white", fg="#666")
        self.lbl_timer.pack()
        
        self.lbl_cycle = tk.Label(status_frame, text="Cycle: 0 / 4", font=("Arial", 14), bg="white", fg="#666")
        self.lbl_cycle.pack()
        
        # Animation Canvas
        self.canvas_frame = tk.Frame(root, bg="#e0f7fa", relief=tk.SUNKEN, bd=2)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="#e0f7fa", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # FIX: Force window to update layout so canvas has correct size before drawing
        self.root.update_idletasks() 
        
        self.drops = []
        self.tomato_plants = []
        self.soil_rect = None
        
        # Draw initial scene (Idle state)
        self.draw_scene(False)
        
        # Controls
        ctrl_frame = tk.Frame(root, bg="#f0f8ff")
        ctrl_frame.pack(pady=20)
        
        btn_style = {"font": ("Arial", 12, "bold"), "width": 14, "height": 2, "fg": "white"}
        
        tk.Button(ctrl_frame, text="START AUTO", command=self.start_auto, bg="#4CAF50", **btn_style).grid(row=0, column=0, padx=10)
        tk.Button(ctrl_frame, text="STOP", command=self.stop_system, bg="#f44336", **btn_style).grid(row=0, column=1, padx=10)
        tk.Button(ctrl_frame, text="MANUAL ON", command=lambda: set_pumps(True), bg="#2196F3", **btn_style).grid(row=0, column=2, padx=10)
        tk.Button(ctrl_frame, text="MANUAL OFF", command=lambda: set_pumps(False), bg="#9E9E9E", **btn_style).grid(row=0, column=3, padx=10)
        
        # Footer Info
        info_lbl = tk.Label(root, text=f"Season: Every {get_seasonal_schedule()} days | Next: {calculate_next_run()}", 
                          font=("Arial", 10), bg="#f0f8ff", fg="#555")
        info_lbl.pack(side=tk.BOTTOM, pady=5)
        
        self.running = False
        self.anim_job = None

    def draw_scene(self, watering):
        self.canvas.delete("all")
        self.drops = []
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        
        # If size is still invalid, try again later
        if w < 10 or h < 10: 
            self.root.after(100, lambda: self.draw_scene(watering))
            return

        # Draw Soil
        soil_color = "#5D4037" if watering else "#8D6E63"
        self.soil_rect = self.canvas.create_rectangle(0, h-40, w, h, fill=soil_color, outline="")
        
        # Draw 3 Tomato Plants
        plant_positions = [w//4, w//2, 3*w//4]
        ground_y = h - 40
        
        for x in plant_positions:
            # Stake
            self.canvas.create_line(x, ground_y, x, ground_y-120, fill="#8B4513", width=3)
            # Leaves
            self.canvas.create_oval(x-20, ground_y-60, x+20, ground_y-20, fill="#228B22", outline="")
            self.canvas.create_oval(x-15, ground_y-90, x+15, ground_y-50, fill="#2E8B57", outline="")
            # Tomatoes (Red circles)
            self.canvas.create_oval(x-10, ground_y-50, x, ground_y-40, fill="#FF4444", outline="#CC0000")
            self.canvas.create_oval(x+5, ground_y-70, x+15, ground_y-60, fill="#FF6666", outline="#CC0000")
            self.canvas.create_oval(x-15, ground_y-80, x-5, ground_y-70, fill="#FF4444", outline="#CC0000")

        # Create 50 Large Water Drops (only if watering)
        if watering:
            for i in range(50):
                dx = (i * (w // 50)) % w
                dy = (i * 37) % h # Staggered start
                speed = 5 + (i % 5) # Varied speed
                drop = self.canvas.create_line(dx, dy, dx, dy+18, fill="#00BFFF", width=4, capstyle=tk.ROUND)
                self.drops.append({'id': drop, 'x': dx, 'y': dy, 'speed': speed})

    def animate_water(self):
        if not pump_active:
            return
            
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        
        # Update Soil Color dynamically
        if self.soil_rect:
            self.canvas.itemconfig(self.soil_rect, fill="#5D4037")

        for drop in self.drops:
            self.canvas.move(drop['id'], 0, drop['speed'])
            drop['y'] += drop['speed']
            
            # Reset drop if it hits bottom
            if drop['y'] > h:
                drop['y'] = -20
                self.canvas.coords(drop['id'], drop['x'], drop['y'], drop['x'], drop['y']+18)
        
        # Schedule next frame (approx 30 FPS)
        if pump_active:
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
        set_pumps(False)
        if self.anim_job:
            self.root.after_cancel(self.anim_job)
        self.draw_scene(False)
        self.lbl_status.config(text="Status: STOPPED BY USER", fg="red")

    def run_cycle_loop(self):
        global current_cycle, phase, stop_requested
        if stop_requested or current_cycle >= TOTAL_CYCLES:
            self.running = False
            phase = "IDLE"
            set_pumps(False)
            msg = "Status: CYCLE COMPLETE" if not stop_requested else "Status: STOPPED"
            self.lbl_status.config(text=msg, fg="green")
            self.draw_scene(False)
            return

        # Watering Phase
        phase = "WATERING"
        self.lbl_status.config(text=f"Status: WATERING (Cycle {current_cycle+1}/{TOTAL_CYCLES})", fg="blue")
        self.draw_scene(True)
        set_pumps(True)
        self.animate_water()
        
        duration_ms = CYCLE_ON_MIN * 60 * 1000
        self.root.after(duration_ms, self.wait_phase)

    def wait_phase(self):
        global current_cycle, phase, stop_requested
        if stop_requested: return
        
        set_pumps(False)
        if self.anim_job: self.root.after_cancel(self.anim_job)
        
        phase = "WAITING"
        self.lbl_status.config(text="Status: WAITING...", fg="orange")
        self.draw_scene(False)
        
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
