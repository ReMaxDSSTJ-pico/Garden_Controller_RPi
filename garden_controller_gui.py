#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk
import datetime
import time
import os
import sys
import math
import random

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

# --- Image Support (Pillow) ---
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Warning: PIL (Pillow) not found. Install with: sudo apt install python3-pil")

# --- Configuration ---
RELAY_PINS = [17, 27, 22, 23]          # GPIO pins for Relays 1-4
DEFAULT_ON_TIMES = [60, 120, 180, 240] # Default ON times in seconds (1, 2, 3, 4 min)
OFF_TIMES = [300, 180, 120, 60]        # Fixed OFF times in seconds (5, 3, 2, 1 min)
NUM_ZONES = 4
WATER_TIME = "19:00"                   # Daily scheduled watering start time
IMAGE_FILE = "TomatoGarden.jpg"        # Background image in the same folder

# Global State
stop_requested = False
zone_active = [False] * NUM_ZONES
zone_on_times = DEFAULT_ON_TIMES.copy()


def get_seasonal_schedule():
    """Returns days interval based on calendar month.
    August             -> daily (every 1 day)
    July & September   -> every 2 days
    December & January -> every 4 days
    All other months   -> every 3 days
    """
    month = datetime.datetime.now().month
    if month == 8:
        return 1   # August: water daily
    elif month in (7, 9):
        return 2   # July / September: every 2 days
    elif month in (12, 1):
        return 4   # December / January: every 4 days
    else:
        return 3   # Feb-Jun, Oct-Nov: every 3 days


def get_season_name(interval):
    """Human-readable name of the active watering rule."""
    names = {1: "AUGUST", 2: "JULY/SEPTEMBER", 3: "REGULAR", 4: "DEC/JAN"}
    return names.get(interval, "REGULAR")


def calculate_next_run():
    """Calculate next run datetime based on monthly rules. Returns a datetime."""
    now = datetime.datetime.now()
    interval = get_seasonal_schedule()
    h, m = map(int, WATER_TIME.split(":"))
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)

    # Find the next valid day matching the interval pattern
    while True:
        if target > now:
            days_since_epoch = (target - datetime.datetime(target.year, 1, 1)).days
            if days_since_epoch % interval == 0:
                return target
        target += datetime.timedelta(days=1)


def setup_gpio():
    global h_chip
    if USING_LGPIO:
        try:
            h_chip = lgpio.gpiochip_open(0)
            for pin in RELAY_PINS:
                lgpio.gpio_claim_output(h_chip, pin)
                lgpio.gpio_write(h_chip, pin, 0)
            print(f"lgpio initialized on chip 0. Pins {RELAY_PINS} set to LOW.")
        except Exception as e:
            print(f"Critical LGPIO Error: {e}")
            sys.exit(1)
    else:
        GPIO.setmode(GPIO.BCM)
        for pin in RELAY_PINS:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)


def set_relay(zone_idx, state):
    pin = RELAY_PINS[zone_idx]
    val = 1 if state else 0
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
                print("lgpio cleanup complete.")
        except Exception as e:
            if "unknown handle" not in str(e).lower():
                print(f"Cleanup Warning: {e}")
    else:
        try:
            GPIO.cleanup()
            print("RPi.GPIO cleanup complete.")
        except Exception:
            pass


