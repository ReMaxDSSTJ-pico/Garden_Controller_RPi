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
DEFAULT_ON_TIMES = [60, 120, 180, 240]  # Default ON times in seconds (1, 2, 3, 4 mins)
OFF_TIME = 300  # Fixed OFF time (5 mins) before next cycle could start (if looping)

# Global State
stop_requested = False
current_cycle = 0
TOTAL_CYCLES = 1  # Run once through all zones simultaneously
relay_states = [False, False, False, False] # Track individual relay states
relay_on_durations = list(DEFAULT_ON_TIMES) # Editable durations in seconds

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
    """Set specific relay state"""
    pin = RELAY_PINS[index]
    val = 1 if state else 0
    relay_states[index] = state
    
    if USING_LGPIO:
        lgpio.gpio_write(h_chip, pin, val)
    else:
        GPIO.output(pin, val)

def all_relays_off():
    for i in range(len(RELAY_PINS)):
        set_relay(i, False)

def cleanup_gpio():
    global h_chip
    all_relays_off()
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
        tk.Label(header, text="🍅 4-Zone Tomato Garden", font=("Arial", 22, "bold"), 
                 bg="#2E8B57", fg="white").pack(pady=15)
        
        # Status Panel
        status_frame = tk.Frame(root, bg="white", pady=10, relief=tk.RAISED, bd=2)
        status_frame.pack(fill=tk.X, padx=20, pady=5)
        
        self.lbl_status = tk.Label(status_frame, text="Status: IDLE", font=("Arial", 16, "bold"), bg="white", fg="#333")
        self.lbl_status.pack()
        
        self.lbl_timer = tk.Label(status_frame, text="Time: --:--:--", font=("Arial", 14), bg="white", fg="#666")
        self.lbl_timer.pack()
        
        # Animation Canvas (Half height roughly)
        self.canvas_frame = tk.Frame(root, bg="#e0f7fa", relief=tk.SUNKEN, bd=2)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="#e0f7fa", highlightthickness=0, width=800, height=250)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.drops = [] # List of lists for 4 zones
        self.zone_graphics = [] # Store graphic IDs for plants
        
        # Initialize drops structure for 4 zones
        for _ in range(4):
            self.drops.append([])
            
        self.draw_scene()
        
        # Main Controls
        ctrl_frame = tk.Frame(root, bg="#f0f8ff")
        ctrl_frame.pack(pady=10)
        
        btn_style = {"font": ("Arial", 12, "bold"), "width": 14, "height": 2, "fg": "white"}
        
        tk.Button(ctrl_frame, text="START ALL ZONES", command=self.start_auto, bg="#4CAF50", **btn_style).grid(row=0, column=0, padx=10)
        tk.Button(ctrl_frame, text="STOP", command=self.stop_system, bg="#f44336", **btn_style).grid(row=0, column=1, padx=10)
        
        # Zone Configuration Panel
        zone_frame = tk.Frame(root, bg="#fff", relief=tk.GROOVE, bd=2)
        zone_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(zone_frame, text="Zone Configuration (ON Time)", font=("Arial", 14, "bold"), bg="#fff").pack(pady=5)
        
        self.zone_controls = []
        
        for i in range(4):
            z_frame = tk.Frame(zone_frame, bg="#f9f9f9", relief=tk.RIDGE, bd=1)
            z_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Zone Title & LED
            led_color = "#ccc"
            self.lbl_led = tk.Label(z_frame, text="●", font=("Arial", 16), bg="#f9f9f9", fg=led_color)
            self.lbl_led.pack()
            
            tk.Label(z_frame, text=f"Zone {i+1}", font=("Arial", 12, "bold"), bg="#f9f9f9").pack()
            
            # Time Display
            self.lbl_time = tk.Label(z_frame, text=f"{relay_on_durations[i]}s", font=("Arial", 14), bg="#f9f9f9", fg="#333")
            self.lbl_time.pack()
            
            # Buttons
            btn_small = {"font": ("Arial", 10), "width": 3}
            b_frame = tk.Frame(z_frame, bg="#f9f9f9")
            b_frame.pack(pady=5)
            
            tk.Button(b_frame, text="-", command=lambda idx=i: self.adjust_time(idx, -10), bg="#ddd", **btn_small).grid(row=0, column=0, padx=2)
            tk.Button(b_frame, text="+", command=lambda idx=i: self.adjust_time(idx, 10), bg="#ddd", **btn_small).grid(row=0, column=1, padx=2)
            
            self.zone_controls.append({
                'led': self.lbl_led,
                'time_lbl': self.lbl_time,
                'index': i
            })

        # Footer Info
        info_lbl = tk.Label(root, text=f"Season: Every {get_seasonal_schedule()} days | Next: {calculate_next_run()}", 
                          font=("Arial", 10), bg="#f0f8ff", fg="#555")
        info_lbl.pack(side=tk.BOTTOM, pady=5)
        
        self.running = False
        self.anim_job = None
        self.active_timers = [] # Store timer job IDs to cancel them individually

    def adjust_time(self, index, change):
        new_time = relay_on_durations[index] + change
        if 10 <= new_time <= 600: # Limit between 10s and 10 mins
            relay_on_durations[index] = new_time
            self.zone_controls[index]['time_lbl'].config(text=f"{new_time}s")

    def draw_scene(self):
        self.canvas.delete("all")
        for i in range(4):
            self.drops[i] = []
            
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10 or h < 10: 
            self.root.update_idletasks()
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
            if w < 10 or h < 10: return

        # Sky / Sun / Moon handled by update_sky method if needed, keeping simple for now
        # Draw Ground
        ground_y = h - 30
        self.canvas.create_rectangle(0, ground_y, w, h, fill="#8D6E63", outline="")
        
        # Divide into 4 zones visually
        zone_width = w // 4
        
        for i in range(4):
            cx = (i * zone_width) + (zone_width // 2)
            
            # Draw Plant
            # Stake
            self.canvas.create_line(cx, ground_y, cx, ground_y-80, fill="#8B4513", width=2)
            # Leaves
            self.canvas.create_oval(cx-15, ground_y-50, cx+15, ground_y-20, fill="#228B22", outline="")
            # Tomatoes
            self.canvas.create_oval(cx-8, ground_y-40, cx, ground_y-32, fill="#FF4444", outline="")
            self.canvas.create_oval(cx+4, ground_y-55, cx+12, ground_y-47, fill="#FF6666", outline="")
            
            # Zone Label
            self.canvas.create_text(cx, ground_y - 90, text=f"Zone {i+1}", font=("Arial", 10, "bold"), fill="#555")
            
            # Prepare Drop slots (50 drops per zone max)
            for j in range(50):
                dx = cx - 20 + (j % 10) * 4 # Spread across plant width
                dy = -10 - (j * 5) % 50
                speed = 3 + (j % 3)
                drop_id = self.canvas.create_line(dx, dy, dx, dy+12, fill="#00BFFF", width=3, capstyle=tk.ROUND, state='hidden')
                self.drops[i].append({'id': drop_id, 'x': dx, 'y': dy, 'speed': speed})

    def animate_water(self):
        h = self.canvas.winfo_height()
        
        for i in range(4):
            # Check if this specific zone is active
            if relay_states[i]:
                # Show and move drops for this zone
                for drop in self.drops[i]:
                    self.canvas.itemconfig(drop['id'], state='normal')
                    self.canvas.move(drop['id'], 0, drop['speed'])
                    drop['y'] += drop['speed']
                    
                    if drop['y'] > h - 30: # Reset if hits ground
                        drop['y'] = -10 - (hash(str(drop['id'])) % 50)
                        self.canvas.coords(drop['id'], drop['x'], drop['y'], drop['x'], drop['y']+12)
            else:
                # Hide drops for inactive zone
                for drop in self.drops[i]:
                    self.canvas.itemconfig(drop['id'], state='hidden')
        
        if self.running:
            self.anim_job = self.root.after(33, self.animate_water)

    def update_leds(self):
        for i in range(4):
            color = "#0f0" if relay_states[i] else "#ccc" # Green if ON, Grey if OFF
            self.zone_controls[i]['led'].config(fg=color)

    def turn_off_relay(self, index):
        if stop_requested: return
        set_relay(index, False)
        self.update_leds()
        print(f"Zone {index+1} turned OFF.")
        
        # Check if all are off to trigger next phase or end
        if not any(relay_states):
            self.lbl_status.config(text="Status: All Zones Complete", fg="green")
            self.running = False
            if self.anim_job:
                self.root.after_cancel(self.anim_job)

    def start_auto(self):
        global stop_requested, current_cycle
        stop_requested = False
        current_cycle = 0
        self.running = True
        self.lbl_status.config(text="Status: Watering Active", fg="blue")
        
        # Start all relays simultaneously
        for i in range(4):
            set_relay(i, True)
            
            # Schedule individual turn-off for each relay
            duration_ms = relay_on_durations[i] * 1000
            timer_id = self.root.after(duration_ms, lambda idx=i: self.turn_off_relay(idx))
            self.active_timers.append(timer_id)
        
        self.update_leds()
        self.animate_water()

    def stop_system(self):
        global stop_requested
        stop_requested = True
        self.running = False
        
        # Cancel all pending timers
        for timer_id in self.active_timers:
            self.root.after_cancel(timer_id)
        self.active_timers = []
        
        all_relays_off()
        self.update_leds()
        if self.anim_job:
            self.root.after_cancel(self.anim_job)
        self.draw_scene() # Clear drops
        self.lbl_status.config(text="Status: STOPPED BY USER", fg="red")

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
