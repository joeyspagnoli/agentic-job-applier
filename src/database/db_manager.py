"""Database manager for job postings storage."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from loguru import logger


class DatabaseManager:
    """Async SQLite database manager for job postings."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[aiosqlite.Connection] = None

    def _require_conn(self) -> aiosqlite.Connection:
        """Return a connected DB handle or fail fast."""

        if self.conn is None:
            raise RuntimeError(
                "Database connection not initialized. Call connect() first (or use 'async with')."
            )
        return self.conn

    async def connect(self) -> None:
        """Initialize database connection."""
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row

        # Improve concurrency behavior for systemd/timers on a homeserver.
        # - busy_timeout reduces transient "database is locked" failures
        # - WAL enables concurrent readers while a writer is active
        await self.conn.execute("PRAGMA busy_timeout = 5000")
        await self.conn.execute("PRAGMA journal_mode = WAL")

    async def create_tables(self) -> None:
        """Run schema.sql to create tables."""
        conn = self._require_conn()
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path) as f:
            schema = f.read()
        await conn.executescript(schema)
        await conn.commit()

    async def insert_job(self, job_data: dict) -> bool:
        """
        Insert a job posting.
        Returns True if inserted (new job), False if duplicate.
        """
        conn = self._require_conn()
        try:
            await conn.execute(
                """
                INSERT INTO job_postings (
                    job_hash, source, source_url, company, company_url,
                    title, location, is_remote, job_type,
                    salary_min, salary_max, salary_currency, salary_source,
                    description, requirements, posted_date, raw_data
                ) VALUES (
                    :job_hash, :source, :source_url, :company, :company_url,
                    :title, :location, :is_remote, :job_type,
                    :salary_min, :salary_max, :salary_currency, :salary_source,
                    :description, :requirements, :posted_date, :raw_data
                )
                """,
                job_data,
            )
            await conn.commit()
            return True
        except aiosqlite.IntegrityError:
            # Duplicate job_hash - job already exists
            return False

    async def get_job_by_hash(self, job_hash: str) -> Optional[dict]:
        """Check if a job exists by its hash."""
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM job_postings WHERE job_hash = ?", (job_hash,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None

    async def update_job_status(self, job_hash: str, status: str) -> None:
        """Update the processing status of a job."""
        conn = self._require_conn()
        await conn.execute(
            """
            UPDATE job_postings
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (status, job_hash),
        )
        await conn.commit()

    async def get_jobs_by_status(self, status: str, limit: int = 100) -> list[dict]:
        """Query jobs by status."""
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM job_postings WHERE status = ? ORDER BY fetched_at DESC LIMIT ?",
            (status, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_jobs_pending_agent_processing(self, limit: int = 100) -> list[dict]:
        """Fetch NEW jobs that have not been processed by an agent."""

        conn = self._require_conn()
        cursor = await conn.execute(
            """
            SELECT *
            FROM job_postings
            WHERE status = 'NEW'
              AND agent_processed_at IS NULL
              AND agent_failed_at IS NULL
            ORDER BY fetched_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def start_crawl(self, source: str, company: Optional[str] = None) -> int:
        """Log crawl start, return crawl_id."""
        conn = self._require_conn()
        cursor = await conn.execute(
            "INSERT INTO crawl_history (source, company) VALUES (?, ?)",
            (source, company),
        )
        await conn.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to insert crawl_history row (no lastrowid)")
        return cursor.lastrowid

    async def complete_crawl(
        self,
        crawl_id: int,
        jobs_found: int,
        jobs_new: int,
        error: Optional[str] = None,
    ) -> None:
        """Log crawl completion."""
        status = "FAILED" if error else "SUCCESS"
        conn = self._require_conn()
        await conn.execute(
            """
            UPDATE crawl_history
            SET completed_at = CURRENT_TIMESTAMP,
                status = ?,
                jobs_found = ?,
                jobs_new = ?,
                error_message = ?
            WHERE id = ?
            """,
            (status, jobs_found, jobs_new, error, crawl_id),
        )
        await conn.commit()

    async def update_daily_stats(
        self,
        date: str,
        jobs_discovered: int,
        jobs_new: int,
        jobs_duplicate: int,
        sources_crawled: int,
        sources_failed: int,
    ) -> None:
        """Update or insert daily statistics."""
        conn = self._require_conn()
        await conn.execute(
            """
            INSERT INTO daily_stats (
                date, total_jobs_discovered, jobs_new, jobs_duplicate,
                sources_crawled, sources_failed
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                total_jobs_discovered = total_jobs_discovered + excluded.total_jobs_discovered,
                jobs_new = jobs_new + excluded.jobs_new,
                jobs_duplicate = jobs_duplicate + excluded.jobs_duplicate,
                sources_crawled = sources_crawled + excluded.sources_crawled,
                sources_failed = sources_failed + excluded.sources_failed
            """,
            (
                date,
                jobs_discovered,
                jobs_new,
                jobs_duplicate,
                sources_crawled,
                sources_failed,
            ),
        )
        await conn.commit()

    async def migrate_agent_schema(self) -> None:
        """Add agent workflow tracking columns if they don't exist."""
        conn = self._require_conn()
        cursor = await conn.execute("PRAGMA table_info(job_postings)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if "agent_processed_at" not in column_names:
            await conn.execute(
                "ALTER TABLE job_postings ADD COLUMN agent_processed_at TIMESTAMP"
            )
            logger.info("Added agent_processed_at column")

        if "agent_result" not in column_names:
            await conn.execute("ALTER TABLE job_postings ADD COLUMN agent_result TEXT")
            logger.info("Added agent_result column")

        # Failure markers to avoid infinite retries (status is CHECK constrained).
        if "agent_failed_at" not in column_names:
            await conn.execute(
                "ALTER TABLE job_postings ADD COLUMN agent_failed_at TIMESTAMP"
            )
            logger.info("Added agent_failed_at column")

        if "agent_error" not in column_names:
            await conn.execute("ALTER TABLE job_postings ADD COLUMN agent_error TEXT")
            logger.info("Added agent_error column")

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agent_processed
            ON job_postings(agent_processed_at)
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agent_failed
            ON job_postings(agent_failed_at)
            """
        )

        await conn.commit()

    async def record_agent_decision(
        self,
        *,
        job_hash: str,
        agent_result: str,
        status: str,
    ) -> None:
        """Atomically persist agent output + status transition."""

        conn = self._require_conn()
        await conn.execute(
            """
            UPDATE job_postings
            SET agent_result = ?,
                agent_processed_at = CURRENT_TIMESTAMP,
                status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (agent_result, status, job_hash),
        )
        await conn.commit()

    async def mark_job_agent_failed(self, job_hash: str, error: str) -> None:
        """Record agent failure and prevent infinite retries."""

        conn = self._require_conn()
        await conn.execute(
            """
            UPDATE job_postings
            SET agent_failed_at = CURRENT_TIMESTAMP,
                agent_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (error, job_hash),
        )
        await conn.commit()

    async def update_job_agent_result(self, job_hash: str, agent_result: str) -> None:
        """Store agent output and mark job as agent-processed."""
        conn = self._require_conn()
        await conn.execute(
            """
            UPDATE job_postings
            SET agent_result = ?,
                agent_processed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (agent_result, job_hash),
        )
        await conn.commit()

    async def get_job_count(self) -> int:
        """Get total number of jobs in database."""
        conn = self._require_conn()
        cursor = await conn.execute("SELECT COUNT(*) FROM job_postings")
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to fetch COUNT(*) from job_postings")
        return row[0]

    async def get_jobs_today(self) -> int:
        """Get number of jobs discovered today."""
        conn = self._require_conn()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM job_postings WHERE DATE(fetched_at) = ?",
            (today,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to fetch today's job count")
        return row[0]

    async def close(self) -> None:
        """Clean shutdown."""
        if self.conn:
            await self.conn.close()
            self.conn = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
