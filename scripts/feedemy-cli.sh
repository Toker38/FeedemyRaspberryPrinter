#!/bin/bash
#
# Feedemy Printer CLI
# Enterprise management tool for Feedemy Printer Service
#

set -e

# === Configuration ===
INSTALL_DIR="/opt/feedemy-printer"
SERVICE_NAME="feedemy-printer"
CONFIG_FILE="$INSTALL_DIR/config/config.json"
DB_FILE="$INSTALL_DIR/data/jobs.db"
PYTHON="$INSTALL_DIR/venv/bin/python"

# === Colors ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# === Helper Functions ===
info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

check_install() {
    if [ ! -d "$INSTALL_DIR" ]; then
        error "Feedemy Printer kurulu değil. Önce kurulum yapın."
    fi
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        error "Bu komut root yetkisi gerektirir: sudo feedemy $1"
    fi
}

# === Commands ===

cmd_start() {
    check_root "start"
    systemctl start $SERVICE_NAME
    info "Servis başlatıldı"
    systemctl status $SERVICE_NAME --no-pager
}

cmd_stop() {
    check_root "stop"
    systemctl stop $SERVICE_NAME
    info "Servis durduruldu"
}

cmd_restart() {
    check_root "restart"
    systemctl restart $SERVICE_NAME
    info "Servis yeniden başlatıldı"
}

cmd_status() {
    echo -e "${CYAN}=== Servis Durumu ===${NC}"
    systemctl status $SERVICE_NAME --no-pager || true

    echo ""
    echo -e "${CYAN}=== Config ===${NC}"
    if [ -f "$CONFIG_FILE" ]; then
        cat "$CONFIG_FILE" | $PYTHON -m json.tool 2>/dev/null || cat "$CONFIG_FILE"
    else
        warn "Config dosyası bulunamadı"
    fi
}

cmd_logs() {
    local lines="${1:-50}"
    journalctl -u $SERVICE_NAME -n "$lines" --no-pager
}

cmd_logs_follow() {
    journalctl -u $SERVICE_NAME -f
}

cmd_register() {
    check_root "register"
    check_install

    # Stop service if running
    systemctl stop $SERVICE_NAME 2>/dev/null || true

    cd "$INSTALL_DIR"
    $PYTHON -m src.main
}

cmd_config_show() {
    check_install
    echo -e "${CYAN}=== Mevcut Config ===${NC}"
    if [ -f "$CONFIG_FILE" ]; then
        cat "$CONFIG_FILE" | $PYTHON -m json.tool 2>/dev/null || cat "$CONFIG_FILE"
    else
        warn "Config dosyası bulunamadı"
    fi
}

cmd_config_set() {
    check_root "config set"
    check_install

    local key="$1"
    local value="$2"

    if [ -z "$key" ] || [ -z "$value" ]; then
        error "Kullanım: feedemy config set <key> <value>"
    fi

    # Ensure config directory exists
    mkdir -p "$INSTALL_DIR/config"

    # Create default config if not exists
    if [ ! -f "$CONFIG_FILE" ]; then
        cat > "$CONFIG_FILE" << 'DEFAULTCONFIG'
{
  "api": {
    "base_url": "https://api.feedemy.com",
    "token": null
  },
  "device": {
    "name": "Raspberry-001",
    "branch_guid": null,
    "token_id": null
  },
  "polling": {
    "interval_seconds": 5,
    "batch_size": 10
  },
  "printer": {
    "default_width": 48,
    "charset": "cp857"
  },
  "auto_update": {
    "enabled": true,
    "branch": "main"
  }
}
DEFAULTCONFIG
    fi

    # Update config using Python
    $PYTHON << PYSCRIPT
import json

config_file = "$CONFIG_FILE"
key = "$key"
value = "$value"

with open(config_file, 'r') as f:
    config = json.load(f)

# Parse nested keys (e.g., "api.base_url")
keys = key.split('.')
obj = config
for k in keys[:-1]:
    if k not in obj:
        obj[k] = {}
    obj = obj[k]

# Try to parse value as JSON (for booleans, numbers, null)
try:
    parsed_value = json.loads(value)
except:
    parsed_value = value

obj[keys[-1]] = parsed_value

with open(config_file, 'w') as f:
    json.dump(config, f, indent=2, ensure_ascii=False)

print(f"✓ {key} = {parsed_value}")
PYSCRIPT
}

