/*
 * Automatic Gardening System - Water Pump Controller
 * For Raspberry Pi 3 with relay module controlling two 12V water pumps
 * 
 * Cycle: 5 minutes ON, 5 minutes OFF, repeat 4 times
 * Total runtime: 40 minutes (20 min ON + 20 min OFF)
 * 
 * Compile with: gcc -o garden_pump_controller garden_pump_controller.c -lwiringPi
 * Run with: sudo ./garden_pump_controller
 */

#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>
#include <wiringPi.h>

// Configuration - GPIO pins (BCM numbering converted to wiringPi)
#define PUMP1_PIN 17  // GPIO17 for pump 1 relay
#define PUMP2_PIN 27  // GPIO27 for pump 2 relay

#define CYCLE_ON_TIME 300   // 5 minutes in seconds
#define CYCLE_OFF_TIME 300  // 5 minutes in seconds
#define NUM_CYCLES 4

// Global flag for interrupt handling
volatile int interrupted = 0;

// Signal handler for graceful shutdown
void signal_handler(int sig) {
    printf("\n\n!!! Interrupted by user !!!\n");
    interrupted = 1;
}

// Initialize GPIO pins
void setup_gpio() {
    if (wiringPiSetupGpio() == -1) {
        fprintf(stderr, "ERROR: Failed to initialize wiringPi. Make sure to run as root.\n");
        exit(1);
    }
    
    pinMode(PUMP1_PIN, OUTPUT);
    pinMode(PUMP2_PIN, OUTPUT);
    
    // Start with pumps OFF (relays typically active LOW)
    digitalWrite(PUMP1_PIN, HIGH);
    digitalWrite(PUMP2_PIN, HIGH);
    
    printf("GPIO initialized: Pump1 on GPIO%d, Pump2 on GPIO%d\n", PUMP1_PIN, PUMP2_PIN);
}

// Turn on both pumps
void turn_on_pumps() {
    // Relays are typically active LOW, so set to LOW to activate
    digitalWrite(PUMP1_PIN, LOW);
    digitalWrite(PUMP2_PIN, LOW);
    printf("✓ Pumps ON\n");
}

// Turn off both pumps
void turn_off_pumps() {
    digitalWrite(PUMP1_PIN, HIGH);
    digitalWrite(PUMP2_PIN, HIGH);
    printf("✓ Pumps OFF\n");
}

// Run the complete gardening cycle
int run_gardening_cycle() {
    int cycle;
    
    printf("\n============================================================\n");
    printf("AUTOMATIC GARDENING SYSTEM STARTED\n");
    printf("============================================================\n");
    printf("Configuration:\n");
    printf("  - Pump 1: GPIO%d\n", PUMP1_PIN);
    printf("  - Pump 2: GPIO%d\n", PUMP2_PIN);
    printf("  - ON time: %d minutes\n", CYCLE_ON_TIME / 60);
    printf("  - OFF time: %d minutes\n", CYCLE_OFF_TIME / 60);
    printf("  - Number of cycles: %d\n", NUM_CYCLES);
    printf("  - Total estimated time: %d minutes\n", 
           (CYCLE_ON_TIME + CYCLE_OFF_TIME) * NUM_CYCLES / 60);
    printf("============================================================\n\n");
    
    for (cycle = 1; cycle <= NUM_CYCLES; cycle++) {
        if (interrupted) {
            return 0;
        }
        
        printf("\n--- Cycle %d/%d ---\n", cycle, NUM_CYCLES);
        
        // Turn pumps ON
        turn_on_pumps();
        printf("  Watering for %d minutes...\n", CYCLE_ON_TIME / 60);
        
        // Wait for ON period (with interrupt checking)
        int i;
        for (i = 0; i < CYCLE_ON_TIME && !interrupted; i++) {
            sleep(1);
        }
        
        if (interrupted) {
            turn_off_pumps();
            return 0;
        }
        
        // Turn pumps OFF
        turn_off_pumps();
        
        // If not the last cycle, wait for OFF period
        if (cycle < NUM_CYCLES) {
            printf("  Waiting for %d minutes...\n", CYCLE_OFF_TIME / 60);
            
            for (i = 0; i < CYCLE_OFF_TIME && !interrupted; i++) {
                sleep(1);
            }
        }
        
        if (interrupted) {
            return 0;
        }
    }
    
    printf("\n============================================================\n");
    printf("GARDENING CYCLE COMPLETED SUCCESSFULLY\n");
    printf("============================================================\n");
    
    return 1;
}

int main() {
    int success;
    
    printf("Starting Automatic Gardening System...\n");
    
    // Setup signal handlers
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    // Setup GPIO
    setup_gpio();
    
    // Run the gardening cycle
    success = run_gardening_cycle();
    
    if (success) {
        printf("\nAll cycles completed. Pumps turned off.\n");
    } else {
        printf("\nProgram terminated early. Pumps turned off for safety.\n");
    }
    
    // Clean up GPIO
    digitalWrite(PUMP1_PIN, HIGH);
    digitalWrite(PUMP2_PIN, HIGH);
    
    printf("GPIO cleaned up\n");
    
    return success ? 0 : 1;
}
