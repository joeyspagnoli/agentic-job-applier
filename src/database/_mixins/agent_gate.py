"""Gate-stage agent decision, retry, and failure helpers.

Owns the agent-processing columns on `job_postings` plus the lightweight
schema migration that backfills those columns on older databases.
Methods here record the outcome of one agent decision per job.
"""

from __future__ import annotations

from loguru import logger

from src.database._mixins.base import _BaseMixin


class AgentGateMixin(_BaseMixin):
    """Agent-decision recording, retry tracking, and failure markers."""

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
