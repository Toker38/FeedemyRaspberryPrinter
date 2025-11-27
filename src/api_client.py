"""
Feedemy API Client
Backend ile iletişim için HTTP client
"""

import aiohttp
import logging
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RegisterResponse:
    token: str
    token_id: str
    branch_guid: str
    device_name: Optional[str]
    issued_at: str
    expires_at: Optional[str]


@dataclass
class CreatedPrinter:
    branch_printer_guid: str
    printer_name: str
    device_address: Optional[str]


@dataclass
class PendingJob:
    job_guid: str
    order_guid: str
    priority: int
    created_at: str


@dataclass
class JobDetail:
    job_guid: str
    order_guid: str
    print_template_guid: str
    print_data: str  # JSON string
    template_content: str  # JSON string
    template_version: int


@dataclass
class FailResponse:
    will_retry: bool


class ApiError(Exception):
    """API hatası"""
    def __init__(self, message: str, error_code: Optional[str] = None):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class FeedemyApiClient:
    """Feedemy Backend API Client"""

    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazy session oluştur"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Session'ı kapat"""
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_headers(self, with_auth: bool = True) -> dict:
        """HTTP headers"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if with_auth and self.token:
            headers["Authorization"] = f"PrinterDevice {self.token}"
        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[dict] = None,
        params: Optional[dict] = None,
        with_auth: bool = True
    ) -> dict:
        """HTTP request yap ve response parse et"""
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers(with_auth)

        try:
            async with session.request(
                method,
                url,
                json=json_data,
                params=params,
                headers=headers
            ) as response:
                data = await response.json()

                # ApiResponse format: { success, message, data, errorCode }
                if not data.get("success", False):
                    raise ApiError(
                        message=data.get("message", "Unknown error"),
                        error_code=data.get("errorCode")
                    )

                return data.get("data")

        except aiohttp.ClientError as e:
            logger.error(f"HTTP error: {e}")
            raise ApiError(f"Connection error: {e}")

    # === Registration ===

    async def register(self, pairing_code: str, device_name: str) -> RegisterResponse:
        """
        Pairing code ile cihaz kaydı
        Token döner - config'e kaydedilmeli
        """
        data = await self._request(
            "POST",
            "/api/printer-device/register",
            json_data={
                "pairingCode": pairing_code,
                "deviceName": device_name
            },
            with_auth=False  # Register'da token yok
        )

        return RegisterResponse(
            token=data["token"],
            token_id=data["tokenId"],
            branch_guid=data["branchGuid"],
            device_name=data.get("deviceName"),
            issued_at=data["issuedAt"],
            expires_at=data.get("expiresAt")
        )

    # === Printer Management ===

    async def add_printer(
        self,
        printer_name: str,
        device_address: str = None,
        printer_model: str = None,
        connection_type: int = 1,  # 1 = Network, 2 = USB
        sort_order: int = None
    ) -> CreatedPrinter:
        """Yeni yazıcı ekle"""
        json_data = {
            "printerName": printer_name,
            "connectionType": connection_type
        }
        if device_address:
            json_data["deviceAddress"] = device_address
        if printer_model:
            json_data["printerModel"] = printer_model
        if sort_order is not None:
            json_data["sortOrder"] = sort_order

        data = await self._request(
            "POST",
            "/api/printer-device/printers",
            json_data=json_data
        )

        return CreatedPrinter(
            branch_printer_guid=data["branchPrinterGuid"],
            printer_name=data["printerName"],
            device_address=data.get("deviceAddress")
        )

    # === Job Polling ===

    async def get_pending_jobs(self, take: int = 10) -> List[PendingJob]:
        """Bekleyen jobları listele"""
        data = await self._request(
            "GET",
            "/api/printer-device/jobs/pending",
            params={"take": take}
        )

        if not data:
            return []

        return [
            PendingJob(
                job_guid=job["jobGuid"],
                order_guid=job["orderGuid"],
                priority=job["priority"],
                created_at=job["createdAt"]
            )
            for job in data
        ]

    async def claim_next_job(self) -> Optional[JobDetail]:
        """Sonraki job'ı claim et ve detayını al"""
        data = await self._request(
            "POST",
            "/api/printer-device/jobs/claim"
        )

        if not data:
            return None

        return JobDetail(
            job_guid=data["jobGuid"],
            order_guid=data["orderGuid"],
            print_template_guid=data["printTemplateGuid"],
            print_data=data["printData"],
            template_content=data.get("templateContent", "{}"),
            template_version=data.get("templateVersion", 1)
        )

    async def get_job_detail(self, job_guid: str) -> Optional[JobDetail]:
        """Job detayını al (retry için)"""
        try:
            data = await self._request(
                "GET",
                f"/api/printer-device/jobs/{job_guid}"
            )

            if not data:
                return None

            return JobDetail(
                job_guid=data["jobGuid"],
                order_guid=data["orderGuid"],
                print_template_guid=data["printTemplateGuid"],
                print_data=data["printData"],
                template_content=data.get("templateContent", "{}"),
                template_version=data.get("templateVersion", 1)
            )
        except ApiError:
            return None

    # === Job Status ===

    async def complete_job(self, job_guid: str) -> bool:
        """Job'ı tamamlandı olarak işaretle"""
        try:
            await self._request(
                "POST",
                f"/api/printer-device/jobs/{job_guid}/complete"
            )
            return True
        except ApiError as e:
            logger.error(f"Failed to complete job {job_guid}: {e.message}")
            return False

    async def fail_job(self, job_guid: str, error_message: str) -> FailResponse:
        """Job'ı başarısız olarak işaretle"""
        data = await self._request(
            "POST",
            f"/api/printer-device/jobs/{job_guid}/fail",
            json_data={"errorMessage": error_message}
        )

        return FailResponse(
            will_retry=data.get("willRetry", False) if data else False
        )
