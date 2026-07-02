"""Manage SQLite persistence for job discovery and agent workflows.

This module composes one `DatabaseManager` from the per-concern mixin
classes under `src/database/_mixins/`. Connection setup, schema
bootstrap, and the async-context-manager protocol live here; everything
else delegates to the matching mixin via Python's MRO.

Public re-exports keep the historical import surface stable:

* `DatabaseManager` — the composed class.
* `ClaimOwnershipError` — raised when claim tokens disagree with state.
* `DEFAULT_AGENT_CLAIM_LEASE_SECONDS`,
  `DEFAULT_TAILOR_CLAIM_LEASE_SECONDS`,
  `DEFAULT_REVIEW_CLAIM_LEASE_SECONDS`,
  `DEFAULT_APPLY_CLAIM_LEASE_SECONDS`,
  `DEFAULT_MONTHLY_BUDGET_USD` — operator-tunable defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import aiosqlite
from loguru import logger

from src.database._mixins.agent_gate import AgentGateMixin
from src.database._mixins.apply import (
    DEFAULT_APPLY_CLAIM_LEASE_SECONDS,
    ApplyMixin,
)
from src.database._mixins.costs import (
    DEFAULT_MONTHLY_BUDGET_USD,
    CostsMixin,
)
from src.database._mixins.failure_resets import FailureResetsMixin
from src.database._mixins.jobs import (
    DEFAULT_AGENT_CLAIM_LEASE_SECONDS,
    JobsMixin,
)
from src.database._mixins.review import (
    DEFAULT_REVIEW_CLAIM_LEASE_SECONDS,
    ClaimOwnershipError,
    ReviewMixin,
)
from src.database._mixins.system_settings import SystemSettingsMixin
from src.database._mixins.tailor import (
    DEFAULT_TAILOR_CLAIM_LEASE_SECONDS,
    TailorMixin,
)
from src.database._mixins.telemetry import TelemetryMixin

__all__ = [
    "ClaimOwnershipError",
    "DEFAULT_AGENT_CLAIM_LEASE_SECONDS",
    "DEFAULT_APPLY_CLAIM_LEASE_SECONDS",
    "DEFAULT_MONTHLY_BUDGET_USD",
    "DEFAULT_REVIEW_CLAIM_LEASE_SECONDS",
    "DEFAULT_TAILOR_CLAIM_LEASE_SECONDS",
    "DatabaseManager",
]

_JOURNAL_MODE_SQL: dict[str, str] = {
    "DELETE": "PRAGMA journal_mode = DELETE",
    "TRUNCATE": "PRAGMA journal_mode = TRUNCATE",
    "PERSIST": "PRAGMA journal_mode = PERSIST",
    "MEMORY": "PRAGMA journal_mode = MEMORY",
    "WAL": "PRAGMA journal_mode = WAL",
}


class DatabaseManager(
    JobsMixin,
    TelemetryMixin,
    AgentGateMixin,
    TailorMixin,
    ReviewMixin,
    ApplyMixin,
    CostsMixin,
    FailureResetsMixin,
    SystemSettingsMixin,
):
    """Async SQLite database manager for job postings and crawl metadata.

    Composes every per-concern mixin under `src/database/_mixins/` so the
    historical public API remains intact. Per-stage helpers are grouped
    by table:

    * `JobsMixin` — `job_postings` CRUD, status, and pending-claim.
    * `TelemetryMixin` — `crawl_history` and `daily_stats`.
    * `AgentGateMixin` — agent-decision columns on `job_postings`.
    * `TailorMixin` — `tailor_runs`.
    * `ReviewMixin` — `review_runs`.
    * `ApplyMixin` — `apply_runs` plus `apply_handoffs`.
    * `CostsMixin` — `cost_events`, `budget_settings`, `app_settings`.
    * `FailureResetsMixin` — operator-facing requeue helpers across
      every stage.
    """

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
        self._system_settings_schema_ready = False

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
        self._system_settings_schema_ready = False

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

        # Mixin migrations handle schema additions that post-date schema.sql so
        # existing databases pick up new columns/CHECKs without manual steps.
        await self.migrate_tailor_schema()
        await self.migrate_review_schema()
        await self.migrate_system_settings_schema()
        await self.migrate_subscriber_schema()
        await self.seed_automation_defaults_from_env()

    async def migrate_subscriber_schema(self) -> None:
        """Create email_subscribers and digest_sends tables when missing."""

        conn = self._require_conn()
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS email_subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                role_level TEXT NOT NULL DEFAULT 'both',
                fields TEXT DEFAULT NULL,
                location_preference TEXT NOT NULL DEFAULT 'both',
                excluded_companies TEXT DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                confirmed INTEGER NOT NULL DEFAULT 0,
                confirm_token TEXT NOT NULL,
                unsubscribe_token TEXT NOT NULL,
                last_digest_at TEXT DEFAULT NULL,
                bounce_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS digest_sends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscriber_id INTEGER NOT NULL REFERENCES email_subscribers(id),
                job_id INTEGER NOT NULL REFERENCES job_postings(id),
                sent_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_digest_sends_sub ON digest_sends(subscriber_id);
            CREATE INDEX IF NOT EXISTS idx_digest_sends_job ON digest_sends(job_id);
            """
        )
        await conn.commit()

    async def cleanup_old_records(self, crawl_days: int = 90, job_days: int = 90) -> dict[str, int]:
        """Delete crawl_history and stale job_postings older than the given thresholds."""
        conn = self._require_conn()
        cur = await conn.execute(
            f"DELETE FROM crawl_history WHERE started_at < datetime('now', '-{crawl_days} days')"
        )
        crawl_deleted = cur.rowcount
        cur = await conn.execute(
            f"DELETE FROM job_postings WHERE status = 'NEW' AND fetched_at < datetime('now', '-{job_days} days')"
        )
        jobs_deleted = cur.rowcount
        await conn.commit()
        return {"crawl_deleted": crawl_deleted, "jobs_deleted": jobs_deleted}

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

    async def __aenter__(self) -> "DatabaseManager":
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

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
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
