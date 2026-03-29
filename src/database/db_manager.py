"""Manage SQLite persistence for job discovery and agent workflows.

This module owns connection setup, schema bootstrap, crawl tracking, job
queries, and the extra state needed by the apply/skip agent pipeline.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import aiosqlite
from loguru import logger

DEFAULT_AGENT_CLAIM_LEASE_SECONDS = 900
DEFAULT_TAILOR_CLAIM_LEASE_SECONDS = 7200
DEFAULT_REVIEW_CLAIM_LEASE_SECONDS = 7200
DEFAULT_APPLY_CLAIM_LEASE_SECONDS = 1800  # Browser ops are slower than agent runs
DEFAULT_MONTHLY_BUDGET_USD = 500.0

_JOURNAL_MODE_SQL: dict[str, str] = {
    "DELETE": "PRAGMA journal_mode = DELETE",
    "TRUNCATE": "PRAGMA journal_mode = TRUNCATE",
    "PERSIST": "PRAGMA journal_mode = PERSIST",
    "MEMORY": "PRAGMA journal_mode = MEMORY",
    "WAL": "PRAGMA journal_mode = WAL",
}


class DatabaseManager:
    """Async SQLite database manager for job postings and crawl metadata."""

    def __init__(self, db_path: str):
        """Store the database path and initialize the connection slot.

        Purpose:
            Capture the SQLite path that future connection and schema methods
            will operate on during a workflow run.
        Args:
            self: The database manager instance being initialized.
            db_path: Filesystem path to the SQLite database file.
        Output:
            Returns `None` after saving the path and clearing the connection.
        """

        self.db_path = db_path
        self.conn: Optional[aiosqlite.Connection] = None
        self._agent_schema_ready = False
        self._tailor_schema_ready = False
        self._review_schema_ready = False
        self._apply_schema_ready = False
        self._cost_schema_ready = False

    def _require_conn(self) -> aiosqlite.Connection:
        """Return the active SQLite connection or fail fast.

        Purpose:
            Centralize the guard that prevents query methods from running before
            `connect()` or the async context manager has been used.
        Args:
            self: The database manager requesting the active connection.
        Output:
            Returns the active `aiosqlite.Connection`, or raises a
            `RuntimeError` when no connection has been created yet.
        """

        if self.conn is None:
            raise RuntimeError(
                "Database connection not initialized. Call connect() first (or use 'async with')."
            )
        return self.conn

    async def connect(self) -> None:
        """Open the SQLite connection and apply connection-level pragmas.

        Purpose:
            Create the on-disk database directory if needed, connect to SQLite,
            and configure behavior that is safer for repeated scheduled runs.
        Args:
            self: The database manager opening its SQLite connection.
        Output:
            Returns `None` after initializing `self.conn`.
        """

        # The database directory may not exist in a fresh checkout, so it is
        # created up front before SQLite tries to open the file.
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row
        self._agent_schema_ready = False
        self._tailor_schema_ready = False
        self._review_schema_ready = False
        self._apply_schema_ready = False
        self._cost_schema_ready = False

        # These pragmas reduce lock contention during timer-driven runs while
        # still keeping the database simple and file-backed.
        await self.conn.execute("PRAGMA busy_timeout = 5000")

        journal_mode = os.getenv("SQLITE_JOURNAL_MODE", "WAL").strip().upper()
        allowed_journal_modes = {"DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL"}
        if journal_mode not in allowed_journal_modes:
            logger.warning(
                "Invalid SQLITE_JOURNAL_MODE='{}'; falling back to WAL",
                journal_mode,
            )
            journal_mode = "WAL"

        await self.conn.execute(_JOURNAL_MODE_SQL[journal_mode])

    async def create_tables(self) -> None:
        """Create the database tables defined in `schema.sql`.

        Purpose:
            Bootstrap the SQLite schema on startup so the repo can be run in a
            new environment without a separate migration step.
        Args:
            self: The database manager executing the schema script.
        Output:
            Returns `None` after executing `schema.sql` and committing it.
        """

        conn = self._require_conn()
        schema_path = Path(__file__).parent / "schema.sql"

        # The schema lives beside the manager so database shape changes stay
        # versioned with the code that depends on them.
        with open(schema_path) as f:
            schema = f.read()

        await conn.executescript(schema)
        await conn.commit()

    async def insert_job(self, job_data: dict) -> bool:
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

    async def get_job_by_hash(self, job_hash: str) -> Optional[dict]:
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

    async def get_job_by_id(self, job_id: int) -> Optional[dict]:
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
    ) -> Optional[dict]:
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

    async def get_jobs_by_status(self, status: str, limit: int = 100) -> list[dict]:
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

    async def get_jobs_pending_agent_processing(self, limit: int = 100) -> list[dict]:
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
            rows = await cursor.fetchall()
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

    async def migrate_agent_schema(self) -> None:
        """Add agent-processing columns and indexes when they are missing.

        Purpose:
            Keep older databases compatible with the agent workflow without
            requiring a separate migration framework.
        Args:
            self: The database manager performing the lightweight migration.
        Output:
            Returns `None` after adding missing columns and indexes.
        """

        conn = self._require_conn()
        cursor = await conn.execute("PRAGMA table_info(job_postings)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        # Column existence checks make the migration safe to run on every start
        # regardless of whether the database is brand new or long-lived.
        if "agent_processed_at" not in column_names:
            await conn.execute(
                "ALTER TABLE job_postings ADD COLUMN agent_processed_at TIMESTAMP"
            )
            logger.info("Added agent_processed_at column")

        if "agent_result" not in column_names:
            await conn.execute("ALTER TABLE job_postings ADD COLUMN agent_result TEXT")
            logger.info("Added agent_result column")

        # Failure markers exist separately from status so rows can stay `NEW`
        # while still being excluded from infinite retry loops.
        if "agent_failed_at" not in column_names:
            await conn.execute(
                "ALTER TABLE job_postings ADD COLUMN agent_failed_at TIMESTAMP"
            )
            logger.info("Added agent_failed_at column")

        if "agent_error" not in column_names:
            await conn.execute("ALTER TABLE job_postings ADD COLUMN agent_error TEXT")
            logger.info("Added agent_error column")

        if "agent_retry_count" not in column_names:
            await conn.execute(
                "ALTER TABLE job_postings "
                "ADD COLUMN agent_retry_count INTEGER NOT NULL DEFAULT 0"
            )
            logger.info("Added agent_retry_count column")

        if "agent_next_retry_at" not in column_names:
            await conn.execute(
                "ALTER TABLE job_postings ADD COLUMN agent_next_retry_at TIMESTAMP"
            )
            logger.info("Added agent_next_retry_at column")

        if "agent_claim_token" not in column_names:
            await conn.execute(
                "ALTER TABLE job_postings ADD COLUMN agent_claim_token TEXT"
            )
            logger.info("Added agent_claim_token column")

        if "agent_claimed_at" not in column_names:
            await conn.execute(
                "ALTER TABLE job_postings ADD COLUMN agent_claimed_at TIMESTAMP"
            )
            logger.info("Added agent_claimed_at column")

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
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agent_retry_ready
            ON job_postings(status, agent_failed_at, agent_processed_at, agent_next_retry_at)
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agent_claimed_at
            ON job_postings(agent_claimed_at)
            """
        )
        await conn.commit()
        self._agent_schema_ready = True

    async def _ensure_agent_schema_ready(self) -> None:
        """Ensure agent-processing columns exist before agent queries run.

        Purpose:
            Prevent runtime SQL failures when callers use agent-specific query
            paths on databases that predate the agent schema columns.
        Args:
            self: The database manager validating agent-schema readiness.
        Output:
            Returns `None` after ensuring required columns and indexes exist.
        """

        if self._agent_schema_ready:
            return

        conn = self._require_conn()
        cursor = await conn.execute("PRAGMA table_info(job_postings)")
        columns = await cursor.fetchall()
        column_names = {col[1] for col in columns}
        required_columns = {
            "agent_processed_at",
            "agent_result",
            "agent_failed_at",
            "agent_error",
            "agent_retry_count",
            "agent_next_retry_at",
            "agent_claim_token",
            "agent_claimed_at",
        }

        if required_columns.issubset(column_names):
            self._agent_schema_ready = True
            return

        await self.migrate_agent_schema()

    async def record_agent_decision(
        self,
        *,
        job_hash: str,
        agent_result: str,
        status: str,
    ) -> None:
        """Persist a successful agent decision and its resulting status.

        Purpose:
            Atomically store the serialized agent output, mark the row as
            processed, and update the workflow status in one statement.
        Args:
            self: The database manager recording the agent result.
            job_hash: Stable deduplication hash for the target job.
            agent_result: Serialized agent output payload.
            status: Final workflow status derived from the decision.
        Output:
            Returns `None` after updating the row and committing the change.
        """

        await self._ensure_agent_schema_ready()
        conn = self._require_conn()

        # This update intentionally sets both the machine-readable result and
        # the coarse-grained status used by simpler operational tooling.
        await conn.execute(
            """
            UPDATE job_postings
            SET agent_result = ?,
                agent_processed_at = CURRENT_TIMESTAMP,
                agent_failed_at = NULL,
                agent_error = NULL,
                agent_retry_count = 0,
                agent_next_retry_at = NULL,
                agent_claim_token = NULL,
                agent_claimed_at = NULL,
                status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (agent_result, status, job_hash),
        )
        await conn.commit()

    async def record_agent_retry(
        self,
        *,
        job_hash: str,
        error: str,
        retry_count: int,
        next_retry_at: str,
    ) -> None:
        """Persist retry state for a job that failed this processing attempt.

        Purpose:
            Record transient agent failure metadata while keeping the row in the
            NEW backlog so it can be retried after the scheduled timestamp.
        Args:
            self: The database manager recording retry metadata.
            job_hash: Stable deduplication hash for the target job.
            error: Error message describing the failed processing attempt.
            retry_count: Retry-attempt counter value to persist.
            next_retry_at: SQLite-compatible UTC timestamp string for the next
                retry attempt.
        Output:
            Returns `None` after persisting retry metadata and committing.
        """

        await self._ensure_agent_schema_ready()
        conn = self._require_conn()

        await conn.execute(
            """
            UPDATE job_postings
            SET agent_error = ?,
                agent_retry_count = ?,
                agent_next_retry_at = ?,
                agent_claim_token = NULL,
                agent_claimed_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (error, retry_count, next_retry_at, job_hash),
        )
        await conn.commit()

    async def mark_job_agent_terminal_failed(
        self,
        job_hash: str,
        error: str,
        retry_count: int | None = None,
    ) -> None:
        """Record a terminal agent-processing failure for a job.

        Purpose:
            Mark jobs that exhausted retries so operators can review and requeue
            them manually without reprocessing every loop.
        Args:
            self: The database manager recording the terminal failure.
            job_hash: Stable deduplication hash for the target job.
            error: Error message describing the terminal failure reason.
            retry_count: Optional final retry-attempt count to persist.
        Output:
            Returns `None` after updating the failure markers and committing.
        """

        await self._ensure_agent_schema_ready()
        conn = self._require_conn()

        # Failure metadata is stored separately from status because the schema's
        # status enum is intentionally coarse and workflow-oriented.
        await conn.execute(
            """
            UPDATE job_postings
            SET agent_failed_at = CURRENT_TIMESTAMP,
                agent_error = ?,
                agent_retry_count = COALESCE(?, agent_retry_count),
                agent_next_retry_at = NULL,
                agent_claim_token = NULL,
                agent_claimed_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (error, retry_count, job_hash),
        )
        await conn.commit()

    async def mark_job_agent_failed(self, job_hash: str, error: str) -> None:
        """Record terminal failure metadata for compatibility call sites.

        Purpose:
            Preserve backward compatibility for existing call sites/tests while
            routing writes through the terminal-failure method.
        Args:
            self: The database manager recording the terminal failure.
            job_hash: Stable deduplication hash for the target job.
            error: Error message describing why agent processing failed.
        Output:
            Returns `None` after writing terminal failure markers.
        """

        await self.mark_job_agent_terminal_failed(job_hash, error)

    async def reset_agent_failure_state(self, job_hash: str) -> None:
        """Requeue a terminally failed job back into NEW processing backlog.

        Purpose:
            Provide an explicit operator action for retrying jobs that failed
            terminally after the automated retry limit.
        Args:
            self: The database manager requeueing the target job.
            job_hash: Stable deduplication hash for the target job.
        Output:
            Returns `None` after clearing failure metadata and committing.
        """

        await self._ensure_agent_schema_ready()
        conn = self._require_conn()

        await conn.execute(
            """
            UPDATE job_postings
            SET status = 'NEW',
                agent_failed_at = NULL,
                agent_error = NULL,
                agent_retry_count = 0,
                agent_next_retry_at = NULL,
                agent_claim_token = NULL,
                agent_claimed_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (job_hash,),
        )
        await conn.commit()

    async def update_job_agent_result(self, job_hash: str, agent_result: str) -> None:
        """Store agent output without changing the job status.

        Purpose:
            Support workflows that want to save the agent payload now and decide
            on the status transition separately.
        Args:
            self: The database manager updating the job.
            job_hash: Stable deduplication hash for the target job.
            agent_result: Serialized agent output payload.
        Output:
            Returns `None` after updating the result columns and committing.
        """

        await self._ensure_agent_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            """
            UPDATE job_postings
            SET agent_result = ?,
                agent_processed_at = CURRENT_TIMESTAMP,
                agent_failed_at = NULL,
                agent_error = NULL,
                agent_retry_count = 0,
                agent_next_retry_at = NULL,
                agent_claim_token = NULL,
                agent_claimed_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (agent_result, job_hash),
        )
        await conn.commit()

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
        return row[0]

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
        return row[0]

    # ------------------------------------------------------------------
    # Tailor-run schema and claim methods
    # ------------------------------------------------------------------

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
    ) -> Optional[dict]:
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
            logger.info(
                "Claimed tailor job: job_hash={} run_id={}", job_hash, run_row["id"]
            )
        except Exception:
            await conn.rollback()
            raise

        if run_row is None or job_row is None:
            return None

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

    async def reset_tailor_failure_state(self, *, job_hash: str) -> None:
        """Delete FAILED tailor runs for a job so it can be requeued.

        Purpose:
            Provide an operator-facing action for retrying a job that
            exhausted its tailor retry limit or was manually rejected.
        Args:
            self: The database manager clearing the failure state.
            job_hash: Stable deduplication hash for the target job.
        Output:
            Returns `None` after deleting FAILED rows and committing.
        """

        await self._ensure_tailor_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            "DELETE FROM tailor_runs WHERE job_hash = ? AND status = 'FAILED'",
            (job_hash,),
        )
        await conn.commit()

    async def get_tailor_runs_for_job(self, job_hash: str) -> list[dict]:
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

    # ------------------------------------------------------------------
    # Review-run schema and claim methods
    # ------------------------------------------------------------------

    async def migrate_review_schema(self) -> None:
        """Create review_runs table and indexes when missing.

        Purpose:
            Bootstrap post-tailor review run tracking idempotently so workers
            can run against databases that predate the review stage.
        Args:
            self: The database manager performing the migration.
        Output:
            Returns `None` after ensuring review schema exists.
        """

        conn = self._require_conn()
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS review_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_hash TEXT NOT NULL,
                tailor_run_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                verdict TEXT,
                selected_yaml_path TEXT,
                selected_tex_path TEXT,
                selected_pdf_path TEXT,
                review_report_json TEXT,
                agent_stdout TEXT,
                agent_stderr TEXT,
                error TEXT,
                next_retry_at TIMESTAMP,
                fallback_base_yaml_path TEXT,
                fallback_base_tex_path TEXT,
                fallback_base_pdf_path TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                claim_token TEXT,
                CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED')),
                CHECK (verdict IS NULL OR verdict IN ('PASS', 'TAILORED', 'BASE', 'FAIL'))
            );
            CREATE INDEX IF NOT EXISTS idx_review_runs_job_hash
                ON review_runs(job_hash);
            CREATE INDEX IF NOT EXISTS idx_review_runs_status
                ON review_runs(status);
            CREATE INDEX IF NOT EXISTS idx_review_runs_started_at
                ON review_runs(started_at);
            CREATE INDEX IF NOT EXISTS idx_review_runs_tailor_run_id
                ON review_runs(tailor_run_id);
            CREATE INDEX IF NOT EXISTS idx_review_runs_tailor_status
                ON review_runs(tailor_run_id, status);
            """
        )
        await conn.commit()
        self._review_schema_ready = True

    async def _ensure_review_schema_ready(self) -> None:
        """Ensure review_runs table exists before review queries run.

        Purpose:
            Prevent runtime SQL failures when callers use review-specific query
            paths on databases that predate the review schema.
        Args:
            self: The database manager validating review-schema readiness.
        Output:
            Returns `None` after ensuring the review schema exists.
        """

        if self._review_schema_ready:
            return

        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='review_runs'"
        )
        row = await cursor.fetchone()
        if row is not None:
            self._review_schema_ready = True
            return

        await self.migrate_review_schema()

    async def claim_next_review_job(
        self,
        *,
        max_retries: int,
        lease_seconds: int = DEFAULT_REVIEW_CLAIM_LEASE_SECONDS,
    ) -> Optional[dict]:
        """Atomically claim one eligible tailor SUCCESS run for review.

        Purpose:
            Insert a PENDING review_runs row in a BEGIN IMMEDIATE transaction so
            concurrent review workers cannot double-claim the same tailor run.
        Args:
            self: The database manager performing the atomic claim.
            max_retries: Maximum FAILED review runs allowed per tailor run.
            lease_seconds: Seconds a PENDING review claim stays valid.
        Output:
            Returns merged job/tailor row with review metadata keys, or `None`
            when no eligible review candidate exists.
        Raises:
            ValueError: When `max_retries` is less than 1.
        """

        if max_retries < 1:
            raise ValueError(f"max_retries must be at least 1, got {max_retries}")

        await self._ensure_tailor_schema_ready()
        await self._ensure_review_schema_ready()
        conn = self._require_conn()
        claim_token = os.urandom(32).hex()
        lease_modifier = f"-{max(lease_seconds, 1)} seconds"

        try:
            await conn.execute("BEGIN IMMEDIATE")

            candidate_cursor = await conn.execute(
                """
                SELECT
                    jp.*,
                    tr.id AS tailor_run_id,
                    tr.artifact_yaml_path,
                    tr.artifact_tex_path,
                    tr.artifact_pdf_path
                FROM tailor_runs tr
                JOIN job_postings jp
                  ON jp.job_hash = tr.job_hash
                WHERE tr.status = 'SUCCESS'
                  AND NOT EXISTS (
                      SELECT 1 FROM review_runs rr
                      WHERE rr.tailor_run_id = tr.id
                        AND rr.status = 'SUCCESS'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM review_runs rr
                      WHERE rr.tailor_run_id = tr.id
                        AND rr.status = 'PENDING'
                        AND rr.started_at > datetime('now', ?)
                  )
                  AND (
                      SELECT COUNT(*) FROM review_runs rr
                      WHERE rr.tailor_run_id = tr.id
                        AND rr.status = 'FAILED'
                  ) < ?
                  AND COALESCE(
                      (
                          SELECT MAX(rr.next_retry_at)
                          FROM review_runs rr
                          WHERE rr.tailor_run_id = tr.id
                            AND rr.status = 'FAILED'
                      ),
                      datetime('now', '-1 second')
                  ) <= datetime('now')
                ORDER BY COALESCE(tr.completed_at, tr.started_at) ASC, tr.id ASC
                LIMIT 1
                """,
                (lease_modifier, max_retries),
            )
            candidate_row = await candidate_cursor.fetchone()
            if candidate_row is None:
                await conn.rollback()
                return None

            insert_cursor = await conn.execute(
                """
                INSERT INTO review_runs (job_hash, tailor_run_id, status, claim_token)
                VALUES (?, ?, 'PENDING', ?)
                RETURNING id, claim_token
                """,
                (
                    candidate_row["job_hash"],
                    candidate_row["tailor_run_id"],
                    claim_token,
                ),
            )
            review_row = await insert_cursor.fetchone()
            await conn.commit()
            logger.info(
                "Claimed review job: job_hash={} tailor_run_id={} review_run_id={}",
                candidate_row["job_hash"],
                candidate_row["tailor_run_id"],
                review_row["id"] if review_row else None,
            )
        except Exception:
            await conn.rollback()
            raise

        if review_row is None:
            return None

        merged_row = dict(candidate_row)
        merged_row["_review_run_id"] = review_row["id"]
        merged_row["_review_claim_token"] = review_row["claim_token"]
        return merged_row

    async def record_review_success(
        self,
        *,
        run_id: int,
        verdict: str,
        selected_yaml_path: str | None,
        selected_tex_path: str | None,
        selected_pdf_path: str | None,
        review_report_json: str,
        agent_stdout: str | None,
        agent_stderr: str | None,
    ) -> None:
        """Mark a review run as successful and persist verdict artifacts.

        Purpose:
            Store the agent-authored verdict/report payload and selected resume
            references for downstream pipeline continuation.
        Args:
            self: The database manager recording review success.
            run_id: Primary key of the review_runs row to update.
            verdict: Agent-selected review verdict value.
            selected_yaml_path: Selected resume YAML path from report.
            selected_tex_path: Selected resume TeX path from report.
            selected_pdf_path: Selected resume PDF path from report.
            review_report_json: Canonical serialized review report JSON.
            agent_stdout: Raw pi subprocess stdout for diagnostics.
            agent_stderr: Raw pi subprocess stderr for diagnostics.
        Output:
            Returns `None` after updating review row and committing.
        """

        await self._ensure_review_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            """
            UPDATE review_runs
            SET status = 'SUCCESS',
                verdict = ?,
                selected_yaml_path = ?,
                selected_tex_path = ?,
                selected_pdf_path = ?,
                review_report_json = ?,
                agent_stdout = ?,
                agent_stderr = ?,
                error = NULL,
                next_retry_at = NULL,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                verdict,
                selected_yaml_path,
                selected_tex_path,
                selected_pdf_path,
                review_report_json,
                agent_stdout,
                agent_stderr,
                run_id,
            ),
        )
        await conn.commit()

    async def record_review_failure(
        self,
        *,
        run_id: int,
        error: str,
        next_retry_at: str | None,
        agent_stdout: str | None,
        agent_stderr: str | None,
        fallback_base_yaml_path: str,
        fallback_base_tex_path: str,
        fallback_base_pdf_path: str,
    ) -> None:
        """Mark a review run as failed and persist fallback/base diagnostics.

        Purpose:
            Store hard-runtime failure details and base fallback references so
            downstream stages can continue without blocking on review retries.
        Args:
            self: The database manager recording review failure.
            run_id: Primary key of the review_runs row to update.
            error: Failure reason text.
            next_retry_at: Optional UTC timestamp for scheduled retry.
            agent_stdout: Raw pi subprocess stdout for diagnostics.
            agent_stderr: Raw pi subprocess stderr for diagnostics.
            fallback_base_yaml_path: Base YAML fallback path.
            fallback_base_tex_path: Base TeX fallback path.
            fallback_base_pdf_path: Base PDF fallback path.
        Output:
            Returns `None` after updating review row and committing.
        """

        await self._ensure_review_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            """
            UPDATE review_runs
            SET status = 'FAILED',
                error = ?,
                next_retry_at = ?,
                agent_stdout = ?,
                agent_stderr = ?,
                fallback_base_yaml_path = ?,
                fallback_base_tex_path = ?,
                fallback_base_pdf_path = ?,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                error,
                next_retry_at,
                agent_stdout,
                agent_stderr,
                fallback_base_yaml_path,
                fallback_base_tex_path,
                fallback_base_pdf_path,
                run_id,
            ),
        )
        await conn.commit()

    async def mark_stale_review_runs_failed(
        self,
        *,
        lease_seconds: int = DEFAULT_REVIEW_CLAIM_LEASE_SECONDS,
    ) -> int:
        """Convert stale PENDING review runs to FAILED on startup.

        Purpose:
            Handle worker crash recovery by marking orphaned PENDING review runs
            failed so they become retry-eligible.
        Args:
            self: The database manager performing stale-run cleanup.
            lease_seconds: Age threshold in seconds for stale PENDING rows.
        Output:
            Returns number of rows converted to FAILED.
        """

        await self._ensure_review_schema_ready()
        conn = self._require_conn()
        lease_modifier = f"-{max(lease_seconds, 1)} seconds"
        cursor = await conn.execute(
            """
            UPDATE review_runs
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

    async def get_review_failure_count(self, tailor_run_id: int) -> int:
        """Count FAILED review runs for one tailor run identifier.

        Purpose:
            Provide efficient retry-count lookups for review worker backoff and
            terminal-failure decisions.
        Args:
            tailor_run_id: Tailor run identifier associated with review attempts.
        Output:
            Returns number of FAILED review_runs rows for the tailor run.
        """

        await self._ensure_review_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM review_runs WHERE tailor_run_id = ? AND status = 'FAILED'",
            (tailor_run_id,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def get_review_runs_for_tailor_run(self, tailor_run_id: int) -> list[dict]:
        """Fetch review run history for one tailor run.

        Purpose:
            Support tests and operational diagnostics for post-tailor review
            retries and verdict progression.
        Args:
            tailor_run_id: Tailor run identifier to inspect.
        Output:
            Returns review_runs rows ordered by started_at ascending.
        """

        await self._ensure_review_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM review_runs WHERE tailor_run_id = ? ORDER BY started_at ASC",
            (tailor_run_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Apply-run schema and claim methods
    # ------------------------------------------------------------------

    async def migrate_apply_schema(self) -> None:
        """Create apply_runs table and indexes when missing.

        Purpose:
            Bootstrap browser apply-run tracking idempotently so workers
            can run against databases that predate the apply stage.
        Args:
            self: The database manager performing the migration.
        Output:
            Returns `None` after ensuring apply schema exists.
        """

        conn = self._require_conn()
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS apply_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_hash TEXT NOT NULL,
                review_run_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                resume_pdf_path TEXT,
                resume_source TEXT,
                outcome TEXT,
                confidence_score REAL,
                confidence_report_json TEXT,
                screenshot_path TEXT,
                dom_snapshot_path TEXT,
                unresolved_fields_json TEXT,
                simplify_autofill_detected BOOLEAN,
                ats_platform TEXT,
                page_url TEXT,
                error TEXT,
                next_retry_at TIMESTAMP,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                claim_token TEXT,
                CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED')),
                CHECK (outcome IS NULL OR outcome IN (
                    'NEEDS_REVIEW', 'SUBMITTED',
                    'FAILED_PREFILL', 'FAILED_UPLOAD',
                    'FAILED_NAVIGATION', 'FAILED_OTHER'
                ))
            );
            CREATE INDEX IF NOT EXISTS idx_apply_runs_job_hash
                ON apply_runs(job_hash);
            CREATE INDEX IF NOT EXISTS idx_apply_runs_status
                ON apply_runs(status);
            CREATE INDEX IF NOT EXISTS idx_apply_runs_started_at
                ON apply_runs(started_at);
            CREATE INDEX IF NOT EXISTS idx_apply_runs_review_run_id
                ON apply_runs(review_run_id);
            CREATE INDEX IF NOT EXISTS idx_apply_runs_outcome
                ON apply_runs(outcome);
            CREATE TABLE IF NOT EXISTS apply_handoffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apply_run_id INTEGER NOT NULL UNIQUE,
                job_hash TEXT NOT NULL,
                review_run_id INTEGER NOT NULL,
                handoff_status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
                apply_outcome TEXT NOT NULL,
                resume_source TEXT,
                resume_pdf_path TEXT,
                confidence_score REAL,
                confidence_report_json TEXT,
                unresolved_fields_json TEXT,
                screenshot_path TEXT,
                dom_snapshot_path TEXT,
                ats_platform TEXT,
                page_url TEXT,
                reviewer_notes TEXT,
                reviewed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CHECK (handoff_status IN ('PENDING_REVIEW', 'APPROVED', 'REJECTED')),
                CHECK (apply_outcome IN (
                    'NEEDS_REVIEW', 'SUBMITTED',
                    'FAILED_PREFILL', 'FAILED_UPLOAD',
                    'FAILED_NAVIGATION', 'FAILED_OTHER'
                ))
            );
            CREATE INDEX IF NOT EXISTS idx_apply_handoffs_status
                ON apply_handoffs(handoff_status);
            CREATE INDEX IF NOT EXISTS idx_apply_handoffs_job_hash
                ON apply_handoffs(job_hash);
            CREATE INDEX IF NOT EXISTS idx_apply_handoffs_review_run_id
                ON apply_handoffs(review_run_id);
            """
        )
        await conn.commit()
        self._apply_schema_ready = True

    async def _ensure_apply_schema_ready(self) -> None:
        """Ensure apply_runs table exists before apply queries run.

        Purpose:
            Prevent runtime SQL failures when callers use apply-specific query
            paths on databases that predate the apply schema.
        Args:
            self: The database manager validating apply-schema readiness.
        Output:
            Returns `None` after ensuring the apply schema exists.
        """

        if self._apply_schema_ready:
            return

        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='apply_runs'"
        )
        row = await cursor.fetchone()
        if row is not None:
            self._apply_schema_ready = True
            return

        await self.migrate_apply_schema()

    async def claim_next_apply_job(
        self,
        *,
        max_retries: int,
        lease_seconds: int = DEFAULT_APPLY_CLAIM_LEASE_SECONDS,
    ) -> Optional[dict]:
        """Atomically claim one eligible reviewed job for browser application.

        Purpose:
            Insert a PENDING apply_runs row in a BEGIN IMMEDIATE transaction so
            concurrent apply workers cannot double-claim the same review run.
        Args:
            self: The database manager performing the atomic claim.
            max_retries: Maximum FAILED apply runs allowed per review run.
            lease_seconds: Seconds a PENDING apply claim stays valid.
        Output:
            Returns merged job/review row with apply metadata keys, or `None`
            when no eligible apply candidate exists.
        Raises:
            ValueError: When `max_retries` is less than 1.
        """

        if max_retries < 1:
            raise ValueError(f"max_retries must be at least 1, got {max_retries}")

        await self._ensure_review_schema_ready()
        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        claim_token = os.urandom(32).hex()
        lease_modifier = f"-{max(lease_seconds, 1)} seconds"

        try:
            await conn.execute("BEGIN IMMEDIATE")

            candidate_cursor = await conn.execute(
                """
                SELECT
                    jp.job_hash,
                    jp.source_url,
                    jp.title,
                    jp.company,
                    jp.description,
                    rr.id AS review_run_id,
                    rr.verdict AS review_verdict,
                    rr.selected_pdf_path,
                    rr.selected_yaml_path,
                    rr.fallback_base_pdf_path
                FROM review_runs rr
                JOIN job_postings jp
                  ON jp.job_hash = rr.job_hash
                WHERE rr.status = 'SUCCESS'
                  AND rr.verdict IN ('PASS', 'TAILORED', 'BASE')
                  AND NOT EXISTS (
                      SELECT 1 FROM apply_runs ar
                      WHERE ar.review_run_id = rr.id
                        AND ar.status = 'SUCCESS'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM apply_runs ar
                      WHERE ar.review_run_id = rr.id
                        AND ar.status = 'PENDING'
                        AND ar.started_at > datetime('now', ?)
                  )
                  AND (
                      SELECT COUNT(*) FROM apply_runs ar
                      WHERE ar.review_run_id = rr.id
                        AND ar.status = 'FAILED'
                  ) < ?
                  AND COALESCE(
                      (
                          SELECT MAX(datetime(ar.next_retry_at))
                          FROM apply_runs ar
                          WHERE ar.review_run_id = rr.id
                            AND ar.status = 'FAILED'
                      ),
                      datetime('now', '-1 second')
                  ) <= datetime('now')
                ORDER BY COALESCE(rr.completed_at, rr.started_at) ASC, rr.id ASC
                LIMIT 1
                """,
                (lease_modifier, max_retries),
            )
            candidate_row = await candidate_cursor.fetchone()
            if candidate_row is None:
                await conn.rollback()
                return None

            insert_cursor = await conn.execute(
                """
                INSERT INTO apply_runs (job_hash, review_run_id, status, claim_token)
                VALUES (?, ?, 'PENDING', ?)
                RETURNING id, claim_token
                """,
                (
                    candidate_row["job_hash"],
                    candidate_row["review_run_id"],
                    claim_token,
                ),
            )
            apply_row = await insert_cursor.fetchone()
            await conn.commit()
            logger.info(
                "Claimed apply job: job_hash={} review_run_id={} apply_run_id={}",
                candidate_row["job_hash"],
                candidate_row["review_run_id"],
                apply_row["id"] if apply_row else None,
            )
        except Exception:
            await conn.rollback()
            raise

        if apply_row is None:
            return None

        merged_row = dict(candidate_row)
        merged_row["_apply_run_id"] = apply_row["id"]
        merged_row["_apply_claim_token"] = apply_row["claim_token"]
        return merged_row

    async def record_apply_success(
        self,
        *,
        run_id: int,
        outcome: str,
        resume_pdf_path: str | None,
        resume_source: str | None,
        confidence_score: float | None,
        confidence_report_json: str | None,
        screenshot_path: str | None,
        dom_snapshot_path: str | None,
        unresolved_fields_json: str | None,
        simplify_autofill_detected: bool | None,
        ats_platform: str | None,
        page_url: str | None,
    ) -> None:
        """Mark an apply run as successful and persist all diagnostics.

        Purpose:
            Store the full application outcome, confidence report, and captured
            artifacts for user review and future agent repair.
        Args:
            self: The database manager recording apply success.
            run_id: Primary key of the apply_runs row to update.
            outcome: Application-level result value.
            resume_pdf_path: Path to the resume PDF that was uploaded.
            resume_source: Whether TAILORED or BASE resume was used.
            confidence_score: Overall confidence score in [0.0, 1.0].
            confidence_report_json: Serialized ConfidenceReport payload.
            screenshot_path: Path to the pre-submit screenshot.
            dom_snapshot_path: Path to the captured page HTML.
            unresolved_fields_json: Serialized list of unresolved field metadata.
            simplify_autofill_detected: Whether Simplify extension activated.
            ats_platform: Detected ATS platform identifier.
            page_url: Final page URL after any redirects.
        Output:
            Returns `None` after updating the apply row and committing.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            """
            UPDATE apply_runs
            SET status = 'SUCCESS',
                outcome = ?,
                resume_pdf_path = ?,
                resume_source = ?,
                confidence_score = ?,
                confidence_report_json = ?,
                screenshot_path = ?,
                dom_snapshot_path = ?,
                unresolved_fields_json = ?,
                simplify_autofill_detected = ?,
                ats_platform = ?,
                page_url = ?,
                error = NULL,
                next_retry_at = NULL,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                outcome,
                resume_pdf_path,
                resume_source,
                confidence_score,
                confidence_report_json,
                screenshot_path,
                dom_snapshot_path,
                unresolved_fields_json,
                simplify_autofill_detected,
                ats_platform,
                page_url,
                run_id,
            ),
        )
        await conn.commit()

    async def record_apply_failure(
        self,
        *,
        run_id: int,
        error: str,
        next_retry_at: str | None,
        outcome: str | None = None,
        screenshot_path: str | None = None,
        dom_snapshot_path: str | None = None,
        ats_platform: str | None = None,
        page_url: str | None = None,
    ) -> None:
        """Mark an apply run as failed and persist partial diagnostics.

        Purpose:
            Store failure details and any partial artifacts captured before the
            error so post-mortem analysis is possible even on failed attempts.
        Args:
            self: The database manager recording apply failure.
            run_id: Primary key of the apply_runs row to update.
            error: Failure reason text.
            next_retry_at: Optional UTC timestamp for scheduled retry.
            outcome: Optional application-level failure classification.
            screenshot_path: Path to any captured screenshot before failure.
            dom_snapshot_path: Path to any captured page HTML before failure.
            ats_platform: Detected ATS platform identifier if available.
            page_url: Final page URL if available.
        Output:
            Returns `None` after updating the apply row and committing.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            """
            UPDATE apply_runs
            SET status = 'FAILED',
                error = ?,
                next_retry_at = ?,
                outcome = ?,
                screenshot_path = ?,
                dom_snapshot_path = ?,
                ats_platform = ?,
                page_url = ?,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                error,
                next_retry_at,
                outcome,
                screenshot_path,
                dom_snapshot_path,
                ats_platform,
                page_url,
                run_id,
            ),
        )
        await conn.commit()

    async def record_apply_handoff(
        self,
        *,
        apply_run_id: int,
        job_hash: str,
        review_run_id: int,
        apply_outcome: str,
        resume_source: str | None,
        resume_pdf_path: str | None,
        confidence_score: float | None,
        confidence_report_json: str | None,
        unresolved_fields_json: str | None,
        screenshot_path: str | None,
        dom_snapshot_path: str | None,
        ats_platform: str | None,
        page_url: str | None,
    ) -> None:
        """Create or update a human-review handoff row for one apply attempt.

        Purpose:
            Persist a stable operator-review checkpoint keyed to apply run ID
            so dry-run outcomes can be audited and approved asynchronously.
        Args:
            self: The database manager writing the handoff checkpoint.
            apply_run_id: Primary key of the associated `apply_runs` row.
            job_hash: Stable job identifier associated with the run.
            review_run_id: Source review run that fed apply-stage eligibility.
            apply_outcome: Apply outcome enum captured from browser execution.
            resume_source: Whether TAILORED or BASE resume was used.
            resume_pdf_path: Path to the uploaded resume PDF.
            confidence_score: Final weighted confidence score.
            confidence_report_json: Serialized confidence-check breakdown.
            unresolved_fields_json: Serialized unresolved-field metadata.
            screenshot_path: Path to pre-submit screenshot artifact.
            dom_snapshot_path: Path to captured DOM snapshot artifact.
            ats_platform: Detected ATS platform slug.
            page_url: Final in-browser URL after automation steps.
        Output:
            Returns `None` after upserting handoff persistence state.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            """
            INSERT INTO apply_handoffs (
                apply_run_id,
                job_hash,
                review_run_id,
                handoff_status,
                apply_outcome,
                resume_source,
                resume_pdf_path,
                confidence_score,
                confidence_report_json,
                unresolved_fields_json,
                screenshot_path,
                dom_snapshot_path,
                ats_platform,
                page_url
            )
            VALUES (?, ?, ?, 'PENDING_REVIEW', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(apply_run_id) DO UPDATE SET
                job_hash = excluded.job_hash,
                review_run_id = excluded.review_run_id,
                apply_outcome = excluded.apply_outcome,
                resume_source = excluded.resume_source,
                resume_pdf_path = excluded.resume_pdf_path,
                confidence_score = excluded.confidence_score,
                confidence_report_json = excluded.confidence_report_json,
                unresolved_fields_json = excluded.unresolved_fields_json,
                screenshot_path = excluded.screenshot_path,
                dom_snapshot_path = excluded.dom_snapshot_path,
                ats_platform = excluded.ats_platform,
                page_url = excluded.page_url,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                apply_run_id,
                job_hash,
                review_run_id,
                apply_outcome,
                resume_source,
                resume_pdf_path,
                confidence_score,
                confidence_report_json,
                unresolved_fields_json,
                screenshot_path,
                dom_snapshot_path,
                ats_platform,
                page_url,
            ),
        )
        await conn.commit()

    async def get_apply_handoffs(
        self,
        *,
        handoff_status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Fetch persisted apply handoffs for operator review workflows.

        Purpose:
            Provide deterministic read access to apply-stage handoff records
            for tooling and test assertions.
        Args:
            self: The database manager loading handoff rows.
            handoff_status: Optional status filter.
            limit: Maximum number of rows to return, clamped to at least 1.
        Output:
            Returns newest-first handoff rows as dictionaries.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        safe_limit = max(limit, 1)

        if handoff_status is None:
            cursor = await conn.execute(
                """
                SELECT *
                FROM apply_handoffs
                ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
                LIMIT ?
                """,
                (safe_limit,),
            )
        else:
            cursor = await conn.execute(
                """
                SELECT *
                FROM apply_handoffs
                WHERE handoff_status = ?
                ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
                LIMIT ?
                """,
                (handoff_status, safe_limit),
            )

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def mark_stale_apply_runs_failed(
        self,
        *,
        lease_seconds: int = DEFAULT_APPLY_CLAIM_LEASE_SECONDS,
    ) -> int:
        """Convert stale PENDING apply runs to FAILED on startup.

        Purpose:
            Handle worker crash recovery by marking orphaned PENDING apply runs
            failed so they become retry-eligible.
        Args:
            self: The database manager performing stale-run cleanup.
            lease_seconds: Age threshold in seconds for stale PENDING rows.
        Output:
            Returns number of rows converted to FAILED.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        lease_modifier = f"-{max(lease_seconds, 1)} seconds"
        cursor = await conn.execute(
            """
            UPDATE apply_runs
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

    async def get_apply_failure_count(self, review_run_id: int) -> int:
        """Count FAILED apply runs for one review run identifier.

        Purpose:
            Provide efficient retry-count lookups for apply worker backoff and
            terminal-failure decisions.
        Args:
            self: The database manager querying failure counts.
            review_run_id: Review run identifier associated with apply attempts.
        Output:
            Returns number of FAILED apply_runs rows for the review run.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM apply_runs WHERE review_run_id = ? AND status = 'FAILED'",
            (review_run_id,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def migrate_cost_schema(self) -> None:
        """Create cost telemetry and budget tables when missing.

        Purpose:
            Bootstrap forward-only cost tracking and monthly budget settings so
            dashboard endpoints can report spend without separate migrations.
        Args:
            self: The database manager performing the migration.
        Output:
            Returns `None` after ensuring cost tables and indexes exist.
        """

        conn = self._require_conn()
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cost_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stage TEXT NOT NULL,
                job_hash TEXT,
                run_id TEXT,
                cost_usd REAL NOT NULL,
                metadata_json TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CHECK (stage IN ('GATE', 'TAILOR', 'REVIEW', 'APPLY', 'DISCOVERY')),
                CHECK (cost_usd >= 0)
            );
            CREATE INDEX IF NOT EXISTS idx_cost_events_recorded_at
                ON cost_events(recorded_at);
            CREATE INDEX IF NOT EXISTS idx_cost_events_stage_recorded_at
                ON cost_events(stage, recorded_at);
            CREATE INDEX IF NOT EXISTS idx_cost_events_job_hash
                ON cost_events(job_hash);

            CREATE TABLE IF NOT EXISTS budget_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                monthly_budget_usd REAL NOT NULL DEFAULT 500.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CHECK (monthly_budget_usd >= 0)
            );
            """
        )
        await conn.execute(
            """
            INSERT INTO budget_settings (id, monthly_budget_usd)
            VALUES (1, 500.0)
            ON CONFLICT(id) DO NOTHING
            """
        )
        await conn.commit()
        self._cost_schema_ready = True

    async def _ensure_cost_schema_ready(self) -> None:
        """Ensure cost telemetry tables exist before cost queries run.

        Purpose:
            Prevent runtime SQL failures when cost endpoints run against older
            databases that were created before cost tracking was added.
        Args:
            self: The database manager validating cost-schema readiness.
        Output:
            Returns `None` after ensuring required cost tables exist.
        """

        if self._cost_schema_ready:
            return

        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cost_events'"
        )
        row = await cursor.fetchone()
        if row is not None:
            self._cost_schema_ready = True
            return

        await self.migrate_cost_schema()

    async def record_cost_event(
        self,
        *,
        stage: str,
        cost_usd: float,
        job_hash: str | None = None,
        run_id: str | None = None,
        metadata_json: str | None = None,
    ) -> None:
        """Record one pipeline execution cost event.

        Purpose:
            Persist stage-level spend in a forward-only event table so costs
            can be rolled up by day and by stage without historical rewrites.
        Args:
            self: The database manager writing telemetry.
            stage: Pipeline stage label (GATE, TAILOR, REVIEW, APPLY, DISCOVERY).
            cost_usd: Non-negative USD cost for this execution attempt.
            job_hash: Optional stable job identifier for correlation.
            run_id: Optional worker run identifier.
            metadata_json: Optional JSON string with model/provider context.
        Output:
            Returns `None` after inserting the event and committing.
        Raises:
            ValueError: When `cost_usd` is negative.
        """

        if cost_usd < 0:
            raise ValueError("cost_usd must be non-negative")

        await self._ensure_cost_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            """
            INSERT INTO cost_events (
                stage,
                job_hash,
                run_id,
                cost_usd,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (stage, job_hash, run_id, cost_usd, metadata_json),
        )
        await conn.commit()

    async def get_budget_settings(self) -> dict:
        """Fetch monthly budget with current month spend rollup.

        Purpose:
            Provide one canonical budget payload for both settings and sidebar
            widgets without duplicating spend math in route handlers.
        Args:
            self: The database manager loading budget and spend aggregates.
        Output:
            Returns a dictionary with `monthly_budget_usd`, `spent_usd`,
            `remaining_usd`, and `utilization_pct`.
        """

        await self._ensure_cost_schema_ready()
        conn = self._require_conn()

        budget_cursor = await conn.execute(
            """
            SELECT monthly_budget_usd
            FROM budget_settings
            WHERE id = 1
            """
        )
        budget_row = await budget_cursor.fetchone()
        budget_value = (
            float(budget_row["monthly_budget_usd"])
            if budget_row
            else DEFAULT_MONTHLY_BUDGET_USD
        )

        spend_cursor = await conn.execute(
            """
            SELECT COALESCE(SUM(cost_usd), 0.0) AS spent_usd
            FROM cost_events
            WHERE strftime('%Y-%m', recorded_at) = strftime('%Y-%m', 'now')
            """
        )
        spend_row = await spend_cursor.fetchone()
        spent_value = float(spend_row["spent_usd"]) if spend_row else 0.0
        remaining_value = max(budget_value - spent_value, 0.0)
        utilization = 0.0 if budget_value <= 0 else (spent_value / budget_value) * 100.0

        return {
            "monthly_budget_usd": budget_value,
            "spent_usd": spent_value,
            "remaining_usd": remaining_value,
            "utilization_pct": utilization,
        }

    async def is_budget_exceeded(self) -> bool:
        """Return whether the monthly budget has been exhausted.

        Purpose:
            Provide one reusable guard for workers that must stop claiming new
            jobs once budget is exhausted while allowing in-flight work to finish.
        Args:
            self: The database manager reading the current budget snapshot.
        Output:
            Returns `True` when remaining budget is zero, otherwise `False`.
        """

        budget_snapshot = await self.get_budget_settings()
        remaining_usd = float(budget_snapshot.get("remaining_usd", 0.0))
        return remaining_usd <= 0.0

    async def set_budget_settings(self, *, monthly_budget_usd: float) -> dict:
        """Persist a new monthly budget value and return the updated snapshot.

        Purpose:
            Keep budget writes idempotent while returning the latest spend and
            utilization values for immediate UI refresh after save.
        Args:
            self: The database manager persisting the new budget.
            monthly_budget_usd: New non-negative monthly budget in USD.
        Output:
            Returns the same payload shape as `get_budget_settings()`.
        Raises:
            ValueError: When `monthly_budget_usd` is negative.
        """

        if monthly_budget_usd < 0:
            raise ValueError("monthly_budget_usd must be non-negative")

        await self._ensure_cost_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            """
            INSERT INTO budget_settings (id, monthly_budget_usd, updated_at)
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                monthly_budget_usd = excluded.monthly_budget_usd,
                updated_at = CURRENT_TIMESTAMP
            """,
            (monthly_budget_usd,),
        )
        await conn.commit()
        return await self.get_budget_settings()

    async def transition_handoff_status(
        self,
        *,
        handoff_id: int,
        target_status: str,
        reviewer_notes: str | None = None,
    ) -> dict:
        """Resolve a human-review handoff and update job status atomically.

        Purpose:
            Apply APPROVED/REJECTED decisions safely, enforce one-way handoff
            transitions, and keep job_postings status aligned with review action.
        Args:
            self: The database manager applying the transition.
            handoff_id: Primary key of the `apply_handoffs` row to resolve.
            target_status: Final handoff status (`APPROVED` or `REJECTED`).
            reviewer_notes: Optional reviewer note text.
        Output:
            Returns the resolved handoff row as a dictionary.
        Raises:
            ValueError: When the handoff does not exist or transition is invalid.
        """

        allowed_targets = {"APPROVED", "REJECTED"}
        if target_status not in allowed_targets:
            raise ValueError(f"Unsupported handoff target status: {target_status}")

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            cursor = await conn.execute(
                "SELECT * FROM apply_handoffs WHERE id = ?",
                (handoff_id,),
            )
            handoff_row = await cursor.fetchone()
            if handoff_row is None:
                await conn.rollback()
                raise ValueError("handoff_not_found")

            current_status = str(handoff_row["handoff_status"])
            if current_status != "PENDING_REVIEW":
                await conn.rollback()
                raise ValueError("handoff_already_resolved")

            await conn.execute(
                """
                UPDATE apply_handoffs
                SET handoff_status = ?,
                    reviewer_notes = ?,
                    reviewed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (target_status, reviewer_notes, handoff_id),
            )

            resolved_job_status = (
                "APPLIED" if target_status == "APPROVED" else "REJECTED"
            )
            await conn.execute(
                """
                UPDATE job_postings
                SET status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_hash = ?
                """,
                (resolved_job_status, handoff_row["job_hash"]),
            )

            updated_cursor = await conn.execute(
                "SELECT * FROM apply_handoffs WHERE id = ?",
                (handoff_id,),
            )
            updated_row = await updated_cursor.fetchone()
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

        if updated_row is None:
            raise ValueError("handoff_update_failed")
        return dict(updated_row)

    async def reset_review_failure_state(self, *, job_hash: str) -> int:
        """Delete FAILED review runs for all tailor runs linked to one job.

        Purpose:
            Requeue review-stage failures by removing terminal FAILED rows so
            claim queries can pick the same tailor output again.
        Args:
            self: The database manager clearing review failure rows.
            job_hash: Stable job identifier tied to related tailor runs.
        Output:
            Returns the number of deleted FAILED review rows.
        """

        await self._ensure_review_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            """
            DELETE FROM review_runs
            WHERE status = 'FAILED'
              AND tailor_run_id IN (
                  SELECT id FROM tailor_runs WHERE job_hash = ?
              )
            """,
            (job_hash,),
        )
        await conn.commit()
        return cursor.rowcount

    async def reset_apply_failure_state(self, *, job_hash: str) -> int:
        """Delete FAILED apply runs for all review runs linked to one job.

        Purpose:
            Requeue apply-stage failures by removing terminal FAILED rows so
            claim queries can process the same review result again.
        Args:
            self: The database manager clearing apply failure rows.
            job_hash: Stable job identifier tied to related review runs.
        Output:
            Returns the number of deleted FAILED apply rows.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            """
            DELETE FROM apply_runs
            WHERE status = 'FAILED'
              AND review_run_id IN (
                  SELECT id FROM review_runs WHERE job_hash = ?
              )
            """,
            (job_hash,),
        )
        await conn.commit()
        return cursor.rowcount

    async def close(self) -> None:
        """Close the active SQLite connection if one exists.

        Purpose:
            Release the file-backed database connection cleanly at the end of a
            workflow run or async context-manager block.
        Args:
            self: The database manager shutting down its connection.
        Output:
            Returns `None` after closing the connection and clearing `self.conn`.
        """

        if self.conn:
            await self.conn.close()
            self.conn = None

    async def __aenter__(self):
        """Open the database connection when entering the async context.

        Purpose:
            Make `DatabaseManager` usable with `async with` so callers do not
            have to remember to call `connect()` manually.
        Args:
            self: The database manager entering the async context.
        Output:
            Returns the database manager instance after connecting.
        """

        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the database connection when exiting the async context.

        Purpose:
            Ensure connection cleanup happens even when the caller exits the
            context because of an exception.
        Args:
            self: The database manager exiting the async context.
            exc_type: Exception type raised inside the context, if any.
            exc_val: Exception instance raised inside the context, if any.
            exc_tb: Traceback for the exception raised inside the context.
        Output:
            Returns `None` after closing the active connection.
        """

        await self.close()
