#!/bin/bash

echo "========================================="
echo "Garden Controller - Dependency Installer"
echo "========================================="

# Update package list
echo "[1/4] Updating package lists..."
sudo apt-get update -y

# Install Python3-tk for GUI
echo "[2/4] Installing tkinter (GUI library)..."
sudo apt-get install -y python3-tk

# Install RPi.GPIO for controlling pins
echo "[3/4] Installing RPi.GPIO..."
sudo apt-get install -y python3-rpi.gpio

# Optional: Install wiringPi for C version (if needed later)
echo "[4/4] Checking C compiler tools..."
if ! command -v gcc &> /dev/null; then
    echo "GCC not found. Installing build-essential..."
    sudo apt-get install -y build-essential
else
    echo "GCC already installed."
fi

echo ""
echo "========================================="
echo "Installation Complete!"
echo "========================================="
echo ""
echo "To run the Python GUI:"
echo "  python3 garden_controller_gui.py"
echo ""
echo "Note: You may need to run with sudo if GPIO access fails:"
echo "  sudo python3 garden_controller_gui.py"
