"""
Job Processor - Ana iş döngüsü
API'den job al, render et, yazdır, raporla
"""

import asyncio
import logging
from typing import Optional

from .api_client import FeedemyApiClient, JobDetail, ApiError
from .job_store import JobStore
from .template_renderer import TemplateRenderer
from .printer_manager import PrinterManager

logger = logging.getLogger(__name__)


class JobProcessor:
    """Print job işleme döngüsü"""

    def __init__(
        self,
        api: FeedemyApiClient,
        store: JobStore,
        renderer: TemplateRenderer,
        printer_manager: PrinterManager,
        poll_interval: int = 5
    ):
        self.api = api
        self.store = store
        self.renderer = renderer
        self.printer_manager = printer_manager
        self.poll_interval = poll_interval
        self._running = False

    async def run(self) -> None:
        """Ana işleme döngüsü"""
        self._running = True
        logger.info(f"Job processor started (poll interval: {self.poll_interval}s)")

        # Eski kayıtları temizle
        self.store.cleanup_old(days=7)

        while self._running:
            try:
                await self._process_next_job()
            except Exception as e:
                logger.error(f"Job processing error: {e}")

            await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        """İşleme döngüsünü durdur"""
        self._running = False
        logger.info("Job processor stopping...")

    async def _process_next_job(self) -> None:
        """Sonraki job'ı işle"""
        # Yazıcı bağlı değilse bekle
        if not self.printer_manager.has_printer():
            logger.debug("No printer connected, waiting...")
            return

        # Job claim et
        job = await self._claim_job()
        if not job:
            return  # Job yok

        job_guid = job.job_guid
        logger.info(f"Processing job: {job_guid}")

        # Daha önce işlendi mi? (duplicate check)
        if self.store.is_processed(job_guid):
            logger.warning(f"Job already processed locally: {job_guid}")
            # Backend'e complete gönder (idempotent)
            await self.api.complete_job(job_guid)
            return

        # Template render et
        escpos_data = self._render_job(job)
        if not escpos_data:
            await self._fail_job(job_guid, "Template render failed")
            return

        # Yazdır
        result = self.printer_manager.print_data(escpos_data)

        if result.success:
            await self._complete_job(job_guid)
        else:
            await self._fail_job(job_guid, result.error or "Print failed")

    async def _claim_job(self) -> Optional[JobDetail]:
        """API'den job claim et"""
        try:
            job = await self.api.claim_next_job()
            return job
        except ApiError as e:
            if "No pending jobs" not in e.message:
                logger.error(f"Failed to claim job: {e.message}")
            return None

    def _render_job(self, job: JobDetail) -> Optional[bytes]:
        """Job'ı ESC/POS bytes'a çevir"""
        try:
            result = self.renderer.render(
                template_json=job.template_content,
                data_json=job.print_data
            )
            logger.debug(f"Rendered {len(result)} bytes for job {job.job_guid}")
            return result
        except Exception as e:
            logger.error(f"Render error for job {job.job_guid}: {e}")
            return None

    async def _complete_job(self, job_guid: str) -> None:
        """Job'ı başarılı olarak işaretle"""
        # SQLite'a kaydet
        self.store.mark_completed(job_guid)

        # API'ye bildir
        success = await self.api.complete_job(job_guid)
        if success:
            logger.info(f"Job completed: {job_guid}")
        else:
            logger.warning(f"Job printed but API notification failed: {job_guid}")

    async def _fail_job(self, job_guid: str, error: str) -> None:
        """Job'ı başarısız olarak işaretle"""
        # SQLite'a kaydet
        self.store.mark_failed(job_guid, error)

        # API'ye bildir
        try:
            response = await self.api.fail_job(job_guid, error)
            if response.will_retry:
                logger.warning(f"Job failed (will retry): {job_guid} - {error}")
            else:
                logger.error(f"Job failed permanently: {job_guid} - {error}")
        except ApiError as e:
            logger.error(f"Failed to report job failure: {e.message}")
