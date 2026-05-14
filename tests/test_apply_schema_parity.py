"""Check apply schema parity between base DDL and runtime migration DDL.

Purpose:
    Prevent drift between `src/database/schema.sql` and
    `DatabaseManager.migrate_apply_schema()` for the `apply_runs` table,
    and between the Python enums (`ApplyOutcome`, `DBReviewVerdict`) and
    every CHECK constraint that references them.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

from src.agents.apply_worker.schemas import ApplyOutcome, apply_outcome_check_sql
from src.agents.resume_tailor.db_verdict import DBReviewVerdict, db_verdict_check_sql
from src.database.db_manager import DatabaseManager


_SCHEMA_SQL_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "database"
    / "schema.sql"
)


def _extract_value_set(sql_block: str, column: str) -> set[str]:
    """Pull the `<column> IN ('A', 'B', ...)` literal set out of a SQL block.

    Purpose:
        Compare schema.sql CHECK clauses against the Python-enum-derived
        SQL fragment without depending on whitespace or ordering.
    Args:
        sql_block: Raw `schema.sql` contents (or a substring).
        column: Column name whose `IN (...)` set should be returned.
    Output:
        Returns the set of single-quoted literal values, with the
        surrounding quotes stripped.
    """

    pattern = re.compile(
        rf"\b{re.escape(column)}\s+IN\s*\(([^)]+)\)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(sql_block)
    assert match is not None, f"No `{column} IN (...)` clause found in SQL block"
    raw_values = re.findall(r"'([^']+)'", match.group(1))
    return set(raw_values)


async def _get_table_columns(
    db_path: Path,
    *,
    use_base_schema: bool,
    table_name: str,
) -> list[str]:
    """Return ordered column names for one table bootstrap path.

    Purpose:
        Reuse deterministic introspection logic for base-schema and migration-
        only database initialization modes.
    Args:
        db_path: SQLite file path for this test database.
        use_base_schema: When True, bootstrap with `create_tables()`; otherwise
            bootstrap via `migrate_apply_schema()` only.
        table_name: SQL table name to inspect via PRAGMA table_info.
    Output:
        Returns ordered table column names from PRAGMA table info.
    """

    async with DatabaseManager(str(db_path)) as db:
        if use_base_schema:
            await db.create_tables()
        else:
            await db.migrate_apply_schema()

        assert db.conn is not None
        cursor = await db.conn.execute(f"PRAGMA table_info({table_name})")
        rows = await cursor.fetchall()

    return [str(row[1]) for row in rows]


@pytest.mark.asyncio
async def test_apply_runs_schema_matches_between_base_schema_and_migration() -> None:
    """Verify apply_runs columns match across both schema definition sources.

    Purpose:
        Regress L-002 by ensuring base schema bootstrap and runtime migration
        produce identical `apply_runs` column definitions.
    Args:
        None.
    Output:
        Returns `None`; test passes when column lists are exactly equal.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        base_db_path = Path(tmpdir) / "base_schema.db"
        migration_db_path = Path(tmpdir) / "migration_schema.db"

        base_columns = await _get_table_columns(
            base_db_path,
            use_base_schema=True,
            table_name="apply_runs",
        )
        migration_columns = await _get_table_columns(
            migration_db_path,
            use_base_schema=False,
            table_name="apply_runs",
        )

    assert base_columns == migration_columns


@pytest.mark.asyncio
async def test_apply_handoffs_schema_matches_between_base_schema_and_migration() -> None:
    """Verify apply_handoffs columns match across both schema definition sources.

    Purpose:
        Prevent migration drift for the apply handoff persistence table used by
        operator review workflows.
    Args:
        None.
    Output:
        Returns `None`; test passes when column lists are exactly equal.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        base_db_path = Path(tmpdir) / "base_schema.db"
        migration_db_path = Path(tmpdir) / "migration_schema.db"

        base_columns = await _get_table_columns(
            base_db_path,
            use_base_schema=True,
            table_name="apply_handoffs",
        )
        migration_columns = await _get_table_columns(
            migration_db_path,
            use_base_schema=False,
            table_name="apply_handoffs",
        )

    assert base_columns == migration_columns


def test_apply_outcome_check_sql_matches_enum_values() -> None:
    """`apply_outcome_check_sql()` produces an `IN` set matching `ApplyOutcome`."""

    expected_values = {item.value for item in ApplyOutcome}

    rendered = apply_outcome_check_sql("apply_outcome")

    assert _extract_value_set(rendered, "apply_outcome") == expected_values


def test_schema_sql_apply_outcome_check_matches_enum_values() -> None:
    """The literal `apply_outcome` CHECK in schema.sql tracks `ApplyOutcome`."""

    sql_text = _SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    expected_values = {item.value for item in ApplyOutcome}

    apply_handoffs_block = sql_text[sql_text.index("apply_handoffs") :]
    handoff_values = _extract_value_set(apply_handoffs_block, "apply_outcome")

    apply_runs_block = sql_text[
        sql_text.index("apply_runs") : sql_text.index("apply_handoffs")
    ]
    runs_values = _extract_value_set(apply_runs_block, "outcome")

    assert handoff_values == expected_values
    assert runs_values == expected_values


def test_db_verdict_check_sql_matches_enum_values() -> None:
    """`db_verdict_check_sql()` produces an `IN` set matching `DBReviewVerdict`."""

    expected_values = {item.value for item in DBReviewVerdict}

    rendered = db_verdict_check_sql("verdict")

    assert _extract_value_set(rendered, "verdict") == expected_values


def test_schema_sql_review_verdict_check_matches_enum_values() -> None:
    """The literal `verdict` CHECK in schema.sql tracks `DBReviewVerdict`."""

    sql_text = _SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    expected_values = {item.value for item in DBReviewVerdict}

    review_block = sql_text[
        sql_text.index("review_runs") : sql_text.index("apply_runs")
    ]
    review_values = _extract_value_set(review_block, "verdict")

    assert review_values == expected_values
