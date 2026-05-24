"""Job CRUD, status updates, listing, and pending-claim queries.

Owns reads/writes against `job_postings` itself — discovery inserts,
hash/id lookups, status changes, paged listings, and the atomic
`get_jobs_pending_agent_processing` claim used by the gate worker.
"""

from __future__ import annotations

import os
from typing import Optional

import aiosqlite
from loguru import logger

from src.database._mixins.base import _BaseMixin
from src.utils.json_types import JSONObject

DEFAULT_AGENT_CLAIM_LEASE_SECONDS = 900


class JobsMixin(_BaseMixin):
    """Job-postings CRUD, status, and pending-claim helpers."""

    async def insert_job(self, job_data: dict[str, object]) -> bool:
        """Insert a normalized job posting into the database.

        Purpose:
            Persist a new job into `job_postings` while treating duplicate hash
            collisions as an expected outcome rather than a hard failure.
        Args:
            self: The database manager performing the insert.
            job_data: Dictionary whose keys match the job insert placeholders.
        Output:
            Returns `True` when the row is inserted and `False` when SQLite
            rejects it because the `job_hash` already exists.
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
        except aiosqlite.IntegrityError as exc:
            error_text = str(exc).lower()
            if "job_postings.job_hash" in error_text:
                # Duplicate hashes are part of normal discovery, so callers get
                # a boolean result for that one expected integrity case.
                return False

            # Non-duplicate integrity failures should surface because they
            # represent real schema or data contract violations.
            logger.error("Unexpected insert integrity error: {}", exc)
            raise

    async def get_job_by_hash(self, job_hash: str) -> Optional[JSONObject]:
        """Fetch one job row by its deduplication hash.

        Purpose:
            Support duplicate checks, debugging, and one-off scripts that need
            to load a specific posting from storage.
        Args:
            self: The database manager performing the lookup.
            job_hash: Stable deduplication hash for the job posting.
        Output:
            Returns the matching row as a dictionary, or `None` when the job
            does not exist in the database.
        """

        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM job_postings WHERE job_hash = ?",
            (job_hash,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_job_by_id(self, job_id: int) -> Optional[JSONObject]:
        """Fetch one job row by its numeric primary key.

        Purpose:
            Support operational scripts and resume-tailor workflows that
            identify rows by SQLite ID instead of deduplication hash.
        Args:
            self: The database manager performing the lookup.
            job_id: Numeric primary key from `job_postings.id`.
        Output:
            Returns the matching row as a dictionary, or `None` when absent.
        """

        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM job_postings WHERE id = ?",
            (job_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_resume_tailor_job_context(
        self,
        *,
        job_hash: str | None = None,
        job_id: int | None = None,
    ) -> Optional[JSONObject]:
        """Fetch the job context payload used by resume-tailor workflows.

        Purpose:
            Provide one stable read path for resume-tailor tooling so the
            tailoring agent can pull job context directly from SQLite by either
            hash or numeric ID.
        Args:
            self: The database manager performing the lookup.
            job_hash: Optional deduplication hash for the target job.
            job_id: Optional numeric primary key for the target job.
        Output:
            Returns a dictionary with the fields needed by the tailor, or
            `None` when no matching row exists.
        Raises:
            ValueError: When both selectors are set, or when neither is set.
        """

        has_hash = job_hash is not None and job_hash.strip() != ""
        has_id = job_id is not None
        if has_hash == has_id:
            raise ValueError("Provide exactly one of job_hash or job_id")

        conn = self._require_conn()
        context_fields = """
            id,
            job_hash,
            source,
            source_url,
            company,
            title,
            location,
            is_remote,
            job_type,
            salary_min,
            salary_max,
            salary_currency,
            salary_source,
            description,
            requirements,
            posted_date,
            status,
            fetched_at,
            updated_at
        """
        if has_hash:
            cursor = await conn.execute(
                f"SELECT {context_fields} FROM job_postings WHERE job_hash = ?",
                (job_hash,),
            )
        else:
            cursor = await conn.execute(
                f"SELECT {context_fields} FROM job_postings WHERE id = ?",
                (job_id,),
            )

        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_existing_job_hashes(self, job_hashes: list[str]) -> set[str]:
        """Fetch the subset of hashes that already exist in the database.

        Purpose:
            Support batch deduplication by replacing one-query-per-hash checks
            with chunked `IN (...)` lookups against SQLite.
        Args:
            self: The database manager performing the batch lookup.
            job_hashes: Candidate hash values to check for persistence.
        Output:
            Returns a set containing only the hashes already stored.
        """

        if not job_hashes:
            return set()

        conn = self._require_conn()
        existing_hashes: set[str] = set()

        # SQLite limits bound parameters, so large lists are chunked to keep
        # the query valid while still avoiding N+1 duplicate lookups.
        chunk_size = 900
        for index in range(0, len(job_hashes), chunk_size):
            chunk = job_hashes[index : index + chunk_size]
            placeholders = ", ".join("?" for _ in chunk)
            cursor = await conn.execute(
                f"SELECT job_hash FROM job_postings WHERE job_hash IN ({placeholders})",
                chunk,
            )
            rows = await cursor.fetchall()
            existing_hashes.update(row[0] for row in rows)

        return existing_hashes

    async def update_job_description(
        self,
        *,
        job_hash: str,
        description: str,
    ) -> None:
        """Persist a freshly-fetched job description back to the row.

        Purpose:
            Cache a lazy-fetched JD body so subsequent tailor runs and
            debug queries see the real text instead of the empty string
            or synthetic placeholder that discovery wrote at insert time.
        Args:
            self: The database manager performing the update.
            job_hash: Stable deduplication hash for the target job.
            description: Plain-text description body to persist.
        Output:
            Returns `None` after updating the row and committing.
        """

        conn = self._require_conn()
        await conn.execute(
            """
            UPDATE job_postings
            SET description = ?, updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (description, job_hash),
        )
        await conn.commit()

    async def update_job_status(self, job_hash: str, status: str) -> None:
        """Update the workflow status for one stored job.

        Purpose:
            Let scripts or future workflows move a job between coarse-grained
            states like `NEW`, `QUALIFIED`, or `FILTERED`.
        Args:
            self: The database manager performing the update.
            job_hash: Stable deduplication hash for the target job.
            status: New workflow status string to persist.
        Output:
            Returns `None` after updating the row and committing the change.
        """

        conn = self._require_conn()

        # Status changes update `updated_at` so downstream tooling can tell when
        # the row was last touched by workflow logic.
        await conn.execute(
            """
            UPDATE job_postings
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (status, job_hash),
        )
        await conn.commit()

    async def get_jobs_by_status(
        self,
        status: str,
        limit: int = 100,
    ) -> list[JSONObject]:
        """Fetch jobs matching a specific workflow status.

        Purpose:
            Support status-based operational scripts and downstream workflows
            that need recent rows from a single status bucket.
        Args:
            self: The database manager performing the query.
            status: Workflow status value to filter on.
            limit: Maximum number of rows to return.
        Output:
            Returns a list of database rows as dictionaries ordered by newest
            `fetched_at` first.
        """

        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM job_postings WHERE status = ? ORDER BY fetched_at DESC LIMIT ?",
            (status, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_jobs_pending_agent_processing(
        self,
        limit: int = 100,
    ) -> list[JSONObject]:
        """Atomically claim and fetch pending NEW jobs for agent processing.

        Purpose:
            Prevent duplicate work across concurrent workers by claiming rows
            in one transaction before returning them for processing.
        Args:
            self: The database manager performing the query.
            limit: Maximum number of rows to claim and return in one batch.
        Output:
            Returns a list of pending claimed rows as dictionaries.
        """

        await self._ensure_agent_schema_ready()
        conn = self._require_conn()
        raw_claim_lease_seconds = os.getenv(
            "AGENT_CLAIM_LEASE_SECONDS",
            str(DEFAULT_AGENT_CLAIM_LEASE_SECONDS),
        )
        try:
            claim_lease_seconds = int(raw_claim_lease_seconds)
        except ValueError:
            logger.warning(
                "Invalid AGENT_CLAIM_LEASE_SECONDS='{}'; using {}",
                raw_claim_lease_seconds,
                DEFAULT_AGENT_CLAIM_LEASE_SECONDS,
            )
            claim_lease_seconds = DEFAULT_AGENT_CLAIM_LEASE_SECONDS
        claim_cutoff_modifier = f"-{max(claim_lease_seconds, 1)} seconds"
        claim_token = os.urandom(12).hex()

        try:
            await conn.execute("BEGIN IMMEDIATE")
            cursor = await conn.execute(
                """
                UPDATE job_postings
                SET agent_claim_token = ?,
                    agent_claimed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id IN (
                    SELECT id
                    FROM job_postings
                    WHERE status = 'NEW'
                      AND agent_processed_at IS NULL
                      AND agent_failed_at IS NULL
                      AND (
                            agent_next_retry_at IS NULL
                            OR agent_next_retry_at <= CURRENT_TIMESTAMP
                          )
                      AND (
                            agent_claimed_at IS NULL
                            OR agent_claimed_at <= datetime('now', ?)
                          )
                    ORDER BY
                        CASE
                            WHEN agent_next_retry_at IS NULL THEN fetched_at
                            ELSE agent_next_retry_at
                        END ASC,
                        fetched_at ASC,
                        id ASC
                    LIMIT ?
                )
                RETURNING *
                """,
                (claim_token, claim_cutoff_modifier, limit),
            )
            rows = list(await cursor.fetchall())
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

        # Keep returned rows in deterministic FIFO order.
        rows.sort(
            key=lambda row: (
                row["agent_next_retry_at"]
                if row["agent_next_retry_at"]
                else row["fetched_at"],
                row["fetched_at"],
                row["id"],
            )
        )
        return [dict(row) for row in rows]

    async def get_job_count(self) -> int:
        """Return the total number of stored jobs.

        Purpose:
            Provide a lightweight metric for status dashboards and end-of-cycle
            logging without exposing raw SQL at call sites.
        Args:
            self: The database manager performing the aggregate query.
        Output:
            Returns the total row count in `job_postings`.
        """

        conn = self._require_conn()
        cursor = await conn.execute("SELECT COUNT(*) FROM job_postings")
        row = await cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to fetch COUNT(*) from job_postings")
        return int(row[0])

    async def get_jobs_today(self) -> int:
        """Return how many jobs were fetched on the current date.

        Purpose:
            Support quick operational visibility into whether today's discovery
            runs are actually producing new records.
        Args:
            self: The database manager performing the aggregate query.
        Output:
            Returns the count of jobs whose `fetched_at` date is today.
        """

        conn = self._require_conn()
        cursor = await conn.execute(
            """
            SELECT COUNT(*)
            FROM job_postings
            WHERE fetched_at >= datetime('now', 'start of day')
              AND fetched_at < datetime('now', 'start of day', '+1 day')
            """
        )
        row = await cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to fetch today's job count")
        return int(row[0])
