"""
Config Manager - JSON config okuma/yazma
Token register sonrası buraya kaydedilir
"""

import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class ApiConfig:
    base_url: str
    token: Optional[str] = None


@dataclass
class DeviceConfig:
    name: str
    branch_guid: Optional[str] = None
    token_id: Optional[str] = None


@dataclass
class PollingConfig:
    interval_seconds: int = 5
    batch_size: int = 10


@dataclass
class PrinterConfig:
    default_width: int = 48
    charset: str = "cp857"


@dataclass
class AutoUpdateConfig:
    enabled: bool = True
    branch: str = "main"


class ConfigManager:
    """Config dosyası yönetimi"""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            # Proje kök dizinine göre config yolu
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "config.json"

        self.config_path = Path(config_path)
        self._data: dict = {}
        self.load()

    def load(self) -> None:
        """Config dosyasını oku"""
        if not self.config_path.exists():
            self._data = self._get_default_config()
            self.save()
            return

        with open(self.config_path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

    def save(self) -> None:
        """Config dosyasını kaydet"""
        # config dizini yoksa oluştur
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def _get_default_config(self) -> dict:
        """Varsayılan config"""
        return {
            "api": {
                "base_url": "https://api.feedemy.com",
                "token": None
            },
            "device": {
                "name": "Raspberry-001",
                "branch_guid": None,
                "token_id": None
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
                "enabled": True,
                "branch": "main"
            }
        }

    # === Property Accessors ===

    @property
    def api(self) -> ApiConfig:
        api_data = self._data.get("api", {})
        return ApiConfig(
            base_url=api_data.get("base_url", "https://api.feedemy.com"),
            token=api_data.get("token")
        )

    @property
    def device(self) -> DeviceConfig:
        dev_data = self._data.get("device", {})
        return DeviceConfig(
            name=dev_data.get("name", "Raspberry-001"),
            branch_guid=dev_data.get("branch_guid"),
            token_id=dev_data.get("token_id")
        )

    @property
    def polling(self) -> PollingConfig:
        poll_data = self._data.get("polling", {})
        return PollingConfig(
            interval_seconds=poll_data.get("interval_seconds", 5),
            batch_size=poll_data.get("batch_size", 10)
        )

    @property
    def printer(self) -> PrinterConfig:
        printer_data = self._data.get("printer", {})
        return PrinterConfig(
            default_width=printer_data.get("default_width", 48),
            charset=printer_data.get("charset", "cp857")
        )

    @property
    def auto_update(self) -> AutoUpdateConfig:
        update_data = self._data.get("auto_update", {})
        return AutoUpdateConfig(
            enabled=update_data.get("enabled", True),
            branch=update_data.get("branch", "main")
        )

    # === Token Management ===

    def is_registered(self) -> bool:
        """Token var mı kontrol et"""
        return self.api.token is not None

    def save_registration(self, token: str, token_id: str, branch_guid: str) -> None:
        """Register sonrası token ve device bilgilerini kaydet"""
        self._data["api"]["token"] = token
        self._data["device"]["token_id"] = token_id
        self._data["device"]["branch_guid"] = branch_guid
        self.save()

    def clear_registration(self) -> None:
        """Token bilgilerini temizle (revoke durumunda)"""
        self._data["api"]["token"] = None
        self._data["device"]["token_id"] = None
        self._data["device"]["branch_guid"] = None
        self.save()

    def update_device_name(self, name: str) -> None:
        """Cihaz adını güncelle"""
        self._data["device"]["name"] = name
        self.save()

    def update_api_url(self, url: str) -> None:
        """API URL'ini güncelle"""
        self._data["api"]["base_url"] = url
        self.save()
