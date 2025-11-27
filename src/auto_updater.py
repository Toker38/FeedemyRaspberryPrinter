"""
Auto Updater - Git pull ile otomatik güncelleme
Başlangıçta çalışır, güncelleme varsa systemctl restart yapar
"""

import subprocess
import logging
import hashlib
import sys
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class AutoUpdater:
    """Git tabanlı otomatik güncelleme"""

    SERVICE_NAME = "feedemy-printer"

    def __init__(self, repo_path: Optional[str] = None, branch: str = "main"):
        if repo_path is None:
            repo_path = Path(__file__).parent.parent

        self.repo_path = Path(repo_path)
        self.branch = branch
        self.requirements_path = self.repo_path / "requirements.txt"
        self.venv_pip = self.repo_path / "venv" / "bin" / "pip"

    def check_and_update(self) -> bool:
        """
        Güncelleme kontrol et ve varsa uygula

        Returns:
            True = güncelleme yapıldı, restart gerekli
            False = güncelleme yok veya hata
        """
        try:
            logger.info("Checking for updates...")

            # 1. Git fetch
            if not self._git_fetch():
                return False

            # 2. Local vs Remote karşılaştır
            local_hash, remote_hash = self._get_commits()
            if local_hash == remote_hash:
                logger.info("Already up to date")
                return False

            logger.info(f"Update available: {local_hash[:8]} → {remote_hash[:8]}")

            # 3. requirements.txt hash'ini kaydet (pip install gerekli mi?)
            old_req_hash = self._get_file_hash(self.requirements_path)

            # 4. Git pull
            if not self._git_pull():
                return False

            # 5. requirements.txt değişti mi?
            new_req_hash = self._get_file_hash(self.requirements_path)
            if old_req_hash != new_req_hash:
                logger.info("requirements.txt changed, installing dependencies...")
                self._pip_install()

            # 6. Restart
            logger.info("Update complete, restarting service...")
            self._restart_service()

            return True

        except Exception as e:
            logger.error(f"Update check failed: {e}")
            return False

    def _git_fetch(self) -> bool:
        """git fetch origin"""
        result = subprocess.run(
            ["git", "fetch", "origin", self.branch],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.error(f"git fetch failed: {result.stderr}")
            return False
        return True

    def _get_commits(self) -> Tuple[str, str]:
        """Local ve remote commit hash'lerini al"""
        # Local HEAD
        local = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        local_hash = local.stdout.strip()

        # Remote HEAD
        remote = subprocess.run(
            ["git", "rev-parse", f"origin/{self.branch}"],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        remote_hash = remote.stdout.strip()

        return local_hash, remote_hash

    def _git_pull(self) -> bool:
        """git pull origin branch"""
        result = subprocess.run(
            ["git", "pull", "origin", self.branch],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.error(f"git pull failed: {result.stderr}")
            return False

        logger.info(f"git pull: {result.stdout}")
        return True

    def _get_file_hash(self, path: Path) -> str:
        """Dosya hash'i (MD5)"""
        if not path.exists():
            return ""
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def _pip_install(self) -> bool:
        """pip install -r requirements.txt using venv pip"""
        # Use venv pip if available, otherwise fall back to system pip
        pip_cmd = str(self.venv_pip) if self.venv_pip.exists() else sys.executable + " -m pip"

        if self.venv_pip.exists():
            cmd = [str(self.venv_pip), "install", "-r", str(self.requirements_path)]
        else:
            cmd = [sys.executable, "-m", "pip", "install", "-r", str(self.requirements_path)]

        result = subprocess.run(
            cmd,
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.error(f"pip install failed: {result.stderr}")
            return False

        logger.info("Dependencies updated")
        return True

    def _restart_service(self) -> None:
        """systemctl restart feedemy-printer"""
        result = subprocess.run(
            ["sudo", "systemctl", "restart", self.SERVICE_NAME],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.error(f"Service restart failed: {result.stderr}")
        # Bu noktadan sonra process zaten restart olacağı için
        # burası muhtemelen çalışmayacak
