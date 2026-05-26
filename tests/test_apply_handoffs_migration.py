"""Tests for the apply_handoffs schema migration and record helper.

Purpose:
    Verify that `migrate_apply_schema` idempotently adds the finisher
    columns (`deferred_questions_json`, `finisher_diagnostics_json`) to an
    existing database that predates them, and that `record_apply_handoff`
    correctly persists both kwargs.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import aiosqlite
import pytest

# ---------------------------------------------------------------------------
# Import-cycle isolation
# ---------------------------------------------------------------------------
# `migrate_apply_schema` lazy-imports `src.agents.apply_worker.schemas` via
# `src.agents.__init__`, which pulls in `src.agents.resume_tailor.pipeline`,
# which imports `record_stage_cost_event` from `src.utils.cost_tracking` — a
# symbol added by a parallel branch not yet merged.  Pre-inject a stub for
# that single missing attribute so the import chain resolves cleanly.
# ---------------------------------------------------------------------------

import src.utils.cost_tracking as _cost_tracking_mod  # noqa: E402

if not hasattr(_cost_tracking_mod, "record_stage_cost_event"):
    _cost_tracking_mod.record_stage_cost_event = MagicMock()
if not hasattr(_cost_tracking_mod, "PIPELINE_STAGE_REVIEW"):
    _cost_tracking_mod.PIPELINE_STAGE_REVIEW = "review"
if not hasattr(_cost_tracking_mod, "PIPELINE_STAGE_TAILOR"):
    _cost_tracking_mod.PIPELINE_STAGE_TAILOR = "tailor"

from src.database.db_manager import DatabaseManager  # noqa: E402


_LEGACY_APPLY_HANDOFFS_DDL = """
CREATE TABLE apply_runs (
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
    CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED'))
);
CREATE TABLE apply_handoffs (
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
    CHECK (handoff_status IN ('PENDING_REVIEW', 'APPROVED', 'REJECTED'))
);
"""
"""DDL for the apply tables before the finisher diagnostic columns were added.

Purpose:
    Reproduce the on-disk schema that a deployed database would carry so the
    idempotent migration can be exercised against a pre-existing database.
