"""Crawl-history and daily-stats telemetry helpers.

Owns writes to `crawl_history` and `daily_stats` — the two tables that
record discovery operational metrics independent of any individual job.
"""

from __future__ import annotations

from typing import Optional

from src.database._mixins.base import _BaseMixin


class TelemetryMixin(_BaseMixin):
    """Crawl-history and daily-stats writers."""

    async def start_crawl(self, source: str, company: Optional[str] = None) -> int:
        """Insert a crawl-history row and return its ID.

        Purpose:
            Create the crawl record before fetch work begins so both successful
            and failed attempts show up in operational history.
        Args:
            self: The database manager recording the crawl start.
            source: Source identifier for the crawl.
            company: Optional company or search label for the crawl.
        Output:
            Returns the inserted crawl-history row ID.
        """

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
        """Mark a crawl-history row as finished.

        Purpose:
            Persist the final outcome of a crawl attempt, including counts and
            any error message needed for later debugging.
        Args:
            self: The database manager recording crawl completion.
            crawl_id: Primary key of the crawl-history row to update.
            jobs_found: Total jobs returned before deduplication.
            jobs_new: Total jobs that were new after deduplication.
            error: Optional error message when the crawl failed.
        Output:
            Returns `None` after updating the crawl-history row and committing.
        """

        status = "FAILED" if error else "SUCCESS"
        conn = self._require_conn()

        # Crawl rows always receive a completion timestamp so dashboards can
        # distinguish in-progress work from completed attempts.
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
        """Accumulate one cycle's counts into the daily stats table.

        Purpose:
            Keep a per-day rollup that survives across multiple discovery cycles
            without needing a separate analytics job.
        Args:
            self: The database manager updating the daily rollup row.
            date: ISO date string representing the stats bucket to update.
            jobs_discovered: Total jobs found before deduplication.
            jobs_new: Total new jobs inserted during the cycle.
            jobs_duplicate: Total duplicate jobs skipped during the cycle.
            sources_crawled: Count of successful crawl units.
            sources_failed: Count of failed crawl units.
        Output:
            Returns `None` after inserting or incrementing the target row.
        """

        conn = self._require_conn()

        # Daily rows are incremented rather than overwritten so multiple runs on
        # the same date contribute to one operational summary.
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
