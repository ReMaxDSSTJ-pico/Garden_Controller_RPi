#!/usr/bin/env python3
"""
Automatic Gardening System GUI
Runs on Raspberry Pi 3B with Tkinter and RPi.GPIO
Displays statistics, time, status, and watering animation.
"""

import tkinter as tk
from tkinter import font as tkfont
import RPi.GPIO as GPIO
import datetime
import threading
import time
import sys

# --- Configuration ---
PUMP_1_PIN = 17
PUMP_2_PIN = 27
CYCLE_ON_MINUTES = 5
CYCLE_OFF_MINUTES = 5
TOTAL_CYCLES = 4

# Global State
state = {
    "running": False,
    "pump_active": False,
    "current_cycle": 0,
    "phase": "OFF",  # ON or OFF
    "start_time": None,
    "next_switch_time": None,
    "total_watering_seconds": 0,
    "manual_override": False
}

# --- GPIO Setup ---
def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PUMP_1_PIN, GPIO.OUT)
    GPIO.setup(PUMP_2_PIN, GPIO.OUT)
    GPIO.output(PUMP_1_PIN, GPIO.LOW)
    GPIO.output(PUMP_2_PIN, GPIO.LOW)

def set_pumps(active):
    level = GPIO.HIGH if active else GPIO.LOW
    GPIO.output(PUMP_1_PIN, level)
    GPIO.output(PUMP_2_PIN, level)
    state["pump_active"] = active
    
    if active:
        state["phase"] = "WATERING"
    else:
        state["phase"] = "RESTING"

# --- Logic Thread ---
def control_loop():
    while state["running"]:
        now = datetime.datetime.now()
        
        if not state["manual_override"]:
            # Check if we need to start a new day/session logic here if needed
            # For this demo, we assume continuous running once started
            
            if state["next_switch_time"] and now >= state["next_switch_time"]:
                if state["phase"] == "WATERING":
                    # Switch to OFF
                    set_pumps(False)
                    state["current_cycle"] += 0.5 # Half cycle done
                    state["next_switch_time"] = now + datetime.timedelta(minutes=CYCLE_OFF_MINUTES)
                    state["phase"] = "WAITING"
                elif state["phase"] == "WAITING":
                    # Switch to ON (if cycles remain)
                    if state["current_cycle"] < TOTAL_CYCLES:
                        set_pumps(True)
                        state["current_cycle"] += 0.5
                        state["next_switch_time"] = now + datetime.timedelta(minutes=CYCLE_ON_MINUTES)
                        state["phase"] = "STARTING"
                    else:
                        # Cycle complete
                        state["running"] = False
                        set_pumps(False)
                        state["phase"] = "COMPLETE"
        
        # Update statistics
        if state["pump_active"]:
            state["total_watering_seconds"] += 1
            
        time.sleep(1)

