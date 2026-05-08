"""Resume-tailor run schema, claim, and retry helpers.

Owns the `tailor_runs` table and every method that claims, completes,
or queries one tailor attempt for a `QUALIFIED` job posting.
"""

from __future__ import annotations

import os
from typing import Optional

from loguru import logger

from src.database._mixins.base import _BaseMixin
from src.utils.json_types import JSONObject

DEFAULT_TAILOR_CLAIM_LEASE_SECONDS = 7200


class TailorMixin(_BaseMixin):
    """Tailor-run claim, success/failure, and history queries."""

    async def migrate_tailor_schema(self) -> None:
        """Create the tailor_runs table and indexes when missing.

        Purpose:
            Bootstrap the tailor-run tracking schema idempotently so the
            worker can run against databases that predate the tailor stage.
        Args:
            self: The database manager performing the migration.
        Output:
            Returns `None` after ensuring the table and indexes exist.
        """

        conn = self._require_conn()
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tailor_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                artifact_yaml_path TEXT,
                artifact_tex_path TEXT,
                artifact_pdf_path TEXT,
                page_count INTEGER,
                error TEXT,
                next_retry_at TIMESTAMP,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                claim_token TEXT,
                CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED'))
            );
            CREATE INDEX IF NOT EXISTS idx_tailor_runs_job_hash
                ON tailor_runs(job_hash);
            CREATE INDEX IF NOT EXISTS idx_tailor_runs_status
                ON tailor_runs(status);
            CREATE INDEX IF NOT EXISTS idx_tailor_runs_started_at
                ON tailor_runs(started_at);
            CREATE INDEX IF NOT EXISTS idx_tailor_runs_job_status
                ON tailor_runs(job_hash, status);
            """
        )

        # Older databases may already have tailor_runs without YAML artifact
        # tracking; add the column idempotently when missing.
        cursor = await conn.execute("PRAGMA table_info(tailor_runs)")
        columns = await cursor.fetchall()
        column_names = {column[1] for column in columns}
        if "artifact_yaml_path" not in column_names:
            await conn.execute(
                "ALTER TABLE tailor_runs ADD COLUMN artifact_yaml_path TEXT"
            )

        await conn.commit()
        self._tailor_schema_ready = True

    async def _ensure_tailor_schema_ready(self) -> None:
        """Ensure the tailor_runs table exists before tailor queries run.

        Purpose:
            Prevent runtime SQL failures when callers use tailor-specific
            query paths on databases that predate the tailor schema.
        Args:
            self: The database manager validating tailor-schema readiness.
        Output:
            Returns `None` after ensuring the tailor_runs table exists.
        """

        if self._tailor_schema_ready:
            return

        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tailor_runs'"
        )
        row = await cursor.fetchone()
        if row is not None:
            self._tailor_schema_ready = True
            return

        await self.migrate_tailor_schema()

    async def claim_next_tailor_job(
        self,
        *,
        max_retries: int,
        lease_seconds: int = DEFAULT_TAILOR_CLAIM_LEASE_SECONDS,
    ) -> Optional[dict[str, object]]:
        """Atomically claim the next eligible QUALIFIED job for tailoring.

        Purpose:
            Insert a PENDING tailor_runs row inside a BEGIN IMMEDIATE
            transaction so concurrent workers cannot double-claim jobs.
        Args:
            self: The database manager performing the atomic claim.
            max_retries: Maximum FAILED runs before a job is excluded.
            lease_seconds: Seconds a PENDING claim stays valid before
                being considered stale.
        Output:
            Returns a merged dictionary of job_postings fields and the
            tailor_runs row with `_tailor_run_id` key, or `None` when
            no eligible job exists.
        """

        if max_retries < 1:
            raise ValueError(f"max_retries must be at least 1, got {max_retries}")

        await self._ensure_tailor_schema_ready()
        conn = self._require_conn()
        claim_token = os.urandom(32).hex()
        lease_modifier = f"-{max(lease_seconds, 1)} seconds"

        try:
            await conn.execute("BEGIN IMMEDIATE")

            # Find one eligible QUALIFIED job that has no active PENDING
            # claim and fewer than max_retries FAILED runs.
            candidate_cursor = await conn.execute(
                """
                SELECT jp.job_hash
                FROM job_postings jp
                WHERE jp.status = 'QUALIFIED'
                  AND NOT EXISTS (
                      SELECT 1 FROM tailor_runs tr
                      WHERE tr.job_hash = jp.job_hash
                        AND tr.status = 'SUCCESS'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM tailor_runs tr
                      WHERE tr.job_hash = jp.job_hash
                        AND tr.status = 'PENDING'
                        AND tr.started_at > datetime('now', ?)
                  )
                  AND (
                      SELECT COUNT(*) FROM tailor_runs tr
                      WHERE tr.job_hash = jp.job_hash
                        AND tr.status = 'FAILED'
                  ) < ?
                  AND COALESCE(
                      (
                          SELECT MAX(tr.next_retry_at)
                          FROM tailor_runs tr
                          WHERE tr.job_hash = jp.job_hash
                            AND tr.status = 'FAILED'
                      ),
                      datetime('now', '-1 second')
                  ) <= datetime('now')
                ORDER BY jp.fetched_at ASC, jp.id ASC
                LIMIT 1
                """,
                (lease_modifier, max_retries),
            )
            candidate = await candidate_cursor.fetchone()
            if candidate is None:
                await conn.rollback()
                return None

            job_hash = candidate["job_hash"]

            # Claim by inserting a PENDING row.
            insert_cursor = await conn.execute(
                """
                INSERT INTO tailor_runs (job_hash, status, claim_token)
                VALUES (?, 'PENDING', ?)
                RETURNING *
                """,
                (job_hash, claim_token),
            )
            run_row = await insert_cursor.fetchone()

            # Fetch the full job row for the caller.
            job_cursor = await conn.execute(
                "SELECT * FROM job_postings WHERE job_hash = ?",
                (job_hash,),
            )
            job_row = await job_cursor.fetchone()

            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

        if run_row is None or job_row is None:
            return None

        logger.info("Claimed tailor job: job_hash={} run_id={}", job_hash, run_row["id"])
        merged = dict(job_row)
        merged["_tailor_run_id"] = run_row["id"]
        merged["_tailor_claim_token"] = run_row["claim_token"]
        return merged

    async def record_tailor_success(
        self,
        *,
        run_id: int,
        artifact_yaml_path: str,
        artifact_tex_path: str,
        artifact_pdf_path: str,
        page_count: int | None,
    ) -> None:
        """Mark a tailor run as successful with artifact metadata.

        Purpose:
            Persist the output artifact paths and page count so operators
            can locate the generated resume without inspecting the filesystem.
        Args:
            self: The database manager recording the success.
            run_id: Primary key of the tailor_runs row to update.
            artifact_yaml_path: Filesystem path to the tailored YAML work file.
            artifact_tex_path: Filesystem path to the generated TeX file.
            artifact_pdf_path: Filesystem path to the generated PDF file.
            page_count: Final page count of the generated PDF.
        Output:
            Returns `None` after updating the row and committing.
        """

        await self._ensure_tailor_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            """
            UPDATE tailor_runs
            SET status = 'SUCCESS',
                artifact_yaml_path = ?,
                artifact_tex_path = ?,
                artifact_pdf_path = ?,
                page_count = ?,
                completed_at = CURRENT_TIMESTAMP,
                next_retry_at = NULL
            WHERE id = ?
            """,
            (
                artifact_yaml_path,
                artifact_tex_path,
                artifact_pdf_path,
                page_count,
                run_id,
            ),
        )
        await conn.commit()

    async def record_tailor_failure(
        self,
        *,
        run_id: int,
        error: str,
        next_retry_at: str | None,
    ) -> None:
        """Mark a tailor run as failed with error details.

        Purpose:
            Persist the failure reason and optional retry scheduling so
            the worker can back off and retry eligible jobs later.
        Args:
            self: The database manager recording the failure.
            run_id: Primary key of the tailor_runs row to update.
            error: Error message describing why the tailor run failed.
            next_retry_at: Optional UTC timestamp string for the next
                eligible retry. `None` means no further retries.
        Output:
            Returns `None` after updating the row and committing.
        """

        await self._ensure_tailor_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            """
            UPDATE tailor_runs
            SET status = 'FAILED',
                error = ?,
                next_retry_at = ?,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (error, next_retry_at, run_id),
        )
        await conn.commit()

    async def mark_stale_tailor_runs_failed(
        self,
        *,
        lease_seconds: int = DEFAULT_TAILOR_CLAIM_LEASE_SECONDS,
    ) -> int:
        """Convert stale PENDING tailor runs to FAILED on startup.

        Purpose:
            Handle crash recovery by marking orphaned PENDING rows so
            the affected jobs become eligible for retry.
        Args:
            self: The database manager performing the stale-run cleanup.
            lease_seconds: Age threshold in seconds for considering a
                PENDING run stale.
        Output:
            Returns the number of PENDING rows converted to FAILED.
        """

        await self._ensure_tailor_schema_ready()
        conn = self._require_conn()
        lease_modifier = f"-{max(lease_seconds, 1)} seconds"
        cursor = await conn.execute(
            """
            UPDATE tailor_runs
            SET status = 'FAILED',
                error = 'stale_pending_on_startup',
                completed_at = CURRENT_TIMESTAMP
            WHERE status = 'PENDING'
              AND started_at <= datetime('now', ?)
            """,
            (lease_modifier,),
        )
        await conn.commit()
        return cursor.rowcount

    async def get_tailor_runs_for_job(self, job_hash: str) -> list[JSONObject]:
        """Fetch all tailor runs for a given job hash.

        Purpose:
            Support retry-count inspection and operator debugging by
            returning the full attempt history for one job.
        Args:
            self: The database manager performing the lookup.
            job_hash: Stable deduplication hash for the target job.
        Output:
            Returns a list of tailor_runs rows as dictionaries ordered
            by `started_at` ascending.
        """

        await self._ensure_tailor_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM tailor_runs WHERE job_hash = ? ORDER BY started_at ASC",
            (job_hash,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_tailor_failure_count(self, job_hash: str) -> int:
        """Count FAILED tailor runs for a given job hash.

        Purpose:
            Replace the N+1 pattern of fetching all runs then counting in Python.
            Used by the exception recovery path to determine retry eligibility
            without loading full run history into memory.

        Arg(s):
            job_hash: Stable deduplication hash for the target job.

        Output:
            Returns the count of FAILED tailor_runs rows for the job.
        """

        await self._ensure_tailor_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM tailor_runs WHERE job_hash = ? AND status = 'FAILED'",
            (job_hash,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0
