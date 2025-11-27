#!/bin/bash
#
# Feedemy Printer Client - Production Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/Toker38/FeedemyRaspberryPrinter/main/scripts/install.sh | sudo bash
#
set -eo pipefail

# === Configuration ===
INSTALL_DIR="/opt/feedemy-printer"
SERVICE_NAME="feedemy-printer"
REPO_URL="https://github.com/Toker38/FeedemyRaspberryPrinter.git"

# === Colors ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# === Functions ===
info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# === Banner ===
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Feedemy Printer Client Installer           ║${NC}"
echo -e "${BLUE}║     Raspberry Pi Thermal Printer Service       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════╝${NC}"
echo ""

# === Pre-flight checks ===

# 1. Root check
if [ "$EUID" -ne 0 ]; then
    error "Bu script root yetkisi gerektirir. Çalıştırın: sudo bash install.sh"
fi

# 2. OS check
if [ ! -f /etc/debian_version ]; then
    error "Bu installer sadece Debian/Raspberry Pi OS destekler"
fi

# 3. Architecture check
ARCH=$(uname -m)
info "Platform: $ARCH"

# === Installation ===

# Step 1: System dependencies
info "[1/6] Sistem bağımlılıkları kuruluyor..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git > /dev/null 2>&1
info "Sistem bağımlılıkları kuruldu"

# Step 2: Clone or update repository
info "[2/6] Proje indiriliyor..."
if [ -d "$INSTALL_DIR" ]; then
    cd "$INSTALL_DIR"
    git fetch --quiet origin
    git reset --hard origin/main --quiet
    info "Proje güncellendi"
else
    git clone --quiet --depth 1 "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    info "Proje indirildi"
fi

# Step 3: Python virtual environment
info "[3/6] Python ortamı hazırlanıyor..."
if [ ! -d "$INSTALL_DIR/venv" ]; then
    python3 -m venv "$INSTALL_DIR/venv"
fi
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip > /dev/null 2>&1
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt" > /dev/null 2>&1
info "Python bağımlılıkları kuruldu"

# Step 4: Create directories
info "[4/6] Dizinler oluşturuluyor..."
mkdir -p "$INSTALL_DIR/data"
mkdir -p "$INSTALL_DIR/config"
mkdir -p "$INSTALL_DIR/logs"
chmod 755 "$INSTALL_DIR/data" "$INSTALL_DIR/config" "$INSTALL_DIR/logs"
info "Dizinler oluşturuldu"

# Step 5: USB printer permissions (udev rules)
info "[5/6] USB yazıcı izinleri ayarlanıyor..."
cat > /etc/udev/rules.d/99-feedemy-printer.rules << 'UDEV_EOF'
# Feedemy Printer Service - USB Thermal Printer Access
# USB Printer class (bInterfaceClass=07)
SUBSYSTEM=="usb", ATTR{bInterfaceClass}=="07", MODE="0666"
# USB LP devices
KERNEL=="lp[0-9]*", SUBSYSTEM=="usblp", MODE="0666"
UDEV_EOF
udevadm control --reload-rules
udevadm trigger
info "USB izinleri ayarlandı"

# Step 6: Systemd service
info "[6/6] Servis kuruluyor..."
cat > /etc/systemd/system/$SERVICE_NAME.service << SERVICE_EOF
[Unit]
Description=Feedemy Printer Service
Documentation=https://github.com/Toker38/FeedemyRaspberryPrinter
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python -m src.main
Restart=on-failure
RestartSec=10
StartLimitInterval=300
StartLimitBurst=5

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=feedemy-printer

# Environment
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1

[Install]
WantedBy=multi-user.target
SERVICE_EOF

systemctl daemon-reload
systemctl enable $SERVICE_NAME > /dev/null 2>&1
info "Servis kuruldu ve etkinleştirildi"

# === Complete ===
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           Kurulum Tamamlandı!                  ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Sonraki adımlar:${NC}"
echo ""
echo "  1. USB yazıcıyı bağlayın"
echo ""
echo "  2. İlk kayıt için çalıştırın:"
echo -e "     ${BLUE}sudo $INSTALL_DIR/venv/bin/python -m src.main${NC}"
echo ""
echo "  3. Admin panelden pairing code alın ve girin"
echo ""
echo "  4. Kayıt tamamlandıktan sonra servisi başlatın:"
echo -e "     ${BLUE}sudo systemctl start $SERVICE_NAME${NC}"
echo ""
echo -e "${YELLOW}Faydalı komutlar:${NC}"
echo "  Logları izle:     journalctl -u $SERVICE_NAME -f"
echo "  Servis durumu:    systemctl status $SERVICE_NAME"
echo "  Servisi durdur:   sudo systemctl stop $SERVICE_NAME"
echo "  Servisi başlat:   sudo systemctl start $SERVICE_NAME"
echo ""