cmd_config_api() {
    check_root "config api"
    local url="$1"
    if [ -z "$url" ]; then
        error "Kullanım: feedemy config api <url>"
    fi
    cmd_config_set "api.base_url" "\"$url\""
    info "API URL ayarlandı: $url"
}

cmd_config_name() {
    check_root "config name"
    local name="$1"
    if [ -z "$name" ]; then
        error "Kullanım: feedemy config name <device-name>"
    fi
    cmd_config_set "device.name" "\"$name\""
    info "Cihaz adı ayarlandı: $name"
}

cmd_db_jobs() {
    check_install

    if [ ! -f "$DB_FILE" ]; then
        warn "Veritabanı dosyası bulunamadı: $DB_FILE"
        return
    fi

    echo -e "${CYAN}=== Son İşlenen Job'lar ===${NC}"
    sqlite3 -header -column "$DB_FILE" "
        SELECT
            job_guid,
            status,
            datetime(processed_at) as processed_at,
            substr(error, 1, 50) as error
        FROM processed_jobs
        ORDER BY processed_at DESC
        LIMIT 20;
    " 2>/dev/null || warn "SQLite sorgusu başarısız"
}

cmd_db_stats() {
    check_install

    if [ ! -f "$DB_FILE" ]; then
        warn "Veritabanı dosyası bulunamadı: $DB_FILE"
        return
    fi

    echo -e "${CYAN}=== Job İstatistikleri ===${NC}"
    sqlite3 -header -column "$DB_FILE" "
        SELECT
            status,
            COUNT(*) as count,
            MAX(datetime(processed_at)) as last_processed
        FROM processed_jobs
        GROUP BY status;
    " 2>/dev/null || warn "SQLite sorgusu başarısız"

    echo ""
    echo -e "${CYAN}=== Toplam ===${NC}"
    sqlite3 "$DB_FILE" "SELECT COUNT(*) || ' job işlendi' FROM processed_jobs;" 2>/dev/null || true
}

cmd_db_clear() {
    check_root "db clear"
    check_install

    if [ ! -f "$DB_FILE" ]; then
        warn "Veritabanı dosyası bulunamadı"
        return
    fi

    read -p "Tüm job kayıtları silinecek. Emin misiniz? (y/N) " confirm
    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        sqlite3 "$DB_FILE" "DELETE FROM processed_jobs;"
        info "Tüm job kayıtları silindi"
    else
        info "İptal edildi"
    fi
}

cmd_update() {
    check_root "update"
    check_install

    info "Güncelleme kontrol ediliyor..."

    cd "$INSTALL_DIR"

    # Fetch updates
    git fetch origin main --quiet

    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse origin/main)

    if [ "$LOCAL" = "$REMOTE" ]; then
        info "Zaten güncel"
        return
    fi

    info "Güncelleme bulundu, indiriliyor..."

    # Stop service
    systemctl stop $SERVICE_NAME 2>/dev/null || true

    # Pull updates
    git reset --hard origin/main --quiet

    # Update dependencies
    $INSTALL_DIR/venv/bin/pip install --quiet -r requirements.txt

    # Restart service
    systemctl start $SERVICE_NAME

    info "Güncelleme tamamlandı ve servis yeniden başlatıldı"
}

