"""Check apply schema parity between base DDL and runtime migration DDL.

Purpose:
    Prevent drift between `src/database/schema.sql` and
    `DatabaseManager.migrate_apply_schema()` for the `apply_runs` table.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.database.db_manager import DatabaseManager


async def _get_apply_runs_columns(db_path: Path, *, use_base_schema: bool) -> list[str]:
    """Return ordered apply_runs column names for one schema bootstrap path.

    Purpose:
        Reuse deterministic introspection logic for base-schema and migration-
        only database initialization modes.
    Args:
        db_path: SQLite file path for this test database.
        use_base_schema: When True, bootstrap with `create_tables()`; otherwise
            bootstrap via `migrate_apply_schema()` only.
    Output:
        Returns ordered `apply_runs` column names from PRAGMA table info.
    """

    async with DatabaseManager(str(db_path)) as db:
        if use_base_schema:
            await db.create_tables()
        else:
            await db.migrate_apply_schema()

        assert db.conn is not None
        cursor = await db.conn.execute("PRAGMA table_info(apply_runs)")
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

        base_columns = await _get_apply_runs_columns(
            base_db_path,
            use_base_schema=True,
        )
        migration_columns = await _get_apply_runs_columns(
            migration_db_path,
            use_base_schema=False,
        )

    assert base_columns == migration_columns