"""


async def _column_names(conn: aiosqlite.Connection, table: str) -> set[str]:
    """Return the set of column names for *table* via PRAGMA table_info.

    Purpose:
        Provide a concise, deterministic way to assert schema shape in tests
        without writing raw SQL column-existence checks everywhere.
    Args:
        conn: Open aiosqlite connection to query.
        table: Table name to inspect.
    Output:
        Returns a set of column-name strings.
    """

    cursor = await conn.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    return {str(r["name"]) for r in rows}


@pytest.mark.asyncio
async def test_migrate_adds_finisher_columns_to_existing_db(
    tmp_path: Path,
) -> None:
    """PRAGMA shows both finisher columns after migrating a legacy database.

    Purpose:
        Catch the regression where `migrate_apply_schema` creates the table
        fresh (adding columns) but the PRAGMA-guarded ALTER path is never
        exercised for databases already carrying the old schema.
    """

    db_path = tmp_path / "legacy.db"

    # Seed the database with the old schema (no finisher columns).
    async with aiosqlite.connect(str(db_path)) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_LEGACY_APPLY_HANDOFFS_DDL)
        await conn.commit()

        cols_before = await _column_names(conn, "apply_handoffs")
        assert "deferred_questions_json" not in cols_before
        assert "finisher_diagnostics_json" not in cols_before

    # Run the migration via DatabaseManager.
    async with DatabaseManager(str(db_path)) as db:
        await db.migrate_apply_schema()

        conn = db._require_conn()
        cols_after = await _column_names(conn, "apply_handoffs")

    assert "deferred_questions_json" in cols_after
    assert "finisher_diagnostics_json" in cols_after


@pytest.mark.asyncio
async def test_migrate_is_idempotent(tmp_path: Path) -> None:
    """Running `migrate_apply_schema` twice raises no error.

    Purpose:
        Guard against the PRAGMA-guarded ALTER path throwing on second run
        (e.g. because the column already exists after the first migration).
    """

    db_path = tmp_path / "idempotent.db"

    async with DatabaseManager(str(db_path)) as db:
        await db.migrate_apply_schema()
        # Second call must not raise.
        await db.migrate_apply_schema()

        conn = db._require_conn()
        cols = await _column_names(conn, "apply_handoffs")

    assert "deferred_questions_json" in cols
    assert "finisher_diagnostics_json" in cols


@pytest.mark.asyncio
async def test_record_apply_handoff_persists_finisher_columns(
    tmp_path: Path,
) -> None:
    """Both new kwargs land in the row returned by a subsequent SELECT.

    Purpose:
        Verify that the INSERT column list, placeholder count, and
        ON CONFLICT UPDATE branch all include the two finisher columns so
        callers can round-trip the values without silent truncation.
    """

    db_path = tmp_path / "handoff.db"

    async with DatabaseManager(str(db_path)) as db:
        await db.migrate_apply_schema()
        # Seed minimal prerequisite rows (job_postings + review_runs are not
        # required by record_apply_handoff — it writes apply_handoffs directly).
        await db.record_apply_handoff(
            apply_run_id=1,
            job_hash="a" * 40,
            review_run_id=99,
            apply_outcome="NEEDS_REVIEW",
            resume_source="BASE",
            resume_pdf_path=None,
            confidence_score=0.75,
            confidence_report_json=None,
            unresolved_fields_json=None,
            screenshot_path=None,
            dom_snapshot_path=None,
            ats_platform="greenhouse",
            page_url="https://example.com/apply",
            deferred_questions_json='[{"q": "visa?"}]',
            finisher_diagnostics_json='{"simplify_no_op": false}',
        )

        conn = db._require_conn()
        cursor = await conn.execute(
            "SELECT deferred_questions_json, finisher_diagnostics_json "
            "FROM apply_handoffs WHERE apply_run_id = 1"
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row["deferred_questions_json"] == '[{"q": "visa?"}]'
    assert row["finisher_diagnostics_json"] == '{"simplify_no_op": false}'


@pytest.mark.asyncio
async def test_record_apply_handoff_upsert_updates_finisher_columns(
    tmp_path: Path,
) -> None:
    """ON CONFLICT path overwrites finisher columns on a second upsert.

    Purpose:
        Confirm that a worker re-running `record_apply_handoff` for the
        same `apply_run_id` does not silently preserve stale finisher data.
    """

    db_path = tmp_path / "upsert.db"

    async with DatabaseManager(str(db_path)) as db:
        await db.migrate_apply_schema()

        common_kwargs: dict[str, object] = dict(
            apply_run_id=7,
            job_hash="b" * 40,
            review_run_id=42,
            apply_outcome="NEEDS_REVIEW",
            resume_source=None,
            resume_pdf_path=None,
            confidence_score=None,
            confidence_report_json=None,
            unresolved_fields_json=None,
            screenshot_path=None,
            dom_snapshot_path=None,
            ats_platform=None,
            page_url=None,
        )

        await db.record_apply_handoff(
            **common_kwargs,  # type: ignore[arg-type]
            deferred_questions_json="[]",
            finisher_diagnostics_json='{"simplify_no_op": true}',
        )
        # Second call with updated values — exercises ON CONFLICT branch.
        await db.record_apply_handoff(
            **common_kwargs,  # type: ignore[arg-type]
            deferred_questions_json='[{"q": "salary?"}]',
            finisher_diagnostics_json='{"simplify_no_op": false}',
        )

        conn = db._require_conn()
        cursor = await conn.execute(
            "SELECT deferred_questions_json, finisher_diagnostics_json "
            "FROM apply_handoffs WHERE apply_run_id = 7"
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row["deferred_questions_json"] == '[{"q": "salary?"}]'
    assert row["finisher_diagnostics_json"] == '{"simplify_no_op": false}'
