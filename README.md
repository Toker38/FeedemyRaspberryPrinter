# Feedemy Raspberry Pi Printer Client

Feedemy sipariş yazdırma client'ı. Raspberry Pi üzerinde çalışır, USB termal yazıcılara sipariş fişi yazdırır.

## Özellikler

- USB yazıcı hotplug tespiti (pyudev)
- Otomatik güncelleme (git pull on startup)
- Duplicate job önleme (SQLite)
- Türkçe karakter desteği (CP857)
- systemd service olarak çalışma

## Kurulum

### 1. Repo'yu klonla

```bash
cd /home/pi
git clone https://github.com/feedemy/feedemy-raspberry-printer.git
cd feedemy-raspberry-printer
```

### 2. Kurulum script'ini çalıştır

```bash
bash scripts/install.sh
```

### 3. Config ayarla

```bash
nano config/config.json
```

API URL'ini ayarla:
```json
{
  "api": {
    "base_url": "https://api.feedemy.com",
    "token": null
  }
}
```

### 4. İlk çalıştırma (kayıt)

```bash
python3 -m src.main
```

Admin panel'den pairing code al:
1. Admin Panel → Şube → Yazıcılar → Pairing Code Oluştur
2. 6 haneli kodu terminale gir
3. Kayıt başarılı olunca service'i başlat

### 5. Service başlat

```bash
sudo systemctl start feedemy-printer
```

## Kullanım

### Service komutları

```bash
# Durumu kontrol et
sudo systemctl status feedemy-printer

# Logları izle
journalctl -u feedemy-printer -f

# Restart
sudo systemctl restart feedemy-printer

# Durdur
sudo systemctl stop feedemy-printer
```

### Manuel çalıştırma

```bash
cd /home/pi/feedemy-raspberry-printer
python3 -m src.main
```

### Test yazdırma

Admin panel'den test yazdırma gönderilebilir:
- Admin Panel → Şube → Yazıcılar → Test Yazdır

## Proje Yapısı

```
feedemy-raspberry-printer/
├── src/
│   ├── main.py               # Entry point
│   ├── config_manager.py     # Config yönetimi
│   ├── api_client.py         # Backend API client
│   ├── printer_detector.py   # USB yazıcı tespiti
│   ├── printer_manager.py    # Yazıcıya gönderme
│   ├── template_renderer.py  # JSON → ESC/POS
│   ├── job_processor.py      # Job işleme döngüsü
│   ├── job_store.py          # SQLite duplicate check
│   └── auto_updater.py       # Git pull güncelleme
├── templates/
│   └── escpos_commands.py    # ESC/POS komutları
├── scripts/
│   ├── install.sh            # Kurulum script'i
│   └── feedemy-printer.service
├── config/
│   └── config.json           # Ayarlar
├── data/
│   └── jobs.db               # İşlenen job'lar (SQLite)
├── requirements.txt
└── README.md
```

## Gereksinimler

- Raspberry Pi (herhangi bir model)
- Raspbian / Raspberry Pi OS
- Python 3.9+
- USB Termal Yazıcı (ESC/POS uyumlu)

## Desteklenen Yazıcılar

ESC/POS protokolü kullanan tüm termal yazıcılar:
- Epson TM-T88
- Epson TM-T20
- Star TSP100
- Bixolon SRP-350
- ve diğerleri...

## Sorun Giderme

### Yazıcı tespit edilmiyor

```bash
# USB cihazları listele
lsusb

# Yazıcı device node
ls -la /dev/usb/lp*

# İzin sorunu varsa
sudo chmod 666 /dev/usb/lp0
```

### Türkçe karakterler bozuk

Yazıcının CP857 (Turkish) code page'i desteklediğinden emin ol.

### Registration başarısız

- Pairing code'un süresi dolmuş olabilir (5 dakika)
- Admin panel'den yeni kod al

## Lisans

Proprietary - Feedemy
