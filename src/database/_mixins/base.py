"""Shared base for `DatabaseManager` mixins.

Mixins reach into shared instance state — the active SQLite connection
and per-stage schema-readiness flags — that lives on `DatabaseManager`.
Defining those attributes once on `_BaseMixin` keeps each mixin file
self-contained for type checkers without duplicating signatures.
"""

from __future__ import annotations

from typing import Optional

import aiosqlite


class _BaseMixin:
    """Typed view of the shared `DatabaseManager` internals.

    Purpose:
        Expose the connection slot, the `_require_conn` guard, and the
        per-stage schema-readiness flags so mixin methods type-check
        without each one redeclaring the same attributes. Cross-mixin
        schema-ensure entry points are also declared here so call sites
        like `JobsMixin -> AgentGateMixin._ensure_agent_schema_ready`
        type-check while Python's MRO dispatches to the real override
        inside `DatabaseManager`.
    Args:
        None: This is a structural base; the real values are set by
            `DatabaseManager.__init__` and by the concrete mixins.
    Output:
        Subclassed by every mixin module under `src/database/_mixins/`.
    """

    db_path: str
    conn: Optional[aiosqlite.Connection]
    _agent_schema_ready: bool
    _tailor_schema_ready: bool
    _review_schema_ready: bool
    _apply_schema_ready: bool
    _cost_schema_ready: bool

    def _require_conn(self) -> aiosqlite.Connection:
        """Return the active SQLite connection or fail fast.

        Purpose:
            Centralize the guard that prevents query methods from running
            before `connect()` or the async context manager has been used.
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

    async def _ensure_agent_schema_ready(self) -> None:
        """Forward declaration; overridden by `AgentGateMixin`.

        Purpose:
            Provide a typed entry point so cross-mixin callers (for example
            `JobsMixin.get_jobs_pending_agent_processing`) can rely on the
            agent-schema bootstrap without each mixin importing every other.
            The real body lives in `AgentGateMixin` and is selected by
            Python's MRO inside `DatabaseManager`.
        Args:
            self: The database manager validating agent-schema readiness.
        Output:
            Never returns from this base; the override always supersedes.
        """

        raise NotImplementedError(
            "_ensure_agent_schema_ready must be provided by AgentGateMixin"
        )

    async def _ensure_tailor_schema_ready(self) -> None:
        """Forward declaration; overridden by `TailorMixin`.

        Purpose:
            Provide a typed entry point so review and failure-reset mixins
            can guarantee the tailor schema is migrated before they query it.
            The real body lives in `TailorMixin`.
        Args:
            self: The database manager validating tailor-schema readiness.
        Output:
            Never returns from this base; the override always supersedes.
        """

        raise NotImplementedError(
            "_ensure_tailor_schema_ready must be provided by TailorMixin"
        )

    async def _ensure_review_schema_ready(self) -> None:
        """Forward declaration; overridden by `ReviewMixin`.

        Purpose:
            Provide a typed entry point so the apply and failure-reset mixins
            can guarantee the review schema is migrated before they query it.
            The real body lives in `ReviewMixin`.
        Args:
            self: The database manager validating review-schema readiness.
        Output:
            Never returns from this base; the override always supersedes.
        """

        raise NotImplementedError(
            "_ensure_review_schema_ready must be provided by ReviewMixin"
        )

    async def _ensure_apply_schema_ready(self) -> None:
        """Forward declaration; overridden by `ApplyMixin`.

        Purpose:
            Provide a typed entry point so the failure-reset mixin can
            guarantee the apply schema is migrated before deleting rows.
            The real body lives in `ApplyMixin`.
        Args:
            self: The database manager validating apply-schema readiness.
        Output:
            Never returns from this base; the override always supersedes.
        """

        raise NotImplementedError(
            "_ensure_apply_schema_ready must be provided by ApplyMixin"
        )
