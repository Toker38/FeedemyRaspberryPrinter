#!/usr/bin/env python3
"""
Feedemy Raspberry Pi Printer Client
Main entry point
"""

import asyncio
import logging
import signal
import sys

from .config_manager import ConfigManager
from .auto_updater import AutoUpdater
from .api_client import FeedemyApiClient, ApiError
from .printer_manager import PrinterManager
from .template_renderer import TemplateRenderer
from .job_store import JobStore
from .job_processor import JobProcessor

# Logging setup
from pathlib import Path
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / 'feedemy-printer.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)


class FeedemyPrinterApp:
    """Ana uygulama"""

    def __init__(self):
        self.config = ConfigManager()
        self.api: FeedemyApiClient = None
        self.printer_manager: PrinterManager = None
        self.job_processor: JobProcessor = None
        self._shutdown_event = asyncio.Event()

    async def run(self) -> None:
        """Uygulamayı çalıştır"""
        logger.info("=" * 50)
        logger.info("Feedemy Printer Client starting...")
        logger.info("=" * 50)

        try:
            # 1. Auto update check
            if self.config.auto_update.enabled:
                self._check_updates()

            # 2. API client oluştur
            self.api = FeedemyApiClient(
                base_url=self.config.api.base_url,
                token=self.config.api.token
            )

            # 3. Register kontrolü
            if not self.config.is_registered():
                await self._do_registration()

            # Token'ı API client'a set et
            self.api.token = self.config.api.token

            # 4. Printer manager başlat
            self.printer_manager = PrinterManager()
            self.printer_manager.start()

            # Yazıcı yoksa USB yazıcı bağlanmasını bekle
            if not self.printer_manager.has_printer():
                logger.warning("No printer detected. Connect a USB printer.")
                # Hotplug dinleyicisi zaten aktif, devam et

            # Yeni tespit edilen yazıcıları API'ye kaydet
            await self._register_new_printers()

            # 5. Job processor başlat
            store = JobStore()
            renderer = TemplateRenderer(
                default_width=self.config.printer.default_width
            )

            self.job_processor = JobProcessor(
                api=self.api,
                store=store,
                renderer=renderer,
                printer_manager=self.printer_manager,
                poll_interval=self.config.polling.interval_seconds
            )

            # Signal handlers
            self._setup_signal_handlers()

            # 6. Ana döngü
            logger.info("Starting job processor...")
            await self.job_processor.run()

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Application error: {e}", exc_info=True)
        finally:
            await self._shutdown()

    def _check_updates(self) -> None:
        """Güncelleme kontrolü"""
        logger.info("Checking for updates...")
        updater = AutoUpdater(branch=self.config.auto_update.branch)

        # Güncelleme varsa restart eder (bu fonksiyondan dönmez)
        updater.check_and_update()

    async def _do_registration(self) -> None:
        """İlk kayıt işlemi - stdin'den pairing code al"""
        logger.info("")
        logger.info("=" * 50)
        logger.info("  DEVICE REGISTRATION REQUIRED")
        logger.info("=" * 50)
        logger.info("")
        logger.info("This device is not registered.")
        logger.info("Please get a pairing code from the admin panel:")
        logger.info("  Admin Panel → Branch → Printers → Generate Pairing Code")
        logger.info("")

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # stdin'den pairing code al
                pairing_code = input("Enter pairing code: ").strip().upper()

                if not pairing_code:
                    logger.warning("Pairing code cannot be empty")
                    continue

                if len(pairing_code) != 6:
                    logger.warning("Pairing code should be 6 characters")
                    continue

                # Device name
                device_name = self.config.device.name
                name_input = input(f"Enter device name [{device_name}]: ").strip()
                if name_input:
                    device_name = name_input

                # Register API call
                logger.info(f"Registering device with code: {pairing_code}...")
                response = await self.api.register(pairing_code, device_name)

                # Token'ı kaydet
                self.config.save_registration(
                    token=response.token,
                    token_id=response.token_id,
                    branch_guid=response.branch_guid
                )
                self.config.update_device_name(device_name)

                logger.info("")
                logger.info("=" * 50)
                logger.info("  REGISTRATION SUCCESSFUL!")
                logger.info("=" * 50)
                logger.info(f"  Branch: {response.branch_guid}")
                logger.info(f"  Token ID: {response.token_id}")
                logger.info("=" * 50)
                logger.info("")

                return

            except ApiError as e:
                logger.error(f"Registration failed: {e.message}")
                if attempt < max_attempts - 1:
                    logger.info(f"Attempts remaining: {max_attempts - attempt - 1}")
                else:
                    logger.error("Max registration attempts reached. Exiting.")
                    sys.exit(1)

    async def _register_new_printers(self) -> None:
        """Tespit edilen yazıcıları API'ye kaydet"""
        printers = self.printer_manager.get_printers()

        for printer in printers:
            try:
                logger.info(f"Registering printer: {printer.printer_model}")
                result = await self.api.add_printer(
                    printer_name=printer.printer_model,
                    device_address=printer.device_address,
                    printer_model=printer.printer_model,
                    connection_type=2  # USB
                )
                logger.info(f"Printer registered: {result.branch_printer_guid}")
            except ApiError as e:
                # Zaten kayıtlı olabilir
                logger.warning(f"Could not register printer: {e.message}")

    def _setup_signal_handlers(self) -> None:
        """SIGTERM ve SIGINT handler'ları"""
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self._handle_shutdown())
            )

    async def _handle_shutdown(self) -> None:
        """Graceful shutdown"""
        logger.info("Shutdown signal received...")
        self._shutdown_event.set()
        if self.job_processor:
            await self.job_processor.stop()

    async def _shutdown(self) -> None:
        """Cleanup"""
        logger.info("Shutting down...")

        if self.printer_manager:
            self.printer_manager.stop()

        if self.api:
            await self.api.close()

        logger.info("Shutdown complete")


def main():
    """Entry point"""
    app = FeedemyPrinterApp()
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
