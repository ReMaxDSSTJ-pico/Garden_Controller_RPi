#!/bin/bash

# Script to add cron entry for garden pump controller
# Schedule:
# - August: Every day at 7:00 PM
# - July & September: Every 2 days at 7:00 PM
# - Other months: Every 3 days at 7:00 PM

CRON_FILE="$HOME/cron_garden_pump"
SCRIPT_PATH="/home/pi/garden_pump_controller.py"  # Adjust this path to your actual script location

# Create the cron entry with month-specific scheduling
cat > "$CRON_FILE" << 'EOF'
# Garden Pump Controller Cron Jobs
# Format: minute hour day month weekday command

# August (month 8) - Every day at 7:00 PM
0 19 * 8 * /usr/bin/python3 /home/pi/garden_pump_controller.py

# July (month 7) and September (month 9) - Every 2 days at 7:00 PM
0 19 */2 7 * /usr/bin/python3 /home/pi/garden_pump_controller.py
0 19 */2 9 * /usr/bin/python3 /home/pi/garden_pump_controller.py

# All other months - Every 3 days at 7:00 PM
0 19 */3 1 * /usr/bin/python3 /home/pi/garden_pump_controller.py
0 19 */3 2 * /usr/bin/python3 /home/pi/garden_pump_controller.py
0 19 */3 3 * /usr/bin/python3 /home/pi/garden_pump_controller.py
0 19 */3 4 * /usr/bin/python3 /home/pi/garden_pump_controller.py
0 19 */3 5 * /usr/bin/python3 /home/pi/garden_pump_controller.py
0 19 */3 6 * /usr/bin/python3 /home/pi/garden_pump_controller.py
0 19 */3 10 * /usr/bin/python3 /home/pi/garden_pump_controller.py
0 19 */3 11 * /usr/bin/python3 /home/pi/garden_pump_controller.py
0 19 */3 12 * /usr/bin/python3 /home/pi/garden_pump_controller.py
EOF

echo "Cron file created at: $CRON_FILE"
echo ""
echo "Contents:"
cat "$CRON_FILE"
echo ""

# Ask user if they want to install the cron job
read -p "Do you want to install this cron job? (y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Install the cron job
    crontab "$CRON_FILE"
    echo "Cron job installed successfully!"
    echo ""
    echo "Current crontab:"
    crontab -l
else
    echo "Cron job not installed."
    echo "To install manually, run: crontab $CRON_FILE"
fi

# Cleanup
rm -f "$CRON_FILE"
