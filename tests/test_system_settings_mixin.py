"""Tests for the `SystemSettingsMixin` automation-mode helpers.

Purpose:
    Lock in the behavioral contract of the new `system_settings` table —
    env-driven first-boot seeding, invalid-value fallback, and explicit
    `set_automation_mode` validation — independent of any other stage.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio

from src.database._mixins.system_settings import (
    AUTOMATION_MODES,
    DEFAULT_AUTOMATION_MODE,
    TAILOR_MODE_KEY,
)
from src.database.db_manager import DatabaseManager


@pytest_asyncio.fixture
async def fresh_db(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Provide a clean DatabaseManager with the system_settings table migrated.

    Purpose:
        Hand each test an isolated SQLite file with the new schema bootstrapped
        but no automation rows present yet, so seeding paths can be observed.
    Args:
        tmp_path: Per-test temporary directory injected by pytest.
    Output:
        Yields a connected `DatabaseManager`; the connection is closed on
        teardown.
    """

    manager = DatabaseManager(str(tmp_path / "settings.db"))
    await manager.connect()
    await manager.migrate_system_settings_schema()
    yield manager
    await manager.close()


@pytest.mark.asyncio
async def test_get_system_setting_returns_none_when_key_missing(
    fresh_db: DatabaseManager,
) -> None:
    """Missing rows return `None` instead of raising.

    Purpose:
        Confirm the value-lookup path is safe to call before any seeding.
    """

    result = await fresh_db.get_system_setting("nonexistent.key")

    assert result is None


@pytest.mark.asyncio
async def test_set_and_get_system_setting_round_trips_value(
    fresh_db: DatabaseManager,
) -> None:
    """Writes are visible to the next read on the same connection."""

    await fresh_db.set_system_setting("custom.key", "custom-value")

    result = await fresh_db.get_system_setting("custom.key")

    assert result == "custom-value"


@pytest.mark.asyncio
async def test_set_system_setting_upserts_existing_row(
    fresh_db: DatabaseManager,
) -> None:
    """Writing the same key twice replaces the prior value."""

    await fresh_db.set_system_setting("custom.key", "first")
    await fresh_db.set_system_setting("custom.key", "second")

    result = await fresh_db.get_system_setting("custom.key")

    assert result == "second"


@pytest.mark.asyncio
async def test_get_automation_mode_returns_default_when_missing(
    fresh_db: DatabaseManager,
) -> None:
    """Missing automation rows fall back to the supplied default."""

    result = await fresh_db.get_automation_mode(TAILOR_MODE_KEY)

    assert result == DEFAULT_AUTOMATION_MODE


@pytest.mark.asyncio
async def test_get_automation_mode_respects_explicit_default(
    fresh_db: DatabaseManager,
) -> None:
    """Caller-supplied defaults override the module default."""

    result = await fresh_db.get_automation_mode(TAILOR_MODE_KEY, default="autonomous")

    assert result == "autonomous"


@pytest.mark.asyncio
async def test_get_automation_mode_returns_stored_value_lowercased(
    fresh_db: DatabaseManager,
) -> None:
    """A stored value is returned as-is when it is a recognized mode."""

    await fresh_db.set_automation_mode(TAILOR_MODE_KEY, "BOTH")

    result = await fresh_db.get_automation_mode(TAILOR_MODE_KEY)

    assert result == "both"


@pytest.mark.asyncio
async def test_get_automation_mode_falls_back_on_invalid_stored_value(
    fresh_db: DatabaseManager,
) -> None:
    """Corrupted stored values do not blow up — the default is returned.

    Purpose:
        Defend against manual edits or schema drift that leak an unsupported
        mode into the table. The worker must keep running with a safe default.
    """

    await fresh_db.set_system_setting(TAILOR_MODE_KEY, "bogus")

    result = await fresh_db.get_automation_mode(TAILOR_MODE_KEY, default="opt_in")

    assert result == "opt_in"


