#!/bin/bash

# Script to compile the Garden Pump Controller C program
# Requires wiringPi library installed

SOURCE_FILE="garden_pump_controller.c"
OUTPUT_FILE="garden_pump_controller"

echo "=== Garden Pump Controller Compilation Script ==="
echo ""

# Check if source file exists
if [ ! -f "$SOURCE_FILE" ]; then
    echo "ERROR: Source file '$SOURCE_FILE' not found!"
    echo "Please ensure you are in the correct directory."
    exit 1
fi

echo "Found source file: $SOURCE_FILE"

# Check if gcc is installed
if ! command -v gcc &> /dev/null; then
    echo "ERROR: gcc compiler not found!"
    echo "Please install it with: sudo apt-get install gcc"
    exit 1
fi

echo "Found gcc compiler: $(gcc --version | head -n1)"

# Check if wiringPi headers are available
if [ ! -f "/usr/include/wiringPi.h" ] && [ ! -f "/usr/local/include/wiringPi.h" ]; then
    echo "WARNING: wiringPi headers not found in standard locations."
    echo "The compilation may fail if wiringPi is not installed."
    echo "To install wiringPi, run:"
    echo "  git clone https://github.com/WiringPi/WiringPi.git"
    echo "  cd WiringPi"
    echo "  ./build"
    echo ""
    read -p "Continue anyway? (y/n): " confirm
    if [[ $confirm != [yY] ]]; then
        echo "Compilation cancelled."
        exit 1
    fi
fi

echo ""
echo "Compiling $SOURCE_FILE..."

# Compile the program
gcc -o "$OUTPUT_FILE" "$SOURCE_FILE" -lwiringPi -Wall -Wextra

# Check if compilation was successful
if [ $? -eq 0 ]; then
    echo ""
    echo "SUCCESS: Compilation completed!"
    echo "Output binary: $OUTPUT_FILE"
    echo ""
    echo "To run the program (requires sudo for GPIO access):"
    echo "  sudo ./$OUTPUT_FILE"
    echo ""
    
    # Set executable permissions
    chmod +x "$OUTPUT_FILE"
    echo "Executable permissions set."
else
    echo ""
    echo "ERROR: Compilation failed!"
    echo "Please check for error messages above."
    echo "Common issues:"
    echo "  - wiringPi library not installed"
    echo "  - Missing development packages"
    exit 1
fi
