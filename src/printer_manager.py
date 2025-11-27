"""
Printer Manager - USB yazıcıya veri gönderme
"""

import logging
from typing import Optional, Dict
from dataclasses import dataclass

from .printer_detector import USBPrinter, USBPrinterDetector

logger = logging.getLogger(__name__)


@dataclass
class PrintResult:
    """Yazdırma sonucu"""
    success: bool
    error: Optional[str] = None
    bytes_written: int = 0


class PrinterManager:
    """USB yazıcı yönetimi ve yazdırma"""

    def __init__(self):
        self._printers: Dict[str, USBPrinter] = {}  # device_path → USBPrinter
        self._detector = USBPrinterDetector(
            on_printer_added=self._on_printer_added,
            on_printer_removed=self._on_printer_removed
        )
        self._default_printer: Optional[str] = None

    def start(self) -> None:
        """Başlangıçta yazıcıları tara ve monitoring başlat"""
        # Mevcut yazıcıları tara
        printers = self._detector.get_connected_printers()
        for printer in printers:
            self._printers[printer.device_path] = printer
            if self._default_printer is None:
                self._default_printer = printer.device_path

        # Hotplug monitoring başlat
        self._detector.start_monitoring()

    def stop(self) -> None:
        """Monitoring durdur"""
        self._detector.stop_monitoring()

    def _on_printer_added(self, printer: USBPrinter) -> None:
        """Yeni yazıcı eklendi callback"""
        self._printers[printer.device_path] = printer
        if self._default_printer is None:
            self._default_printer = printer.device_path
        logger.info(f"Printer registered: {printer.printer_model} at {printer.device_path}")

    def _on_printer_removed(self, device_path: str) -> None:
        """Yazıcı çıkarıldı callback"""
        if device_path in self._printers:
            del self._printers[device_path]
        if self._default_printer == device_path:
            # Başka yazıcı varsa onu default yap
            self._default_printer = next(iter(self._printers.keys()), None)
        logger.info(f"Printer removed: {device_path}")

    def get_printers(self) -> list:
        """Bağlı yazıcıları listele"""
        return list(self._printers.values())

    def has_printer(self) -> bool:
        """En az bir yazıcı bağlı mı?"""
        return len(self._printers) > 0

    def get_default_printer(self) -> Optional[USBPrinter]:
        """Varsayılan yazıcıyı al"""
        if self._default_printer:
            return self._printers.get(self._default_printer)
        return None

    def set_default_printer(self, device_path: str) -> bool:
        """Varsayılan yazıcıyı ayarla"""
        if device_path in self._printers:
            self._default_printer = device_path
            return True
        return False

    def print_data(self, data: bytes, device_path: str = None) -> PrintResult:
        """
        Yazıcıya veri gönder

        Args:
            data: ESC/POS byte sequence
            device_path: Hedef yazıcı (None = default)

        Returns:
            PrintResult
        """
        # Yazıcı seç
        target_path = device_path or self._default_printer

        if not target_path:
            return PrintResult(
                success=False,
                error="No printer available"
            )

        if target_path not in self._printers:
            return PrintResult(
                success=False,
                error=f"Printer not found: {target_path}"
            )

        # Yazıcıya gönder
        try:
            with open(target_path, 'wb') as printer:
                bytes_written = printer.write(data)
                printer.flush()

            logger.info(f"Printed {bytes_written} bytes to {target_path}")
            return PrintResult(
                success=True,
                bytes_written=bytes_written
            )

        except PermissionError:
            error = f"Permission denied: {target_path}. Run: sudo chmod 666 {target_path}"
            logger.error(error)
            return PrintResult(success=False, error=error)

        except FileNotFoundError:
            error = f"Printer not found: {target_path}"
            logger.error(error)
            # Yazıcı listesinden kaldır
            self._on_printer_removed(target_path)
            return PrintResult(success=False, error=error)

        except Exception as e:
            error = f"Print error: {e}"
            logger.error(error)
            return PrintResult(success=False, error=error)

    def test_print(self, device_path: str = None) -> PrintResult:
        """Test yazdırma"""
        from templates.escpos_commands import (
            INIT, SELECT_CHARSET, ALIGN_CENTER, BOLD_ON, BOLD_OFF,
            LF, feed_lines, CUT_FULL, encode_turkish
        )

        test_data = bytearray()
        test_data.extend(INIT)
        test_data.extend(SELECT_CHARSET)
        test_data.extend(ALIGN_CENTER)
        test_data.extend(BOLD_ON)
        test_data.extend(encode_turkish("=== TEST YAZDIRMA ==="))
        test_data.extend(LF)
        test_data.extend(BOLD_OFF)
        test_data.extend(encode_turkish("Türkçe: ğüşıöç ĞÜŞİÖÇ"))
        test_data.extend(LF)
        test_data.extend(encode_turkish("Feedemy Printer OK"))
        test_data.extend(LF)
        test_data.extend(feed_lines(3))
        test_data.extend(CUT_FULL)

        return self.print_data(bytes(test_data), device_path)
