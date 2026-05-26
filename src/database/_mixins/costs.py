"""Cost telemetry, budget, and service-tier helpers.

Owns the `cost_events`, `budget_settings`, and `app_settings` tables.
Recorded cost events feed dashboards while the budget rollup powers
worker guards and the settings UI.

Per-LLM-call columns (`provider`, `model`, `prompt_tokens`,
`completion_tokens`, `cached_input_tokens`, `reasoning_tokens`,
`phase`, `cost_source`) let dashboards break spend down by model and
phase. Existing rows are backfilled to `unknown` via the
PRAGMA-guarded `ALTER TABLE` block.
"""

from __future__ import annotations

from src.database._mixins.base import _BaseMixin
from src.utils.json_types import JSONObject, get_float_opt

DEFAULT_MONTHLY_BUDGET_USD = 500.0

# Per-LLM-call columns that extend the base cost_events schema. Each entry is
# (column_name, column_definition_sql) and is applied via PRAGMA-guarded
# ALTER TABLE so the migration is idempotent on pre-existing databases.
_COST_EVENTS_NEW_COLUMNS: tuple[tuple[str, str], ...] = (
    ("provider", "TEXT NOT NULL DEFAULT 'unknown'"),
    ("model", "TEXT NOT NULL DEFAULT 'unknown'"),
    ("prompt_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("completion_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("cached_input_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("reasoning_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("phase", "TEXT"),
    ("cost_source", "TEXT NOT NULL DEFAULT 'unknown'"),
)


class CostsMixin(_BaseMixin):
    """Cost telemetry, monthly budget, and service-tier persistence."""

    async def migrate_cost_schema(self) -> None:
        """Create cost telemetry and budget tables when missing.

        Purpose:
            Bootstrap forward-only cost tracking and monthly budget settings so
            dashboard endpoints can report spend without separate migrations.
            Also applies PRAGMA-guarded `ALTER TABLE` for the per-LLM-call
            columns so existing databases pick them up on the next startup.
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
                provider TEXT NOT NULL DEFAULT 'unknown',
                model TEXT NOT NULL DEFAULT 'unknown',
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                cached_input_tokens INTEGER NOT NULL DEFAULT 0,
                reasoning_tokens INTEGER NOT NULL DEFAULT 0,
                phase TEXT,
                cost_source TEXT NOT NULL DEFAULT 'unknown',
                CHECK (stage IN ('GATE', 'TAILOR', 'REVIEW', 'APPLY', 'DISCOVERY')),
                CHECK (cost_usd >= 0),
                CHECK (cost_source IN ('provider', 'computed', 'internal', 'unknown'))
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

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )

        # Idempotent ALTER for databases that predate the per-LLM-call
        # columns. SQLite has no `ADD COLUMN IF NOT EXISTS`, so probe
        # with `PRAGMA table_info` first.
        existing_cursor = await conn.execute("PRAGMA table_info(cost_events)")
        existing_rows = await existing_cursor.fetchall()
        existing_columns = {str(row["name"]) for row in existing_rows}
        for column_name, column_definition in _COST_EVENTS_NEW_COLUMNS:
            if column_name in existing_columns:
                continue
            await conn.execute(
                f"ALTER TABLE cost_events ADD COLUMN {column_name} {column_definition}"
            )

        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cost_events_run_id ON cost_events(run_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cost_events_model ON cost_events(model)"
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
        provider: str = "unknown",
        model: str = "unknown",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_input_tokens: int = 0,
        reasoning_tokens: int = 0,
        phase: str | None = None,
        cost_source: str = "unknown",
    ) -> None:
        """Record one LLM-call cost event with full provider/token detail.

        Purpose:
            Persist stage-level spend in a forward-only event table so costs
            can be rolled up by day, stage, model, and phase without
            historical rewrites or runtime re-pricing.
        Args:
            self: The database manager writing telemetry.
            stage: Pipeline stage label (GATE, TAILOR, REVIEW, APPLY, DISCOVERY).
            cost_usd: Non-negative USD cost for this execution attempt.
            job_hash: Optional stable job identifier for correlation.
            run_id: Optional worker run identifier.
            metadata_json: Optional JSON string with full context payload.
            provider: Provider that handled the call (`openai`, `internal`).
            model: Model identifier returned by the provider.
            prompt_tokens: Billable prompt tokens (includes cached).
            completion_tokens: Completion tokens produced.
            cached_input_tokens: Cached subset of `prompt_tokens`.
            reasoning_tokens: Hidden reasoning tokens (gpt-5.x families).
            phase: Optional sub-phase within the stage.
            cost_source: How the cost was derived
                (`provider`, `computed`, `internal`, `unknown`).
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
                metadata_json,
                provider,
                model,
                prompt_tokens,
                completion_tokens,
                cached_input_tokens,
                reasoning_tokens,
                phase,
                cost_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stage,
                job_hash,
                run_id,
                cost_usd,
                metadata_json,
                provider,
                model,
                prompt_tokens,
                completion_tokens,
                cached_input_tokens,
                reasoning_tokens,
                phase,
                cost_source,
            ),
        )
        await conn.commit()

    async def get_budget_settings(self) -> JSONObject:
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
        remaining_usd = get_float_opt(budget_snapshot, "remaining_usd") or 0.0
        return remaining_usd <= 0.0

    async def set_budget_settings(
        self,
        *,
        monthly_budget_usd: float,
    ) -> JSONObject:
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

    async def get_service_tier(self) -> str:
        """Return the currently persisted service tier.

        Purpose:
            Provide the settings UI with the active pipeline tier so it can
            pre-select the correct card on load.
        Args:
            self: The database manager reading from app_settings.
        Output:
            Returns the tier string ('base', 'latex', or 'full').
        """

        await self._ensure_cost_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT value FROM app_settings WHERE key = 'service_tier'"
        )
        row = await cursor.fetchone()
        return str(row["value"]) if row else "base"

    async def set_service_tier(self, tier: str) -> str:
        """Persist the selected service tier.

        Purpose:
            Keep the active pipeline tier durable across restarts so the worker
            scripts pick up the correct stage gate configuration.
        Args:
            self: The database manager writing the tier.
            tier: One of 'base', 'latex', or 'full'.
        Output:
            Returns the persisted tier string.
        """

        await self._ensure_cost_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES ('service_tier', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (tier,),
        )
        await conn.commit()
        return tier
