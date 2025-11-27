"""
Job Store - SQLite ile işlenen job'ları takip et
Duplicate job işlemeyi önler
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class JobStore:
    """SQLite tabanlı job tracking"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            project_root = Path(__file__).parent.parent
            db_path = project_root / "data" / "jobs.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Veritabanı tablolarını oluştur"""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_jobs (
                    job_guid TEXT PRIMARY KEY,
                    processed_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT
                )
            """)
            # Index for cleanup queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_processed_at
                ON processed_jobs(processed_at)
            """)
            conn.commit()

    @contextmanager
    def _get_connection(self):
        """SQLite connection context manager"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            yield conn
        finally:
            conn.close()

    def is_processed(self, job_guid: str) -> bool:
        """Job daha önce işlendi mi?"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_jobs WHERE job_guid = ?",
                (job_guid,)
            )
            return cursor.fetchone() is not None

    def get_status(self, job_guid: str) -> Optional[str]:
        """Job'ın durumunu getir"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT status FROM processed_jobs WHERE job_guid = ?",
                (job_guid,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def mark_completed(self, job_guid: str) -> None:
        """Job'ı tamamlandı olarak işaretle"""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_jobs
                (job_guid, processed_at, status, error)
                VALUES (?, ?, ?, ?)
                """,
                (job_guid, datetime.utcnow().isoformat(), "completed", None)
            )
            conn.commit()
        logger.debug(f"Job marked as completed: {job_guid}")

    def mark_failed(self, job_guid: str, error: str) -> None:
        """Job'ı başarısız olarak işaretle"""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_jobs
                (job_guid, processed_at, status, error)
                VALUES (?, ?, ?, ?)
                """,
                (job_guid, datetime.utcnow().isoformat(), "failed", error)
            )
            conn.commit()
        logger.debug(f"Job marked as failed: {job_guid} - {error}")

    def mark_skipped(self, job_guid: str, reason: str) -> None:
        """Job'ı atlandı olarak işaretle"""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_jobs
                (job_guid, processed_at, status, error)
                VALUES (?, ?, ?, ?)
                """,
                (job_guid, datetime.utcnow().isoformat(), "skipped", reason)
            )
            conn.commit()
        logger.debug(f"Job marked as skipped: {job_guid} - {reason}")

    def cleanup_old(self, days: int = 7) -> int:
        """Eski kayıtları temizle"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM processed_jobs WHERE processed_at < ?",
                (cutoff_str,)
            )
            conn.commit()
            deleted = cursor.rowcount

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old job records")

        return deleted

    def get_stats(self) -> dict:
        """İstatistikleri getir"""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    status,
                    COUNT(*) as count
                FROM processed_jobs
                GROUP BY status
            """)
            stats = {row[0]: row[1] for row in cursor.fetchall()}

            cursor = conn.execute("SELECT COUNT(*) FROM processed_jobs")
            stats["total"] = cursor.fetchone()[0]

        return stats