@pytest.mark.parametrize("mode", AUTOMATION_MODES)
@pytest.mark.asyncio
async def test_set_automation_mode_accepts_every_valid_mode(
    fresh_db: DatabaseManager,
    mode: str,
) -> None:
    """Every entry in `AUTOMATION_MODES` is a valid write input."""

    await fresh_db.set_automation_mode(TAILOR_MODE_KEY, mode)

    result = await fresh_db.get_automation_mode(TAILOR_MODE_KEY)

    assert result == mode


@pytest.mark.asyncio
async def test_set_automation_mode_normalizes_case_and_whitespace(
    fresh_db: DatabaseManager,
) -> None:
    """Whitespace and casing variants are accepted and stored normalized."""

    await fresh_db.set_automation_mode(TAILOR_MODE_KEY, "  Both  ")

    result = await fresh_db.get_automation_mode(TAILOR_MODE_KEY)

    assert result == "both"


@pytest.mark.asyncio
async def test_set_automation_mode_rejects_invalid_mode(
    fresh_db: DatabaseManager,
) -> None:
    """Invalid modes raise `ValueError` and do not write anything."""

    with pytest.raises(ValueError, match="Invalid automation mode"):
        await fresh_db.set_automation_mode(TAILOR_MODE_KEY, "bogus")

    stored = await fresh_db.get_system_setting(TAILOR_MODE_KEY)
    assert stored is None


@pytest.mark.asyncio
async def test_seed_automation_defaults_uses_default_when_env_unset(
    fresh_db: DatabaseManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First boot with no env var seeds the safe default for the tailor key."""

    monkeypatch.delenv("TAILOR_MODE", raising=False)

    await fresh_db.seed_automation_defaults_from_env()

    tailor_mode = await fresh_db.get_system_setting(TAILOR_MODE_KEY)
    assert tailor_mode == DEFAULT_AUTOMATION_MODE


@pytest.mark.asyncio
async def test_seed_automation_defaults_picks_up_valid_env_value(
    fresh_db: DatabaseManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid env value overrides the bare default when the key is missing."""

    monkeypatch.setenv("TAILOR_MODE", "autonomous")

    await fresh_db.seed_automation_defaults_from_env()

    assert await fresh_db.get_system_setting(TAILOR_MODE_KEY) == "autonomous"


@pytest.mark.asyncio
async def test_seed_automation_defaults_ignores_invalid_env(
    fresh_db: DatabaseManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo in the env var is rejected; default is seeded instead."""

    monkeypatch.setenv("TAILOR_MODE", "definitely_not_a_mode")

    await fresh_db.seed_automation_defaults_from_env()

    assert await fresh_db.get_system_setting(TAILOR_MODE_KEY) == DEFAULT_AUTOMATION_MODE


@pytest.mark.asyncio
async def test_seed_automation_defaults_does_not_overwrite_existing_rows(
    fresh_db: DatabaseManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Once the user picks a mode via Settings UI, env seeds never override it.

    Purpose:
        Protect user-edited values from being clobbered on every restart when
        the env var still has a deployment-default value.
    """

    await fresh_db.set_automation_mode(TAILOR_MODE_KEY, "both")
    monkeypatch.setenv("TAILOR_MODE", "autonomous")

    await fresh_db.seed_automation_defaults_from_env()

    assert await fresh_db.get_system_setting(TAILOR_MODE_KEY) == "both"


@pytest.mark.asyncio
async def test_seed_automation_defaults_is_idempotent(
    fresh_db: DatabaseManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Running seeding repeatedly produces a stable end state."""

    monkeypatch.setenv("TAILOR_MODE", "autonomous")

    await fresh_db.seed_automation_defaults_from_env()
    await fresh_db.seed_automation_defaults_from_env()
    await fresh_db.seed_automation_defaults_from_env()

    assert await fresh_db.get_system_setting(TAILOR_MODE_KEY) == "autonomous"