# --- GUI Class ---
class GardenGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Smart Garden Controller")
        self.geometry("800x480")  # Standard 7-inch screen resolution
        self.configure(bg="#1a1a1a")
        
        # Fonts
        self.title_font = tkfont.Font(family="Helvetica", size=24, weight="bold")
        self.status_font = tkfont.Font(family="Helvetica", size=18, weight="bold")
        self.info_font = tkfont.Font(family="Helvetica", size=14)
        self.big_digit_font = tkfont.Font(family="Digital-7", size=48) # Fallback if missing
        
        self.create_widgets()
        self.update_clock()
        self.update_gui_loop()
        
        # Start logic thread
        self.logic_thread = threading.Thread(target=control_loop, daemon=True)
        self.logic_thread.start()

    def create_widgets(self):
        # Header
        header_frame = tk.Frame(self, bg="#2c3e50", height=60)
        header_frame.pack(fill=tk.X, padx=10, pady=10)
        
        lbl_title = tk.Label(header_frame, text="🌱 Automatic Garden System", 
                             font=self.title_font, fg="#ecf0f1", bg="#2c3e50")
        lbl_title.pack(side=tk.LEFT, padx=20)
        
        self.lbl_clock = tk.Label(header_frame, text="--:--:--", 
                                  font=("Courier", 20), fg="#2ecc71", bg="#2c3e50")
        self.lbl_clock.pack(side=tk.RIGHT, padx=20)

        # Main Content
        main_frame = tk.Frame(self, bg="#1a1a1a")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # Left Panel: Status & Animation
        left_panel = tk.Frame(main_frame, bg="#2c3e50", relief=tk.RAISED, bd=2)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        self.lbl_status_text = tk.Label(left_panel, text="SYSTEM IDLE", 
                                        font=self.status_font, fg="#95a5a6", bg="#2c3e50")
        self.lbl_status_text.pack(pady=20)
        
        # Canvas for Animation
        self.canvas = tk.Canvas(left_panel, width=300, height=200, bg="#34495e", highlightthickness=0)
        self.canvas.pack(pady=10)
        
        # Draw initial static elements (Pots)
        self.draw_pots()
        
        # Right Panel: Statistics & Controls
        right_panel = tk.Frame(main_frame, bg="#2c3e50", relief=tk.RAISED, bd=2)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        
        # Stats
        stats_frame = tk.Frame(right_panel, bg="#2c3e50")
        stats_frame.pack(pady=20)
        
        self.create_stat_row(stats_frame, "Cycle Progress:", "0 / 4", 0)
        self.create_stat_row(stats_frame, "Phase:", "Waiting", 1)
        self.create_stat_row(stats_frame, "Total Water Time:", "0 min", 2)
        self.create_stat_row(stats_frame, "Next Action:", "--:--", 3)
        
        # Controls
        ctrl_frame = tk.Frame(right_panel, bg="#2c3e50")
        ctrl_frame.pack(side=tk.BOTTOM, pady=30)
        
        btn_start = tk.Button(ctrl_frame, text="START AUTO", command=self.start_auto,
                              bg="#27ae60", fg="white", font=self.info_font, width=12, height=2)
        btn_start.grid(row=0, column=0, padx=10, pady=10)
        
        btn_stop = tk.Button(ctrl_frame, text="STOP", command=self.stop_auto,
                             bg="#c0392b", fg="white", font=self.info_font, width=12, height=2)
        btn_stop.grid(row=0, column=1, padx=10, pady=10)
        
        btn_manual = tk.Button(ctrl_frame, text="MANUAL ON/OFF", command=self.toggle_manual,
                               bg="#f39c12", fg="white", font=self.info_font, width=25, height=2)
        btn_manual.grid(row=1, column=0, columnspan=2, padx=10, pady=10)

        self.animation_objects = []
        self.animate_flag = False

    def draw_pots(self):
        self.canvas.delete("all")
        # Draw two pots
        colors = ["#8e44ad", "#2980b9"]
        for i in range(2):
            x = 80 + (i * 140)
            # Pot body
            self.canvas.create_polygon(x, 100, x+20, 40, x+80, 40, x+100, 100, 
                                       fill=colors[i], outline="#ecf0f1", width=2)
            # Plant
            self.canvas.create_oval(x+30, 10, x+70, 40, fill="#2ecc71", outline="#27ae60")
            
    def create_stat_row(self, parent, label_text, initial_value, row):
        lbl_label = tk.Label(parent, text=label_text, font=self.info_font, fg="#bdc3c7", bg="#2c3e50", anchor="w")
        lbl_label.grid(row=row, column=0, sticky="w", padx=20, pady=5)
        
        lbl_value = tk.Label(parent, text=initial_value, font=("Courier", 16, "bold"), fg="#f1c40f", bg="#2c3e50", anchor="e")
        lbl_value.grid(row=row, column=1, sticky="e", padx=20, pady=5)
        
        setattr(self, f"stat_val_{row}", lbl_value)

    def update_clock(self):
        now = datetime.datetime.now().strftime("%H:%M:%S\n%Y-%m-%d")
        self.lbl_clock.config(text=now)
        self.after(1000, self.update_clock)

    def update_gui_loop(self):
        # Update Text Stats
        cycle_display = f"{int(state['current_cycle'] // 1)} / {TOTAL_CYCLES}"
        if state["current_cycle"] % 1 != 0:
            cycle_display += " (Active)"
        
        self.stat_val_0.config(text=cycle_display)
        self.stat_val_1.config(text=state["phase"])
        
        mins = state["total_watering_seconds"] // 60
        secs = state["total_watering_seconds"] % 60
        self.stat_val_2.config(text=f"{mins}m {secs}s")
        
        if state["next_switch_time"]:
            self.stat_val_3.config(text=state["next_switch_time"].strftime("%H:%M:%S"))
        else:
            self.stat_val_3.config(text="--:--")

        # Update Status Label Color
        if state["pump_active"]:
            self.lbl_status_text.config(text="💧 WATERING ACTIVE 💧", fg="#2ecc71")
            if not self.animate_flag:
                self.start_animation()
        else:
            if state["phase"] == "COMPLETE":
                self.lbl_status_text.config(text="✅ CYCLE COMPLETE", fg="#f1c40f")
            else:
                self.lbl_status_text.config(text="⏸️ SYSTEM RESTING", fg="#95a5a6")
            if self.animate_flag:
                self.stop_animation()

        self.after(500, self.update_gui_loop)

    def start_animation(self):
        self.animate_flag = True
        self.canvas.delete("water")
        self.animate_drops()

    def stop_animation(self):
        self.animate_flag = False
        self.canvas.delete("water")

    def animate_drops(self):
        if not self.animate_flag:
            return
            
        self.canvas.delete("water")
        colors = ["#3498db", "#2980b9"]
        
        for i in range(2):
            x_base = 90 + (i * 140)
            # Draw falling drops at random heights to simulate flow
            for j in range(5):
                y_offset = (time.time() * 100 + j * 40) % 100
                y = 40 + y_offset
                if y < 100: # Only draw above pot
                    self.canvas.create_oval(x_base+35+j*5, y, x_base+45+j*5, y+10, 
                                            fill=colors[i], tags="water", outline="")
        
        self.after(50, self.animate_drops)

    def start_auto(self):
        if not state["running"]:
            state["running"] = True
            state["manual_override"] = False
            state["current_cycle"] = 0
            state["total_watering_seconds"] = 0
            state["phase"] = "STARTING"
            state["next_switch_time"] = datetime.datetime.now() # Start immediately
            set_pumps(True)
            state["current_cycle"] = 0.5

    def stop_auto(self):
        state["running"] = False
        state["manual_override"] = False
        set_pumps(False)
        state["phase"] = "STOPPED"

    def toggle_manual(self):
        state["manual_override"] = True
        state["running"] = False # Pause auto logic
        if state["pump_active"]:
            set_pumps(False)
            state["phase"] = "MANUAL OFF"
        else:
            set_pumps(True)
            state["phase"] = "MANUAL ON"

    def on_closing(self):
        state["running"] = False
        set_pumps(False)
        GPIO.cleanup()
        self.destroy()

if __name__ == "__main__":
    try:
        setup_gpio()
        app = GardenGUI()
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        app.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
