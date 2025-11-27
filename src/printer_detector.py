"""
Printer Detector - pyudev ile USB yazıcı tespiti
Linux'ta USB hotplug olaylarını dinler
"""

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional
import threading

logger = logging.getLogger(__name__)

# pyudev sadece Linux'ta çalışır
try:
    import pyudev
    PYUDEV_AVAILABLE = True
except ImportError:
    PYUDEV_AVAILABLE = False
    logger.warning("pyudev not available - USB detection disabled")


# Bilinen yazıcı modelleri (vendor_id, product_id) -> (vendor, model)
KNOWN_PRINTER_MODELS = {
    # Epson
    ("04b8", "0e03"): ("Epson", "TM-T20"),
    ("04b8", "0e15"): ("Epson", "TM-T88V"),
    ("04b8", "0e28"): ("Epson", "TM-T88VI"),
    ("04b8", "0202"): ("Epson", "TM-T20II"),
    ("04b8", "0e27"): ("Epson", "TM-M30"),
    # Xprinter
    ("0483", "5720"): ("Xprinter", "XP-58"),
    ("0483", "5740"): ("Xprinter", "XP-80"),
    ("0483", "5743"): ("Xprinter", "XP-N160I"),
    # Rongta
    ("0fe6", "811e"): ("Rongta", "RP80"),
    # Goojprt
    ("1504", "0006"): ("Goojprt", "PT-210"),
    # Generic POS
    ("0416", "5011"): ("WinPOS", "WP-T810"),
    ("28e9", "0289"): ("Generic", "POS-58"),
}


@dataclass
class USBPrinter:
    """Tespit edilen USB yazıcı bilgisi"""
    device_path: str           # /dev/usb/lp0
    vendor_id: str             # 04b8 (Epson)
    product_id: str            # 0e03
    manufacturer: Optional[str]
    product: Optional[str]
    serial: Optional[str]

    @property
    def device_address(self) -> str:
        """API'ye gönderilecek device address"""
        return self.device_path

    @property
    def vendor_name(self) -> str:
        """Yazıcı üreticisi"""
        # Önce lookup table'dan bak
        key = (self.vendor_id.lower(), self.product_id.lower())
        if key in KNOWN_PRINTER_MODELS:
            return KNOWN_PRINTER_MODELS[key][0]
        # Manufacturer string varsa kullan
        if self.manufacturer:
            return self.manufacturer
        # Vendor ID'den tahmin et
        vendor_map = {
            "04b8": "Epson",
            "0416": "WinPOS",
            "0483": "Xprinter",
            "0fe6": "Rongta",
            "1504": "Goojprt",
            "28e9": "Generic POS",
        }
        return vendor_map.get(self.vendor_id.lower(), "Unknown")

    @property
    def printer_model(self) -> str:
        """Yazıcı model adı"""
        # Önce lookup table'dan bak
        key = (self.vendor_id.lower(), self.product_id.lower())
        if key in KNOWN_PRINTER_MODELS:
            vendor, model = KNOWN_PRINTER_MODELS[key]
            return f"{vendor} {model}"

        # Product string varsa ve anlamlıysa kullan
        if self.product:
            # Yıl gibi anlamsız değerleri filtrele
            if not self.product.isdigit() and len(self.product) > 2:
                vendor = self.vendor_name
                return f"{vendor} {self.product}"

        # Fallback
        return f"{self.vendor_name} Thermal Printer"


