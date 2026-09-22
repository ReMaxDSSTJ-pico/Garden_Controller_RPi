#!/usr/bin/env python3
import tkinter as tk
import datetime
import math
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

# --- Celestial Calculation Helpers ---
def get_moon_phase_name(day, month, year):
    # Simple approximation for moon phase name
    c = e = jd = b = 0
    if month < 3:
        year -= 1
        month += 12
    c = 365.25 * year
    e = 30.6 * month
    jd = c + e + day - 694039.09
    jd /= 29.5305882
    b = int(jd)
    jd -= b
    b = round(jd * 8)
    
    phases = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
              "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"]
    if b >= 8: b = 0
    return phases[b]

def get_sun_position(hour, minute):
    # Calculate sun angle (0° at 6am, 180° at 12pm, 360° at 6pm)
    # Returns (x_ratio, y_ratio, is_night)
    time_dec = hour + minute / 60.0
    
    if 6.0 <= time_dec <= 18.0:
        # Daytime
        progress = (time_dec - 6.0) / 12.0 # 0.0 to 1.0
        angle = progress * math.pi # 0 to PI
        x = 0.1 + 0.8 * progress # 10% to 90% width
        y = 0.1 + 0.4 * math.sin(angle) # Arc height
        return x, y, False
    else:
        # Nightime (Sun below horizon)
        return -1, -1, True

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
        
        self.lbl_moon = tk.Label(status_frame, text="", font=("Arial", 10), bg="white", fg="#555")
        self.lbl_moon.pack()
        
        # Animation Canvas
        self.canvas_frame = tk.Frame(root, bg="#87CEEB", relief=tk.SUNKEN, bd=2)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="#87CEEB", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.drops = []
        self.sky_objects = {} # Store sun/moon IDs
        
        # Force layout update before drawing
        self.root.update_idletasks()
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
        self.info_lbl = tk.Label(root, text=f"Season: Every {get_seasonal_schedule()} days | Next: {calculate_next_run()}", 
                          font=("Arial", 10), bg="#f0f8ff", fg="#555")
        self.info_lbl.pack(side=tk.BOTTOM, pady=5)
        
        self.running = False
        self.anim_job = None
        
        # Start celestial update loop
        self.update_celestial()

    def draw_scene(self, watering):
        self.canvas.delete("all")
        self.drops = []
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10 or h < 10: return

        # Sky Background (Dynamic handled in update_celestial, default here)
        self.canvas.configure(bg="#87CEEB")

        # Draw Soil
        soil_color = "#5D4037" if watering else "#8D6E63"
        self.canvas.create_rectangle(0, h-40, w, h, fill=soil_color, outline="")
        
        # Draw 3 Tomato Plants
        plant_positions = [w//4, w//2, 3*w//4]
        ground_y = h - 40
        
        for x in plant_positions:
            # Stake
            self.canvas.create_line(x, ground_y, x, ground_y-120, fill="#8B4513", width=3)
            # Leaves
            self.canvas.create_oval(x-20, ground_y-60, x+20, ground_y-20, fill="#228B22", outline="")
            self.canvas.create_oval(x-15, ground_y-90, x+15, ground_y-50, fill="#2E8B57", outline="")
            # Tomatoes
            self.canvas.create_oval(x-10, ground_y-50, x, ground_y-40, fill="#FF4444", outline="#CC0000")
            self.canvas.create_oval(x+5, ground_y-70, x+15, ground_y-60, fill="#FF6666", outline="#CC0000")
            self.canvas.create_oval(x-15, ground_y-80, x-5, ground_y-70, fill="#FF4444", outline="#CC0000")

        # Create 50 Large Water Drops
        if watering:
            for i in range(50):
                dx = (i * (w // 50)) % w
                dy = (i * 37) % h
                speed = 8 + (i % 5)
                drop = self.canvas.create_line(dx, dy, dx, dy+18, fill="#00BFFF", width=4, capstyle=tk.ROUND)
                self.drops.append({'id': drop, 'x': dx, 'y': dy, 'speed': speed})

    def update_celestial(self):
        """Updates Sun/Moon position and sky color based on real time"""
        now = datetime.datetime.now()
        h, m = now.hour, now.minute
        w = self.canvas.winfo_width()
        h_canvas = self.canvas.winfo_height()
        
        if w < 10 or h_canvas < 10:
            self.root.after(1000, self.update_celestial)
            return

        # Clear previous sky objects
        if 'sun' in self.sky_objects: self.canvas.delete(self.sky_objects['sun'])
        if 'moon' in self.sky_objects: self.canvas.delete(self.sky_objects['moon'])
        if 'moon_text' in self.sky_objects: self.canvas.delete(self.sky_objects['moon_text'])

        sun_x, sun_y, is_night = get_sun_position(h, m)
        
        if not is_night:
            # Draw Sun
            cx = int(sun_x * w)
            cy = int(sun_y * (h_canvas - 50)) # Keep above plants
            self.sky_objects['sun'] = self.canvas.create_oval(cx-30, cy-30, cx+30, cy+30, fill="#FFD700", outline="#FFA500", width=2)
            self.canvas.configure(bg="#87CEEB") # Day sky
            self.lbl_moon.config(text="")
        else:
            # Draw Moon
            # Moon phase logic
            phase_name = get_moon_phase_name(now.day, now.month, now.year)
            mx = int((0.1 + 0.8 * ((h - 18) / 12.0)) * w) if h > 18 else int((0.1 + 0.8 * ((h + 6) / 12.0)) * w)
            my = int(0.3 * (h_canvas - 50))
            
            # Simple visual representation of phase (color/size variation)
            moon_color = "#F4F6F0"
            if "Full" in phase_name: moon_color = "#FFFFFF"
            elif "New" in phase_name: moon_color = "#CCCCCC"
            
            self.sky_objects['moon'] = self.canvas.create_oval(mx-25, my-25, mx+25, my+25, fill=moon_color, outline="#DDD", width=1)
            self.sky_objects['moon_text'] = self.canvas.create_text(mx, my+40, text=phase_name, fill="white", font=("Arial", 10))
            
            # Night Sky Gradient simulation (solid dark blue for simplicity)
            self.canvas.configure(bg="#0B1026")

        self.root.after(60000, self.update_celestial) # Update every minute

    def animate_water(self):
        if not pump_active:
            return
            
        h = self.canvas.winfo_height()
        
        for drop in self.drops:
            self.canvas.move(drop['id'], 0, drop['speed'])
            drop['y'] += drop['speed']
            
            if drop['y'] > h:
                drop['y'] = -20
                self.canvas.coords(drop['id'], drop['x'], drop['y'], drop['x'], drop['y']+18)
        
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