cmd_uninstall() {
    check_root "uninstall"

    read -p "Feedemy Printer tamamen kaldırılacak. Emin misiniz? (y/N) " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        info "İptal edildi"
        return
    fi

    info "Servis durduruluyor..."
    systemctl stop $SERVICE_NAME 2>/dev/null || true
    systemctl disable $SERVICE_NAME 2>/dev/null || true

    info "Dosyalar siliniyor..."
    rm -f /etc/systemd/system/$SERVICE_NAME.service
    rm -f /etc/udev/rules.d/99-feedemy-printer.rules
    rm -f /usr/local/bin/feedemy
    rm -rf $INSTALL_DIR

    systemctl daemon-reload
    udevadm control --reload-rules

    info "Feedemy Printer kaldırıldı"
}

cmd_version() {
    check_install
    cd "$INSTALL_DIR"

    echo -e "${CYAN}Feedemy Printer CLI${NC}"
    echo "Kurulum: $INSTALL_DIR"
    echo -n "Versiyon: "
    git describe --tags 2>/dev/null || git rev-parse --short HEAD
    echo -n "Branch: "
    git branch --show-current
}

cmd_help() {
    echo -e "${CYAN}Feedemy Printer CLI${NC}"
    echo ""
    echo -e "${YELLOW}Kullanım:${NC} feedemy <command> [options]"
    echo ""
    echo -e "${YELLOW}Servis Komutları:${NC}"
    echo "  start              Servisi başlat"
    echo "  stop               Servisi durdur"
    echo "  restart            Servisi yeniden başlat"
    echo "  status             Servis durumu ve config göster"
    echo "  logs [n]           Son n log satırı (varsayılan: 50)"
    echo "  logs -f            Logları canlı izle"
    echo ""
    echo -e "${YELLOW}Kurulum & Kayıt:${NC}"
    echo "  register           Pairing code ile cihaz kaydı (interaktif)"
    echo "  update             Yazılımı güncelle"
    echo "  uninstall          Tamamen kaldır"
    echo ""
    echo -e "${YELLOW}Config Komutları:${NC}"
    echo "  config show        Mevcut config'i göster"
    echo "  config set <k> <v> Config değeri ayarla (örn: api.base_url)"
    echo "  config api <url>   API URL ayarla"
    echo "  config name <name> Cihaz adı ayarla"
    echo ""
    echo -e "${YELLOW}Veritabanı Komutları:${NC}"
    echo "  db jobs            Son işlenen job'ları listele"
    echo "  db stats           Job istatistikleri"
    echo "  db clear           Tüm job kayıtlarını sil"
    echo ""
    echo -e "${YELLOW}Diğer:${NC}"
    echo "  version            Versiyon bilgisi"
    echo "  help               Bu yardım mesajı"
    echo ""
    echo -e "${YELLOW}Örnekler:${NC}"
    echo "  sudo feedemy config api https://api.feedemy.com"
    echo "  sudo feedemy config name Kitchen-Printer-01"
    echo "  sudo feedemy register"
    echo "  sudo feedemy start"
    echo "  feedemy logs -f"
}

# === Main ===
case "${1:-help}" in
    start)      cmd_start ;;
    stop)       cmd_stop ;;
    restart)    cmd_restart ;;
    status)     cmd_status ;;
    logs)
        if [ "$2" = "-f" ]; then
            cmd_logs_follow
        else
            cmd_logs "${2:-50}"
        fi
        ;;
    register)   cmd_register ;;
    config)
        case "${2:-show}" in
            show)   cmd_config_show ;;
            set)    cmd_config_set "$3" "$4" ;;
            api)    cmd_config_api "$3" ;;
            name)   cmd_config_name "$3" ;;
            *)      error "Bilinmeyen config komutu: $2" ;;
        esac
        ;;
    db)
        case "${2:-jobs}" in
            jobs)   cmd_db_jobs ;;
            stats)  cmd_db_stats ;;
            clear)  cmd_db_clear ;;
            *)      error "Bilinmeyen db komutu: $2" ;;
        esac
        ;;
    update)     cmd_update ;;
    uninstall)  cmd_uninstall ;;
    version|-v|--version) cmd_version ;;
    help|-h|--help) cmd_help ;;
    *)          error "Bilinmeyen komut: $1. 'feedemy help' yazın." ;;
esac
