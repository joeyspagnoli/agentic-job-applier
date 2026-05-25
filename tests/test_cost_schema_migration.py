"""Tests for ``migrate_cost_schema`` — idempotence + backfill defaults.

The migration owns the issue #59 column additions on ``cost_events``
(provider / model / token counts / phase / cost_source). Existing rows
should backfill to the canonical ``'unknown'`` sentinel.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from src.database.db_manager import DatabaseManager


_PRE_59_COST_EVENTS_DDL = """
CREATE TABLE cost_events (
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
"""


async def _column_names(conn: aiosqlite.Connection, table: str) -> set[str]:
    """Return the column-name set for ``table`` via PRAGMA table_info."""

    cursor = await conn.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    return {str(r["name"]) for r in rows}


@pytest.mark.asyncio
async def test_migrate_adds_new_cost_columns_to_pre_59_db(tmp_path: Path) -> None:
    """Pre-#59 ``cost_events`` schemas pick up every new column."""

    db_path = tmp_path / "pre59_cost.db"

    async with aiosqlite.connect(str(db_path)) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_PRE_59_COST_EVENTS_DDL)
        await conn.execute(
            "INSERT INTO cost_events (stage, cost_usd) VALUES ('TAILOR', 0.05)"
        )
        await conn.commit()

        cols_before = await _column_names(conn, "cost_events")
        assert "provider" not in cols_before
        assert "model" not in cols_before
        assert "cost_source" not in cols_before

    async with DatabaseManager(str(db_path)) as db:
        await db.migrate_cost_schema()

        conn = db._require_conn()
        cols_after = await _column_names(conn, "cost_events")

        row_cursor = await conn.execute(
            "SELECT provider, model, prompt_tokens, completion_tokens, "
            "cached_input_tokens, reasoning_tokens, phase, cost_source "
            "FROM cost_events WHERE stage = 'TAILOR'"
        )
        row = await row_cursor.fetchone()

    new_cols = {
        "provider", "model", "prompt_tokens", "completion_tokens",
        "cached_input_tokens", "reasoning_tokens", "phase", "cost_source",
    }
    assert new_cols.issubset(cols_after)

    # Backfill defaults must stick on the pre-existing row.
    assert row is not None
    assert row["provider"] == "unknown"
    assert row["model"] == "unknown"
    assert row["cost_source"] == "unknown"
    assert row["prompt_tokens"] == 0
    assert row["completion_tokens"] == 0
    assert row["cached_input_tokens"] == 0
    assert row["reasoning_tokens"] == 0
    assert row["phase"] is None


@pytest.mark.asyncio
async def test_migrate_cost_schema_is_idempotent(tmp_path: Path) -> None:
    """Running ``migrate_cost_schema`` twice is a no-op the second time."""

    db_path = tmp_path / "idempotent_cost.db"

    async with DatabaseManager(str(db_path)) as db:
        await db.migrate_cost_schema()
        await db.migrate_cost_schema()  # second call must not raise

        conn = db._require_conn()
        cols = await _column_names(conn, "cost_events")

    assert "provider" in cols
    assert "cost_source" in cols


@pytest.mark.asyncio
async def test_migrate_cost_schema_preserves_existing_rows(tmp_path: Path) -> None:
    """The migration must not delete or overwrite rows that pre-date it."""

    db_path = tmp_path / "preserve_cost.db"

    async with aiosqlite.connect(str(db_path)) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_PRE_59_COST_EVENTS_DDL)
        await conn.execute(
            "INSERT INTO cost_events (stage, cost_usd, run_id) "
            "VALUES ('GATE', 0.01, 'run-A'), ('REVIEW', 0.02, 'run-B')"
        )
        await conn.commit()

    async with DatabaseManager(str(db_path)) as db:
        await db.migrate_cost_schema()
        conn = db._require_conn()
        cursor = await conn.execute("SELECT stage, run_id FROM cost_events ORDER BY id")
        rows = await cursor.fetchall()

    assert [(r["stage"], r["run_id"]) for r in rows] == [
        ("GATE", "run-A"),
        ("REVIEW", "run-B"),
    ]
