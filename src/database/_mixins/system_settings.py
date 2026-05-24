"""System-wide configuration toggles backed by SQLite.

Owns the `system_settings` table, a generic key/value store for runtime
toggles that the worker and the API both need to read every poll cycle.

The first consumer is per-stage automation mode — `automation.tailor_mode`,
one of `{autonomous, opt_in, both}` — which controls whether the
resume-tailor worker daemon claims jobs or idles while waiting for
user-triggered runs.
"""

from __future__ import annotations

import os
from typing import Optional

from loguru import logger

from src.database._mixins.base import _BaseMixin

AUTOMATION_MODES: tuple[str, ...] = ("autonomous", "opt_in", "both")

GATE_MODE_KEY = "automation.gate_mode"
TAILOR_MODE_KEY = "automation.tailor_mode"
APPLY_MODE_KEY = "automation.apply_mode"

GATE_MODE_ENV_VAR = "GATE_MODE"
TAILOR_MODE_ENV_VAR = "TAILOR_MODE"
APPLY_MODE_ENV_VAR = "APPLY_MODE"

# Per-stage settings keys exposed for the supervisor and API to enumerate.
AUTOMATION_STAGE_KEYS: tuple[str, ...] = (
    GATE_MODE_KEY,
    TAILOR_MODE_KEY,
    APPLY_MODE_KEY,
)

DEFAULT_AUTOMATION_MODE = "opt_in"


def _normalize_mode_or_none(raw: Optional[str]) -> Optional[str]:
    """Return a validated automation mode or `None` for unknown input.

    Purpose:
        Guard the env-seeding path so a typo in `TAILOR_MODE` does not
        leak an invalid string into the database.
    Args:
        raw: Raw env-var value (case-insensitive) or `None`.
    Output:
        Returns the lowercased mode when it is one of `AUTOMATION_MODES`,
        otherwise `None`.
    """

    if raw is None:
        return None
    candidate = raw.strip().lower()
    if candidate in AUTOMATION_MODES:
        return candidate
    return None


class SystemSettingsMixin(_BaseMixin):
    """`system_settings` table CRUD and automation-mode helpers."""

    async def migrate_system_settings_schema(self) -> None:
        """Create the `system_settings` table when missing.

        Purpose:
            Bootstrap the generic key/value settings table idempotently so
            the worker and API can both rely on a runtime toggle store
            without a separate migration step.
        Args:
            self: The database manager performing the migration.
        Output:
            Returns `None` after ensuring the table exists.
        """

        conn = self._require_conn()
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await conn.commit()
        self._system_settings_schema_ready = True

    async def _ensure_system_settings_schema_ready(self) -> None:
        """Ensure the `system_settings` table exists before reads/writes.

        Purpose:
            Mirror the per-stage schema-ready guards used by the other
            mixins so query methods never hit a missing table.
        Args:
            self: The database manager validating system-settings readiness.
        Output:
            Returns `None` after ensuring the table exists.
        """

        if self._system_settings_schema_ready:
            return

        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='system_settings'"
        )
        row = await cursor.fetchone()
        if row is not None:
            self._system_settings_schema_ready = True
            return

        await self.migrate_system_settings_schema()

    async def get_system_setting(self, key: str) -> Optional[str]:
        """Return the stored value for one setting key.

        Purpose:
            Provide a typed read path for the worker (every poll cycle)
            and the API routers without each call site re-implementing
            the SELECT.
        Args:
            self: The database manager performing the lookup.
            key: Full settings key (e.g. `automation.tailor_mode`).
        Output:
            Returns the stored string value, or `None` when the key has
            no row.
        """

        await self._ensure_system_settings_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT value FROM system_settings WHERE key = ?",
            (key,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return str(row["value"])

    async def set_system_setting(self, key: str, value: str) -> None:
        """Insert or update one settings row.

        Purpose:
            Provide a single write path used by the settings router and
            the env-seeding helper so timestamps stay consistent.
        Args:
            self: The database manager performing the write.
            key: Full settings key.
            value: Value to persist; must be a non-empty string.
        Output:
            Returns `None` after committing the row.
        """

        await self._ensure_system_settings_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE
                SET value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )
        await conn.commit()

    async def get_automation_mode(
        self,
        key: str,
        *,
        default: str = DEFAULT_AUTOMATION_MODE,
    ) -> str:
        """Return the stored automation mode for one stage key.

        Purpose:
            Read a `{autonomous, opt_in, both}` mode with a safe default
            when the row is missing or contains a value that is no longer
            in the allowed set.
        Args:
            self: The database manager performing the lookup.
            key: The settings key, e.g. `automation.tailor_mode`.
            default: Fallback mode used when the key is missing or invalid.
        Output:
            Returns one of `AUTOMATION_MODES`.
        """

        raw = await self.get_system_setting(key)
        if raw is None:
            return default
        candidate = raw.strip().lower()
        if candidate not in AUTOMATION_MODES:
            logger.warning(
                "Invalid automation mode in system_settings: key={} value={}; using default={}",
                key,
                raw,
                default,
            )
            return default
        return candidate

    async def set_automation_mode(self, key: str, mode: str) -> None:
        """Validate and persist an automation-mode value.

        Purpose:
            Centralize enum validation so callers cannot persist a typo.
        Args:
            self: The database manager performing the write.
            key: The settings key, e.g. `automation.tailor_mode`.
            mode: One of `AUTOMATION_MODES`.
        Output:
            Returns `None` after committing the row.
        Raises:
            ValueError: When `mode` is not a recognized automation mode.
        """

        normalized = mode.strip().lower()
        if normalized not in AUTOMATION_MODES:
            raise ValueError(
                f"Invalid automation mode {mode!r}; expected one of {AUTOMATION_MODES}"
            )
        await self.set_system_setting(key, normalized)

    async def seed_automation_defaults_from_env(self) -> None:
        """Populate missing automation rows from env vars or the default.

        Purpose:
            On first boot — and only when the key is missing — copy the
            value from `TAILOR_MODE` into the database, falling back to
            `DEFAULT_AUTOMATION_MODE` when the env var is unset or
            invalid. Subsequent boots leave the stored value alone so
            user edits via the Settings UI persist.
        Args:
            self: The database manager performing the seeding.
        Output:
            Returns `None` after inserting any missing rows.
        """

        await self._ensure_system_settings_schema_ready()
        env_seeds: tuple[tuple[str, str], ...] = (
            (GATE_MODE_KEY, GATE_MODE_ENV_VAR),
            (TAILOR_MODE_KEY, TAILOR_MODE_ENV_VAR),
            (APPLY_MODE_KEY, APPLY_MODE_ENV_VAR),
        )

        for setting_key, env_var in env_seeds:
            existing = await self.get_system_setting(setting_key)
            if existing is not None:
                continue
            from_env = _normalize_mode_or_none(os.getenv(env_var))
            seed_value = from_env if from_env is not None else DEFAULT_AUTOMATION_MODE
            await self.set_system_setting(setting_key, seed_value)
            logger.info(
                "Seeded {} = {} (source={})",
                setting_key,
                seed_value,
                "env" if from_env is not None else "default",
            )
