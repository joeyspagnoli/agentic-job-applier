"""Database manager for job postings storage."""

import aiosqlite
from pathlib import Path
from typing import Optional
from datetime import datetime


class DatabaseManager:
    """Async SQLite database manager for job postings."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Initialize database connection."""
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row

    async def create_tables(self) -> None:
        """Run schema.sql to create tables."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path) as f:
            schema = f.read()
        await self.conn.executescript(schema)
        await self.conn.commit()

    async def insert_job(self, job_data: dict) -> bool:
        """
        Insert a job posting.
        Returns True if inserted (new job), False if duplicate.
        """
        try:
            await self.conn.execute(
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
            await self.conn.commit()
            return True
        except aiosqlite.IntegrityError:
            # Duplicate job_hash - job already exists
            return False

    async def get_job_by_hash(self, job_hash: str) -> Optional[dict]:
        """Check if a job exists by its hash."""
        cursor = await self.conn.execute(
            "SELECT * FROM job_postings WHERE job_hash = ?", (job_hash,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None

    async def update_job_status(self, job_hash: str, status: str) -> None:
        """Update the processing status of a job."""
        await self.conn.execute(
            """
            UPDATE job_postings
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (status, job_hash),
        )
        await self.conn.commit()

    async def get_jobs_by_status(self, status: str, limit: int = 100) -> list[dict]:
        """Query jobs by status."""
        cursor = await self.conn.execute(
            "SELECT * FROM job_postings WHERE status = ? ORDER BY fetched_at DESC LIMIT ?",
            (status, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def start_crawl(self, source: str, company: str = None) -> int:
        """Log crawl start, return crawl_id."""
        cursor = await self.conn.execute(
            "INSERT INTO crawl_history (source, company) VALUES (?, ?)",
            (source, company),
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def complete_crawl(
        self,
        crawl_id: int,
        jobs_found: int,
        jobs_new: int,
        error: str = None,
    ) -> None:
        """Log crawl completion."""
        status = "FAILED" if error else "SUCCESS"
        await self.conn.execute(
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
        await self.conn.commit()

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
        await self.conn.execute(
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
            (date, jobs_discovered, jobs_new, jobs_duplicate, sources_crawled, sources_failed),
        )
        await self.conn.commit()

    async def get_job_count(self) -> int:
        """Get total number of jobs in database."""
        cursor = await self.conn.execute("SELECT COUNT(*) FROM job_postings")
        row = await cursor.fetchone()
        return row[0]

    async def get_jobs_today(self) -> int:
        """Get number of jobs discovered today."""
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = await self.conn.execute(
            "SELECT COUNT(*) FROM job_postings WHERE DATE(fetched_at) = ?",
            (today,),
        )
        row = await cursor.fetchone()
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
