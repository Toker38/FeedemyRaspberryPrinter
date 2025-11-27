"""
Feedemy API Client
Backend ile iletişim için HTTP client
"""

import asyncio
import aiohttp
import logging
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds (exponential backoff)


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
    """Feedemy Backend API Client with retry and timeout support"""

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries
        self._session: Optional[aiohttp.ClientSession] = None
        self._timeout_config = aiohttp.ClientTimeout(total=timeout)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazy session oluştur with connection pooling"""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=10,  # max connections
                limit_per_host=5,
                ttl_dns_cache=300,  # DNS cache 5 minutes
                enable_cleanup_closed=True
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=self._timeout_config
            )
        return self._session

    async def close(self) -> None:
        """Session'ı kapat"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _get_headers(self, with_auth: bool = True) -> dict:
        """HTTP headers"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "FeedemyPrinter/1.0"
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
        with_auth: bool = True,
        retry: bool = True
    ) -> dict:
        """HTTP request with retry and timeout"""
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers(with_auth)

        last_error = None
        retries = self.max_retries if retry else 1

        for attempt in range(retries):
            try:
                async with session.request(
                    method,
                    url,
                    json=json_data,
                    params=params,
                    headers=headers
                ) as response:
                    # Handle non-JSON responses
                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" not in content_type:
                        if response.status >= 400:
                            raise ApiError(f"HTTP {response.status}: {await response.text()}")
                        return None

                    data = await response.json()

                    # ApiResponse format: { success, message, data, errorCode }
                    if not data.get("success", False):
                        error = ApiError(
                            message=data.get("message", "Unknown error"),
                            error_code=data.get("errorCode")
                        )
                        # Don't retry on client errors (4xx)
                        if response.status < 500:
                            raise error
                        last_error = error
                    else:
                        return data.get("data")

            except asyncio.TimeoutError:
                last_error = ApiError(f"Request timeout after {self.timeout}s")
                logger.warning(f"Timeout on {method} {endpoint} (attempt {attempt + 1}/{retries})")

            except aiohttp.ClientError as e:
                last_error = ApiError(f"Connection error: {e}")
                logger.warning(f"Connection error on {method} {endpoint}: {e} (attempt {attempt + 1}/{retries})")

            # Exponential backoff before retry
            if attempt < retries - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                await asyncio.sleep(delay)

        # All retries exhausted
        logger.error(f"All {retries} retries failed for {method} {endpoint}")
        raise last_error or ApiError("Request failed after all retries")

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
