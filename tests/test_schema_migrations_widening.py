"""Tests for the CHECK-widening table-rebuild migrations.

Purpose:
    The handoff flagged two SQLite table-rebuild migrations as risk areas:

    * `tailor_runs` widens its `status` CHECK to allow `'RUNNING'`.
    * `review_runs` widens its `verdict` CHECK to allow `'NO_IMPROVEMENT'`
      and `'PAGE_FIT_FAILED'`.

    Both rebuilds use `SELECT * INTO __new`, which is column-order-sensitive.
    These tests pre-seed databases with the *old* table definitions, run the
    migration, and assert: (a) every existing row survives intact, and
    (b) the widened CHECK now accepts the new values.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from src.database.db_manager import DatabaseManager


async def _create_legacy_tailor_table(conn: aiosqlite.Connection) -> None:
    """Create the pre-RUNNING `tailor_runs` table shape from the legacy schema.

    Purpose:
        Reconstruct exactly the row shape an older deployment has on disk so
        the migration can be exercised end-to-end.
    """

    await conn.executescript(
        """
        CREATE TABLE tailor_runs (
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
        """
    )
    await conn.commit()


async def _create_legacy_review_table(conn: aiosqlite.Connection) -> None:
    """Create the pre-widening `review_runs` table shape.

    Purpose:
        Reproduce the older verdict CHECK so the rebuild can be tested.
    """

    await conn.executescript(
        """
        CREATE TABLE review_runs (
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
        """
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_tailor_status_check_widens_and_preserves_rows(
    tmp_path: Path,
) -> None:
    """Existing rows survive the rebuild; a new RUNNING insert now succeeds.

    Purpose:
        Catch the silent-misalignment risk flagged in the handoff: if the
        positional `SELECT *` ever falls out of sync with the destination
        column list, the persisted row values would shift columns. The
        explicit column round-trip below would surface the regression.
    """

    db_path = tmp_path / "legacy.db"
    async with aiosqlite.connect(str(db_path)) as conn:
        await _create_legacy_tailor_table(conn)
        await conn.execute(
            "INSERT INTO tailor_runs (job_hash, status, claim_token, error) "
            "VALUES (?, 'SUCCESS', 'tok-existing', NULL)",
            ("a" * 40,),
        )
        await conn.commit()

    async with DatabaseManager(str(db_path)) as db:
        await db.migrate_tailor_schema()

        conn = db._require_conn()
        cursor = await conn.execute(
            "SELECT job_hash, status, claim_token FROM tailor_runs"
        )
        rows = list(await cursor.fetchall())
        assert len(rows) == 1
        assert rows[0]["job_hash"] == "a" * 40
        assert rows[0]["status"] == "SUCCESS"
        assert rows[0]["claim_token"] == "tok-existing"

        await conn.execute(
            "INSERT INTO tailor_runs (job_hash, status, claim_token) "
            "VALUES (?, 'RUNNING', 'tok-new')",
            ("b" * 40,),
        )
        await conn.commit()

        running_cursor = await conn.execute(
            "SELECT status FROM tailor_runs WHERE job_hash = ?", ("b" * 40,)
        )
        running_row = await running_cursor.fetchone()
        assert running_row is not None
        assert running_row["status"] == "RUNNING"


@pytest.mark.asyncio
async def test_tailor_migration_is_idempotent(tmp_path: Path) -> None:
    """Running the migration twice does not destroy or duplicate rows."""

    db_path = tmp_path / "legacy.db"

    async with DatabaseManager(str(db_path)) as db:
        await db.migrate_tailor_schema()
        conn = db._require_conn()
        await conn.execute(
            "INSERT INTO tailor_runs (job_hash, status) VALUES (?, 'RUNNING')",
            ("c" * 40,),
        )
        await conn.commit()

        await db.migrate_tailor_schema()

        cursor = await conn.execute("SELECT COUNT(*) AS c FROM tailor_runs")
        row = await cursor.fetchone()
        assert row is not None
        assert int(row["c"]) == 1


@pytest.mark.asyncio
async def test_review_verdict_check_widens_and_preserves_rows(
    tmp_path: Path,
) -> None:
    """Pre-existing review rows survive; NO_IMPROVEMENT now accepted."""

    db_path = tmp_path / "legacy.db"
    async with aiosqlite.connect(str(db_path)) as conn:
        await _create_legacy_review_table(conn)
        await conn.execute(
            "INSERT INTO review_runs (job_hash, tailor_run_id, status, verdict) "
            "VALUES (?, 1, 'SUCCESS', 'TAILORED')",
            ("a" * 40,),
        )
        await conn.commit()

    async with DatabaseManager(str(db_path)) as db:
        await db.migrate_review_schema()

        conn = db._require_conn()
        cursor = await conn.execute(
            "SELECT job_hash, verdict FROM review_runs"
        )
        rows = list(await cursor.fetchall())
        assert len(rows) == 1
        assert rows[0]["verdict"] == "TAILORED"

        await conn.execute(
            "INSERT INTO review_runs (job_hash, tailor_run_id, status, verdict) "
            "VALUES (?, 1, 'SUCCESS', 'NO_IMPROVEMENT')",
            ("d" * 40,),
        )
        await conn.execute(
            "INSERT INTO review_runs (job_hash, tailor_run_id, status, verdict) "
            "VALUES (?, 1, 'SUCCESS', 'PAGE_FIT_FAILED')",
            ("e" * 40,),
        )
        await conn.commit()

        check_cursor = await conn.execute(
            "SELECT verdict FROM review_runs WHERE job_hash IN (?, ?)",
            ("d" * 40, "e" * 40),
        )
        verdicts = {row["verdict"] for row in await check_cursor.fetchall()}
        assert verdicts == {"NO_IMPROVEMENT", "PAGE_FIT_FAILED"}


@pytest.mark.asyncio
async def test_review_migration_is_idempotent(tmp_path: Path) -> None:
    """Re-running the migration after it widened the CHECK is a no-op."""

    db_path = tmp_path / "legacy.db"

    async with DatabaseManager(str(db_path)) as db:
        await db.migrate_review_schema()
        conn = db._require_conn()
        await conn.execute(
            "INSERT INTO review_runs (job_hash, tailor_run_id, status, verdict) "
            "VALUES (?, 1, 'SUCCESS', 'PAGE_FIT_FAILED')",
            ("f" * 40,),
        )
        await conn.commit()

        await db.migrate_review_schema()

        cursor = await conn.execute("SELECT COUNT(*) AS c FROM review_runs")
        row = await cursor.fetchone()
        assert row is not None
        assert int(row["c"]) == 1
