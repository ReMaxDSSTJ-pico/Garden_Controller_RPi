#!/bin/bash

# =============================================================================
# Garden Controller Installer Script
# Installs all required dependencies for the Smart Tomato Garden System
# Compatible with Raspberry Pi OS (Bookworm/Bullseye) - Pi 3B and Pi 5
# =============================================================================

echo "=========================================="
echo " 🍅 Smart Garden Controller Installer"
echo "=========================================="

# Update package list
echo "[1/6] Updating package lists..."
sudo apt update -y

# Install Python 3 and pip
echo "[2/6] Installing Python 3 and pip..."
sudo apt install -y python3 python3-pip

# Install Tkinter GUI library
echo "[3/6] Installing Tkinter GUI support..."
sudo apt install -y python3-tk

# Install Pillow for image rendering
echo "[4/6] Installing Pillow (PIL) for image support..."
sudo apt install -y python3-pil python3-pil.imagetk

# Install GPIO libraries based on hardware detection
echo "[5/6] Detecting hardware and installing GPIO libraries..."
if grep -q "Raspberry Pi 5" /proc/cpuinfo; then
    echo "   -> Detected Raspberry Pi 5. Installing lgpio..."
    sudo apt install -y python3-lgpio
elif grep -q "Raspberry Pi 4" /proc/cpuinfo; then
    echo "   -> Detected Raspberry Pi 4. Installing RPi.GPIO..."
    sudo apt install -y python3-rpi.gpio
else
    echo "   -> Detected older Pi (3B/Zero). Installing RPi.GPIO..."
    sudo apt install -y python3-rpi.gpio
fi

# Download the Tomato Garden background image from GitHub repository
echo "[6/6] Downloading Tomato Garden background image..."
cd /home/$USER/workspace || mkdir -p /home/$USER/workspace && cd /home/$USER/workspace

REPO_URL="https://raw.githubusercontent.com/ReMaxDSSTJ-pico/Garden_Controller_RPi/main/TomatoGarden.jpg"
IMAGE_FILE="TomatoGarden.jpg"

if [ -f "$IMAGE_FILE" ]; then
    echo "   -> Image '$IMAGE_FILE' already exists. Skipping download."
else
    wget -O "$IMAGE_FILE" "$REPO_URL"
    if [ $? -eq 0 ]; then
        echo "   -> Image downloaded successfully."
    else
        echo "   ⚠ Warning: Could not download image. The app will use fallback pixel art."
    fi
fi

REPO_URL="https://raw.githubusercontent.com/ReMaxDSSTJ-pico/Garden_Controller_RPi/main/garden_controller_gui.py"
IMAGE_FILE="garden_controller_gui.py"

if [ -f "$IMAGE_FILE" ]; then
    echo "   -> Image '$IMAGE_FILE' already exists. Skipping download."
else
    wget -O "$IMAGE_FILE" "$REPO_URL"
    if [ $? -eq 0 ]; then
        echo "   -> Python program downloaded successfully."
    else
        echo "   ⚠ Error: Could not download python source code .py Download it manually from repository."
    fi
fi

# Install Emoji Font Support
echo "[6/7] Installing Noto Color Emoji font..."
sudo apt install -y fonts-noto-color-emoji
# Refresh the font cache so applications can see the new emoji glyphs immediately
fc-cache -f -v > /dev/null 2>&1
echo "   -> Emoji fonts installed and font cache updated."

# Make the main application executable
chmod +x garden_controller_gui.py 2>/dev/null || true

echo ""
echo "=========================================="
echo " ✅ Installation Complete!"
echo "=========================================="
echo ""
echo "To run the Garden Controller:"
echo "  cd /home/$USER/workspace"
echo "  sudo python3 garden_controller_gui.py"
echo ""
echo "Requirements summary:"
echo "  • python3          : Core language"
echo "  • python3-tk       : GUI toolkit (Tkinter)"
echo "  • python3-pil      : Image processing (Pillow)"
echo "  • python3-lgpio    : GPIO control for Pi 5"
echo "  • python3-rpi.gpio : GPIO control for Pi 3/4"
echo "  • $IMAGE_FILE     : Background image for animation"
echo ""
