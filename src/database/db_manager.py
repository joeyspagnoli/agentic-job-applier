"""Manage SQLite persistence for job discovery and agent workflows.

This module owns connection setup, schema bootstrap, crawl tracking, job
queries, and the extra state needed by the apply/skip agent pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import aiosqlite
from loguru import logger


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
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row
        self._agent_schema_ready = False

        # These pragmas reduce lock contention during timer-driven runs while
        # still keeping the database simple and file-backed.
        await self.conn.execute("PRAGMA busy_timeout = 5000")
        await self.conn.execute("PRAGMA journal_mode = WAL")

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
        """Fetch NEW jobs that have not been processed by the agent.

        Purpose:
            Feed the agent-processing script only the rows that are still ready
            for a first decision and have not already failed permanently.
        Args:
            self: The database manager performing the query.
            limit: Maximum number of rows to return in one batch.
        Output:
            Returns a list of pending job rows as dictionaries ordered by newest
            `fetched_at` first.
        """

        await self._ensure_agent_schema_ready()
        conn = self._require_conn()

        # Failed rows are excluded to avoid infinite retry loops until a human
        # explicitly decides how to handle them.
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
                status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (agent_result, status, job_hash),
        )
        await conn.commit()

    async def mark_job_agent_failed(self, job_hash: str, error: str) -> None:
        """Record an agent-processing failure for a job.

        Purpose:
            Mark jobs that failed during agent execution so they can be reviewed
            without being retried forever on every loop iteration.
        Args:
            self: The database manager recording the failure.
            job_hash: Stable deduplication hash for the target job.
            error: Error message describing why agent processing failed.
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
                updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (error, job_hash),
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
