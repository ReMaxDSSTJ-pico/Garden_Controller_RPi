#!/usr/bin/env python3
"""
Automatic Gardening System - Water Pump Controller
For Raspberry Pi 3 with relay module controlling two 12V water pumps

Cycle: 5 minutes ON, 5 minutes OFF, repeat 4 times
Total runtime: 40 minutes (20 min ON + 20 min OFF)
"""

import RPi.GPIO as GPIO
import time
import sys

# Configuration
PUMP1_PIN = 17  # GPIO pin for pump 1 relay
PUMP2_PIN = 27  # GPIO pin for pump 2 relay
CYCLE_ON_TIME = 300  # 5 minutes in seconds
CYCLE_OFF_TIME = 300  # 5 minutes in seconds
NUM_CYCLES = 4

def setup_gpio():
    """Initialize GPIO pins for relay control"""
    GPIO.setmode(GPIO.BCM)  # Use BCM numbering
    GPIO.setup(PUMP1_PIN, GPIO.OUT)
    GPIO.setup(PUMP2_PIN, GPIO.OUT)
    
    # Start with pumps OFF (relays typically active LOW)
    GPIO.output(PUMP1_PIN, GPIO.HIGH)
    GPIO.output(PUMP2_PIN, GPIO.HIGH)
    
    print(f"GPIO initialized: Pump1 on GPIO{PUMP1_PIN}, Pump2 on GPIO{PUMP2_PIN}")

def cleanup_gpio():
    """Clean up GPIO pins on exit"""
    GPIO.cleanup()
    print("GPIO cleaned up")

def turn_on_pumps():
    """Activate both water pumps"""
    # Relays are typically active LOW, so set to LOW to activate
    GPIO.output(PUMP1_PIN, GPIO.LOW)
    GPIO.output(PUMP2_PIN, GPIO.LOW)
    print("✓ Pumps ON")

def turn_off_pumps():
    """Deactivate both water pumps"""
    GPIO.output(PUMP1_PIN, GPIO.HIGH)
    GPIO.output(PUMP2_PIN, GPIO.HIGH)
    print("✓ Pumps OFF")

def run_gardening_cycle():
    """Run the complete gardening cycle"""
    print("\n" + "="*60)
    print("AUTOMATIC GARDENING SYSTEM STARTED")
    print("="*60)
    print(f"Configuration:")
    print(f"  - Pump 1: GPIO{PUMP1_PIN}")
    print(f"  - Pump 2: GPIO{PUMP2_PIN}")
    print(f"  - ON time: {CYCLE_ON_TIME//60} minutes")
    print(f"  - OFF time: {CYCLE_OFF_TIME//60} minutes")
    print(f"  - Number of cycles: {NUM_CYCLES}")
    print(f"  - Total estimated time: {(CYCLE_ON_TIME + CYCLE_OFF_TIME) * NUM_CYCLES // 60} minutes")
    print("="*60 + "\n")
    
    try:
        for cycle in range(1, NUM_CYCLES + 1):
            print(f"\n--- Cycle {cycle}/{NUM_CYCLES} ---")
            
            # Turn pumps ON
            turn_on_pumps()
            print(f"  Watering for {CYCLE_ON_TIME//60} minutes...")
            
            # Wait for ON period
            time.sleep(CYCLE_ON_TIME)
            
            # Turn pumps OFF
            turn_off_pumps()
            
            # If not the last cycle, wait for OFF period
            if cycle < NUM_CYCLES:
                print(f"  Waiting for {CYCLE_OFF_TIME//60} minutes...")
                time.sleep(CYCLE_OFF_TIME)
        
        print("\n" + "="*60)
        print("GARDENING CYCLE COMPLETED SUCCESSFULLY")
        print("="*60)
        
    except KeyboardInterrupt:
        print("\n\n!!! Interrupted by user !!!")
        turn_off_pumps()
        return False
    
    except Exception as e:
        print(f"\n!!! Error occurred: {e} !!!")
        turn_off_pumps()
        return False
    
    return True

def main():
    """Main entry point"""
    print("Starting Automatic Gardening System...")
    
    # Setup GPIO
    setup_gpio()
    
    try:
        # Run the gardening cycle
        success = run_gardening_cycle()
        
        if success:
            print("\nAll cycles completed. Pumps turned off.")
        else:
            print("\nProgram terminated early. Pumps turned off for safety.")
            
    finally:
        # Always clean up GPIO
        cleanup_gpio()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