class USBPrinterDetector:
    """USB yazıcı tespit ve hotplug monitoring"""

    # Bilinen termal yazıcı vendor ID'leri
    KNOWN_PRINTER_VENDORS = {
        "04b8": "Epson",
        "0416": "Winbond (POS)",
        "0483": "STMicroelectronics (POS)",
        "0525": "Netchip (USB gadget)",
        "067b": "Prolific",
        "0fe6": "ICS (POS printers)",
        "1504": "Goojprt",
        "1fc9": "NXP (POS)",
        "28e9": "Printer vendor",
        "4348": "WCH (CH340)",
    }

    def __init__(
        self,
        on_printer_added: Optional[Callable[[USBPrinter], None]] = None,
        on_printer_removed: Optional[Callable[[str], None]] = None
    ):
        self.on_printer_added = on_printer_added
        self.on_printer_removed = on_printer_removed
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        if PYUDEV_AVAILABLE:
            self._context = pyudev.Context()
        else:
            self._context = None

    def get_connected_printers(self) -> List[USBPrinter]:
        """Bağlı tüm USB yazıcıları listele"""
        if not PYUDEV_AVAILABLE:
            logger.warning("pyudev not available")
            return []

        printers = []

        # USB printer class devices
        for device in self._context.list_devices(subsystem='usb', DEVTYPE='usb_device'):
            if self._is_printer(device):
                printer = self._device_to_printer(device)
                if printer:
                    printers.append(printer)

        # usblp subsystem (printer specific)
        for device in self._context.list_devices(subsystem='usblp'):
            printer = self._usblp_to_printer(device)
            if printer:
                # Duplicate check
                if not any(p.device_path == printer.device_path for p in printers):
                    printers.append(printer)

        logger.info(f"Found {len(printers)} USB printer(s)")
        return printers

    def _is_printer(self, device) -> bool:
        """Device yazıcı mı kontrol et"""
        # USB class 7 = Printer
        bInterfaceClass = device.get("bInterfaceClass")
        if bInterfaceClass == "07":
            return True

        # Vendor ID check
        vendor_id = device.get("ID_VENDOR_ID", "").lower()
        if vendor_id in self.KNOWN_PRINTER_VENDORS:
            return True

        # Product string check
        product = device.get("ID_MODEL", "").lower()
        if any(kw in product for kw in ["printer", "pos", "receipt", "thermal"]):
            return True

        return False

    def _device_to_printer(self, device) -> Optional[USBPrinter]:
        """pyudev device → USBPrinter"""
        try:
            vendor_id = device.get("ID_VENDOR_ID", "")
            product_id = device.get("ID_MODEL_ID", "")

            # Device path bul
            device_path = None
            for child in device.children:
                if child.subsystem == "usblp":
                    device_path = child.device_node
                    break

            if not device_path:
                # Fallback: /dev/usb/lpX ara
                import glob
                lp_devices = glob.glob("/dev/usb/lp*")
                if lp_devices:
                    device_path = lp_devices[0]

            if not device_path:
                return None

            return USBPrinter(
                device_path=device_path,
                vendor_id=vendor_id,
                product_id=product_id,
                manufacturer=device.get("ID_VENDOR"),
                product=device.get("ID_MODEL"),
                serial=device.get("ID_SERIAL_SHORT")
            )
        except Exception as e:
            logger.error(f"Error parsing device: {e}")
            return None

    def _usblp_to_printer(self, device) -> Optional[USBPrinter]:
        """usblp device → USBPrinter"""
        try:
            device_path = device.device_node
            if not device_path:
                return None

            parent = device.parent
            while parent:
                vendor_id = parent.get("ID_VENDOR_ID")
                if vendor_id:
                    break
                parent = parent.parent

            return USBPrinter(
                device_path=device_path,
                vendor_id=parent.get("ID_VENDOR_ID", "") if parent else "",
                product_id=parent.get("ID_MODEL_ID", "") if parent else "",
                manufacturer=parent.get("ID_VENDOR") if parent else None,
                product=parent.get("ID_MODEL") if parent else None,
                serial=parent.get("ID_SERIAL_SHORT") if parent else None
            )
        except Exception as e:
            logger.error(f"Error parsing usblp device: {e}")
            return None

    def start_monitoring(self) -> None:
        """Hotplug monitoring başlat"""
        if not PYUDEV_AVAILABLE:
            logger.warning("pyudev not available - monitoring disabled")
            return

        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("Monitoring already running")
            return

        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="USBPrinterMonitor"
        )
        self._monitor_thread.start()
        logger.info("USB printer monitoring started")

    def stop_monitoring(self) -> None:
        """Hotplug monitoring durdur"""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)
        logger.info("USB printer monitoring stopped")

    def _monitor_loop(self) -> None:
        """Hotplug event loop"""
        monitor = pyudev.Monitor.from_netlink(self._context)
        monitor.filter_by(subsystem='usblp')

        for device in iter(monitor.poll, None):
            if self._stop_event.is_set():
                break

            if device.action == 'add':
                printer = self._usblp_to_printer(device)
                if printer and self.on_printer_added:
                    logger.info(f"USB printer added: {printer.device_path}")
                    self.on_printer_added(printer)

            elif device.action == 'remove':
                device_path = device.device_node
                if device_path and self.on_printer_removed:
                    logger.info(f"USB printer removed: {device_path}")
                    self.on_printer_removed(device_path)
