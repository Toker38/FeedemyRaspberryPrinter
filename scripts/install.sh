#!/bin/bash
#
# Feedemy Printer Client - Kurulum Script'i
# Raspberry Pi üzerinde çalıştırılmalı
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="feedemy-printer"

echo "=================================="
echo "  Feedemy Printer Client Setup"
echo "=================================="
echo ""

# 1. Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "Please run without sudo. Script will request sudo when needed."
    exit 1
fi

# 2. System dependencies
echo "[1/6] Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv git

# 3. Python dependencies
echo "[2/6] Installing Python dependencies..."
cd "$PROJECT_DIR"
pip3 install -r requirements.txt

# 4. Create directories
echo "[3/6] Creating directories..."
mkdir -p "$PROJECT_DIR/data"
mkdir -p "$PROJECT_DIR/config"

# 5. USB printer permissions
echo "[4/6] Setting up USB printer permissions..."
# lp grubuna kullanıcı ekle
sudo usermod -a -G lp,dialout $USER

# udev rule for USB printers
echo 'SUBSYSTEM=="usb", ATTR{bInterfaceClass}=="07", MODE="0666"' | \
    sudo tee /etc/udev/rules.d/99-usb-printer.rules > /dev/null
sudo udevadm control --reload-rules

# 6. Log directory
echo "[5/6] Setting up logging..."
sudo touch /var/log/feedemy-printer.log
sudo chown $USER:$USER /var/log/feedemy-printer.log

# 7. Systemd service
echo "[6/6] Installing systemd service..."
sudo cp "$SCRIPT_DIR/feedemy-printer.service" /etc/systemd/system/
sudo sed -i "s|/home/pi/feedemy-raspberry-printer|$PROJECT_DIR|g" \
    /etc/systemd/system/feedemy-printer.service
sudo sed -i "s|User=pi|User=$USER|g" \
    /etc/systemd/system/feedemy-printer.service
sudo sed -i "s|Group=pi|Group=$USER|g" \
    /etc/systemd/system/feedemy-printer.service

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME

echo ""
echo "=================================="
echo "  Installation Complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo "  1. Edit config/config.json to set API URL"
echo "  2. Run manually first to register:"
echo "     python3 -m src.main"
echo "  3. Enter pairing code from admin panel"
echo "  4. After registration, start service:"
echo "     sudo systemctl start $SERVICE_NAME"
echo ""
echo "View logs:"
echo "  journalctl -u $SERVICE_NAME -f"
echo ""