# --- GUI Application ---
class GardenApp:
    def __init__(self, root):
        self.root = root
        self.root.title("\U0001F345 Smart Tomato Garden Controller")
        self.root.geometry("800x700")
        self.root.configure(bg="#f0f8ff")

        # Header
        header = tk.Frame(root, bg="#2E8B57", height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="\U0001F345 Tomato Garden Controller", font=("Arial", 20, "bold"),
                 bg="#2E8B57", fg="white").pack(pady=10)

        # Status Panel
        status_frame = tk.Frame(root, bg="white", pady=10, relief=tk.RAISED, bd=2)
        status_frame.pack(fill=tk.X, padx=20, pady=10)

        self.lbl_status = tk.Label(status_frame, text="Status: IDLE", font=("Arial", 16, "bold"),
                                   bg="white", fg="#333")
        self.lbl_status.pack()

        self.lbl_timer = tk.Label(status_frame, text="Time: --:--:--", font=("Arial", 14),
                                  bg="white", fg="#666")
        self.lbl_timer.pack()

        # Animation Canvas
        self.canvas_frame = tk.Frame(root, bg="#e0f7fa", relief=tk.SUNKEN, bd=2)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        self.canvas = tk.Canvas(self.canvas_frame, bg="#e0f7fa", highlightthickness=0,
                                width=800, height=250)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.zone_drops = [[] for _ in range(NUM_ZONES)]
        self.zone_anim_running = [False] * NUM_ZONES
        self.bg_image = None

        self.draw_background()
        self.draw_all_plants()

        # Controls
        ctrl_frame = tk.Frame(root, bg="#f0f8ff")
        ctrl_frame.pack(pady=10)

        btn_style = {"font": ("Arial", 11, "bold"), "width": 12, "height": 1, "fg": "white"}
        tk.Button(ctrl_frame, text="START ALL", command=self.start_all, bg="#4CAF50", **btn_style)\
            .grid(row=0, column=0, padx=5)
        tk.Button(ctrl_frame, text="STOP", command=self.stop_system, bg="#f44336", **btn_style)\
            .grid(row=0, column=1, padx=5)

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

            led = tk.Label(z_frame, text="\u25CF", font=("Arial", 16), bg="white", fg="#cccccc")
            led.pack()
            self.zone_leds.append(led)

            time_lbl = tk.Label(z_frame, text=f"{zone_on_times[i]}s ON", font=("Arial", 10), bg="white")
            time_lbl.pack()
            self.time_labels.append(time_lbl)

            btn_frame = tk.Frame(z_frame, bg="white")
            btn_frame.pack()
            tk.Button(btn_frame, text="-", command=lambda idx=i: self.adjust_time(idx, -10),
                      width=3, bg="#FF9800", fg="white").grid(row=0, column=0, padx=2)
            tk.Button(btn_frame, text="+", command=lambda idx=i: self.adjust_time(idx, 10),
                      width=3, bg="#2196F3", fg="white").grid(row=0, column=1, padx=2)

            tk.Label(z_frame, text=f"Off: {OFF_TIMES[i]}s", font=("Arial", 9), bg="white", fg="#666").pack()

        # --- Bottom Status Bar: Season + Next Watering Countdown ---
        self.status_bar = tk.Frame(root, bg="#263238", height=44)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_bar.pack_propagate(False)

        self.lbl_next = tk.Label(self.status_bar, text="", font=("Arial", 11, "bold"),
                                 bg="#263238", fg="#80DE60")
        self.lbl_next.pack(side=tk.LEFT, padx=15)

        self.lbl_countdown = tk.Label(self.status_bar, text="", font=("Arial", 11, "bold"),
                                      bg="#263238", fg="#FFD54F")
        self.lbl_countdown.pack(side=tk.RIGHT, padx=15)

        self.running = False
        self.next_run_dt = calculate_next_run()

    # ---------- Drawing ----------
    def draw_background(self):
        self.canvas.delete("bg")
        w, h = 800, 250

        img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), IMAGE_FILE)
        if HAS_PIL and os.path.exists(img_path):
            try:
                img = Image.open(img_path)
                img = img.resize((w, h))
                self.bg_image = ImageTk.PhotoImage(img)
                self.canvas.create_image(0, 0, anchor=tk.NW, image=self.bg_image, tags="bg")
                return
            except Exception as e:
                print(f"Could not load image {img_path}: {e}")

        # Fallback procedural background
        for y in range(0, 180, 4):
            factor = y / 180.0
            r = int(63 * (1 - factor) + 121 * factor)
            g = int(142 * (1 - factor) + 195 * factor)
            b = int(226 * (1 - factor) + 252 * factor)
            color = f"#{r:02x}{g:02x}{b:02x}"
            self.canvas.create_rectangle(0, y, w, y + 4, fill=color, outline="", tags="bg")

        self.canvas.create_rectangle(0, 180, w, h, fill="#5D4037", outline="", tags="bg")
        self.canvas.create_rectangle(0, 180, w, 185, fill="#795548", outline="", tags="bg")
        for x in range(0, w, 15):
            offset = random.randint(-2, 2)
            self.canvas.create_line(x, 180, x - 3 + offset, 170, fill="#4CAF50", width=2, tags="bg")
            self.canvas.create_line(x + 5, 180, x + 2 + offset, 168, fill="#388E3C", width=2, tags="bg")

    def draw_pixel_art_plant(self, center_x, ground_y, stage):
        """Draws pixel-art style plants for growth stages 1-4."""
        items = []
        soil_y = ground_y

        if stage == 1:  # Sprout
            items.append(self.canvas.create_line(center_x, soil_y, center_x, soil_y - 15,
                                                 fill="#2E7D32", width=2, tags="plant"))
            items.append(self.canvas.create_oval(center_x - 8, soil_y - 12, center_x - 2, soil_y - 6,
                                                 fill="#4CAF50", outline="", tags="plant"))
            items.append(self.canvas.create_oval(center_x + 2, soil_y - 12, center_x + 8, soil_y - 6,
                                                 fill="#66BB6A", outline="", tags="plant"))

        elif stage == 2:  # Young Plant
            items.append(self.canvas.create_line(center_x, soil_y, center_x, soil_y - 25,
                                                 fill="#1B5E20", width=3, tags="plant"))
            items.append(self.canvas.create_polygon(center_x - 15, soil_y - 10, center_x - 5, soil_y - 15,
                                                    center_x - 10, soil_y - 5, fill="#388E3C", outline="", tags="plant"))
            items.append(self.canvas.create_polygon(center_x + 15, soil_y - 10, center_x + 5, soil_y - 15,
                                                    center_x + 10, soil_y - 5, fill="#4CAF50", outline="", tags="plant"))
            items.append(self.canvas.create_polygon(center_x - 12, soil_y - 20, center_x - 2, soil_y - 25,
                                                    center_x - 8, soil_y - 15, fill="#2E7D32", outline="", tags="plant"))
            items.append(self.canvas.create_polygon(center_x + 12, soil_y - 20, center_x + 2, soil_y - 25,
                                                    center_x + 8, soil_y - 15, fill="#388E3C", outline="", tags="plant"))

        elif stage == 3:  # Flowering
            items.append(self.canvas.create_line(center_x, soil_y, center_x, soil_y - 35,
                                                 fill="#1B5E20", width=4, tags="plant"))
            items.append(self.canvas.create_oval(center_x - 20, soil_y - 10, center_x - 5, soil_y + 5,
                                                 fill="#2E7D32", outline="", tags="plant"))
            items.append(self.canvas.create_oval(center_x + 5, soil_y - 10, center_x + 20, soil_y + 5,
                                                 fill="#388E3C", outline="", tags="plant"))
            items.append(self.canvas.create_oval(center_x - 15, soil_y - 25, center_x, soil_y - 10,
                                                 fill="#4CAF50", outline="", tags="plant"))
            items.append(self.canvas.create_oval(center_x, soil_y - 25, center_x + 15, soil_y - 10,
                                                 fill="#66BB6A", outline="", tags="plant"))
            items.append(self.canvas.create_oval(center_x - 8, soil_y - 18, center_x - 2, soil_y - 12,
                                                 fill="#FFEB3B", outline="#FBC02D", tags="plant"))
            items.append(self.canvas.create_oval(center_x + 2, soil_y - 22, center_x + 8, soil_y - 16,
                                                 fill="#FFEB3B", outline="#FBC02D", tags="plant"))
            items.append(self.canvas.create_oval(center_x - 5, soil_y - 5, center_x + 2, soil_y + 2,
                                                 fill="#8BC34A", outline="", tags="plant"))

        elif stage == 4:  # Mature Fruit
            items.append(self.canvas.create_line(center_x, soil_y, center_x, soil_y - 45,
                                                 fill="#004D40", width=5, tags="plant"))
            items.append(self.canvas.create_oval(center_x - 25, soil_y - 5, center_x - 10, soil_y + 10,
                                                 fill="#1B5E20", outline="", tags="plant"))
            items.append(self.canvas.create_oval(center_x + 10, soil_y - 5, center_x + 25, soil_y + 10,
                                                 fill="#2E7D32", outline="", tags="plant"))
            items.append(self.canvas.create_oval(center_x - 20, soil_y - 30, center_x - 5, soil_y - 15,
                                                 fill="#388E3C", outline="", tags="plant"))
            items.append(self.canvas.create_oval(center_x + 5, soil_y - 30, center_x + 20, soil_y - 15,
                                                 fill="#4CAF50", outline="", tags="plant"))
            items.append(self.canvas.create_oval(center_x - 10, soil_y - 45, center_x + 10, soil_y - 30,
                                                 fill="#2E7D32", outline="", tags="plant"))
            items.append(self.canvas.create_oval(center_x - 12, soil_y - 8, center_x - 2, soil_y + 4,
                                                 fill="#D32F2F", outline="#B71C1C", tags="plant"))
            items.append(self.canvas.create_oval(center_x + 2, soil_y - 12, center_x + 12, soil_y,
                                                 fill="#F44336", outline="#D32F2F", tags="plant"))
            items.append(self.canvas.create_oval(center_x - 8, soil_y - 20, center_x + 2, soil_y - 10,
                                                 fill="#D32F2F", outline="#B71C1C", tags="plant"))
            items.append(self.canvas.create_oval(center_x - 10, soil_y - 6, center_x - 6, soil_y - 2,
                                                 fill="#FFCDD2", outline="", tags="plant"))
        return items

    def draw_all_plants(self):
        self.canvas.delete("plant")
        self.canvas.delete("drops")
        panel_width = 800 // NUM_ZONES
        for i in range(NUM_ZONES):
            self.zone_drops[i] = []
            center_x = (panel_width * i) + (panel_width // 2)
            ground_y = 180

            self.draw_pixel_art_plant(center_x, ground_y, i + 1)

            # Create 10 Water Drops per zone (hidden initially)
            for j in range(10):
                dx = center_x - 20 + (j * 4)
                dy = -20 - (j * 10)
                drop = self.canvas.create_line(dx, dy, dx, dy + 12, fill="#00BFFF",
                                               width=3, capstyle=tk.ROUND, state='hidden', tags="drops")
                self.zone_drops[i].append({'id': drop, 'x': dx, 'y': dy, 'speed': 4 + (j % 3)})

    # ---------- Animation ----------
    def animate_zone(self, zone_idx):
        if stop_requested or not zone_active[zone_idx]:
            self.zone_anim_running[zone_idx] = False
            for d in self.zone_drops[zone_idx]:
                self.canvas.itemconfig(d['id'], state='hidden')
            return

        panel_width = 800 // NUM_ZONES
        center_x = (panel_width * zone_idx) + (panel_width // 2)

        for d in self.zone_drops[zone_idx]:
            self.canvas.itemconfig(d['id'], state='normal')
            self.canvas.move(d['id'], 0, d['speed'])
            d['y'] += d['speed']
            if d['y'] > 180:
                d['y'] = -20 - random.randint(0, 20)
                d['x'] = center_x - 25 + random.randint(0, 50)
                self.canvas.coords(d['id'], d['x'], d['y'], d['x'], d['y'] + 12)

        if zone_active[zone_idx]:
            self.root.after(50, lambda: self.animate_zone(zone_idx))
        else:
            self.zone_anim_running[zone_idx] = False

    # ---------- Controls ----------
    def update_led(self, idx, state):
        self.zone_leds[idx].config(fg="#00E676" if state else "#cccccc")

    def adjust_time(self, idx, delta):
        new_time = zone_on_times[idx] + delta
        if 10 <= new_time <= 600:
            zone_on_times[idx] = new_time
            self.time_labels[idx].config(text=f"{new_time}s ON")

    def start_all(self):
        global stop_requested
        stop_requested = False
        self.lbl_status.config(text="Status: WATERING ALL ZONES", fg="blue")
        for i in range(NUM_ZONES):
            set_relay(i, True)
            self.update_led(i, True)
            if not self.zone_anim_running[i]:
                self.zone_anim_running[i] = True
                self.animate_zone(i)
            delay_ms = zone_on_times[i] * 1000
            self.root.after(delay_ms, lambda idx=i: self.stop_zone(idx))

    def stop_zone(self, idx):
        if stop_requested:
            return
        set_relay(idx, False)
        self.update_led(idx, False)
        for d in self.zone_drops[idx]:
            self.canvas.itemconfig(d['id'], state='hidden')
        if not any(zone_active):
            self.lbl_status.config(text="Status: CYCLE COMPLETE", fg="green")
            # Reschedule next seasonal run
            self.next_run_dt = calculate_next_run()

    def stop_system(self):
        global stop_requested
        stop_requested = True
        for i in range(NUM_ZONES):
            set_relay(i, False)
            self.update_led(i, False)
            for d in self.zone_drops[i]:
                self.canvas.itemconfig(d['id'], state='hidden')
        self.lbl_status.config(text="Status: STOPPED BY USER", fg="red")
        self.next_run_dt = calculate_next_run()

    # ---------- Clock & Countdown ----------
    def format_countdown(self, delta):
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            total_seconds = 0
        hours, rem = divmod(total_seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def update_clock(self):
        now = datetime.datetime.now()
        self.lbl_timer.config(text=f"Time: {now.strftime('%H:%M:%S')}")

        # Bottom status bar: next watering info + countdown
        interval = get_seasonal_schedule()
        season = get_season_name(interval)
        next_str = self.next_run_dt.strftime("%Y-%m-%d %H:%M")
        self.lbl_next.config(text=f"\U0001F4C5 Next Watering: {next_str}  ({season}: every {interval} day{'s' if interval > 1 else ''})")

        remaining = self.next_run_dt - now
        self.lbl_countdown.config(text=f"Starts in: {self.format_countdown(remaining)}")

        # Auto-start when scheduled time arrives (if idle)
        if remaining.total_seconds() <= 0 and not any(zone_active) and not self.running:
            self.lbl_countdown.config(text="Triggering scheduled watering...")
            self.start_all()

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
