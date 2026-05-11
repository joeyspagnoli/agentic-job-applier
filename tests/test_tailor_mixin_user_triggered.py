"""Tests for the new user-triggered tailor_runs helpers.

Purpose:
    Lock in the contract of `insert_user_triggered_tailor_run`,
    `soft_delete_tailor_run`, `mark_tailor_running`, `get_tailor_run`,
    and `get_latest_tailor_run_for_job`. The `claim_next_tailor_job`
    legacy path is already covered by `test_tailor_concurrent_claims.py`;
    this module focuses on the opt-in API surface.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio

from src.database.db_manager import DatabaseManager


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Provide a fully migrated DB with tailor + jobs schemas ready.

    Purpose:
        Mirror the production migration sequence so every assertion runs
        against the same schema shape the API and worker will see.
    """

    manager = DatabaseManager(str(tmp_path / "tailor.db"))
    await manager.connect()
    await manager.create_tables()
    yield manager
    await manager.close()


async def _new_inserter(db_path: str, job_hash: str) -> dict[str, object] | None:
    """Open an independent DB connection, attempt one user-triggered insert.

    Purpose:
        Simulate two concurrent FastAPI workers competing on the same job.
    """

    manager = DatabaseManager(db_path)
    await manager.connect()
    try:
        return await manager.insert_user_triggered_tailor_run(job_hash=job_hash)
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_insert_user_triggered_returns_id_and_claim_token(
    db: DatabaseManager,
) -> None:
    """First-time insert returns a positive id and a hex claim token."""

    result = await db.insert_user_triggered_tailor_run(job_hash="a" * 40)

    assert result is not None
    assert isinstance(result["id"], int) and result["id"] > 0
    assert isinstance(result["claim_token"], str)
    assert len(result["claim_token"]) == 64


@pytest.mark.asyncio
async def test_insert_user_triggered_blocks_when_pending_row_exists(
    db: DatabaseManager,
) -> None:
    """A second call for the same job returns `None` while one is PENDING."""

    first = await db.insert_user_triggered_tailor_run(job_hash="b" * 40)
    assert first is not None

    second = await db.insert_user_triggered_tailor_run(job_hash="b" * 40)

    assert second is None


@pytest.mark.asyncio
async def test_insert_user_triggered_blocks_when_running_row_exists(
    db: DatabaseManager,
) -> None:
    """RUNNING rows occupy the slot the same way PENDING rows do."""

    first = await db.insert_user_triggered_tailor_run(job_hash="c" * 40)
    assert first is not None
    await db.mark_tailor_running(run_id=cast(int, first["id"]))

    second = await db.insert_user_triggered_tailor_run(job_hash="c" * 40)

    assert second is None


@pytest.mark.asyncio
async def test_insert_user_triggered_blocks_when_success_row_exists(
    db: DatabaseManager,
) -> None:
    """A SUCCESS row also occupies the slot — user must delete first."""

    first = await db.insert_user_triggered_tailor_run(job_hash="d" * 40)
    assert first is not None
    await db.record_tailor_success(
        run_id=cast(int, first["id"]),
        artifact_yaml_path="/tmp/a.yaml",
        artifact_tex_path="/tmp/a.tex",
        artifact_pdf_path="/tmp/a.pdf",
        page_count=1,
    )

    second = await db.insert_user_triggered_tailor_run(job_hash="d" * 40)

    assert second is None


@pytest.mark.asyncio
async def test_insert_user_triggered_allows_after_failure(
    db: DatabaseManager,
) -> None:
    """A FAILED row does not occupy the slot — retry is allowed."""

    first = await db.insert_user_triggered_tailor_run(job_hash="e" * 40)
    assert first is not None
    await db.record_tailor_failure(
        run_id=cast(int, first["id"]),
        error="something_failed",
        next_retry_at=None,
    )

    second = await db.insert_user_triggered_tailor_run(job_hash="e" * 40)

    assert second is not None
    assert second["id"] != first["id"]


@pytest.mark.asyncio
async def test_insert_user_triggered_allows_after_soft_delete(
    db: DatabaseManager,
) -> None:
    """Soft-deleted rows do not block a re-insert."""

    first = await db.insert_user_triggered_tailor_run(job_hash="f" * 40)
    assert first is not None
    assert await db.soft_delete_tailor_run(cast(int, first["id"])) is True

    second = await db.insert_user_triggered_tailor_run(job_hash="f" * 40)

    assert second is not None
    assert second["id"] != first["id"]


@pytest.mark.asyncio
async def test_insert_user_triggered_serializes_concurrent_callers(
    db: DatabaseManager,
) -> None:
    """Five concurrent inserters race; exactly one wins.

    Purpose:
        Validate the `BEGIN IMMEDIATE` race semantics flagged as a risk in
        the testing handoff. Under contention, only one row may land.
    """

    job_hash = "0" * 40
    db_path = db.db_path

    results = await asyncio.gather(
        *(_new_inserter(db_path, job_hash) for _ in range(5))
    )

    winners = [r for r in results if r is not None]
    losers = [r for r in results if r is None]
    assert len(winners) == 1
    assert len(losers) == 4


@pytest.mark.asyncio
async def test_soft_delete_returns_false_for_missing_row(
    db: DatabaseManager,
) -> None:
    """Soft-deleting a nonexistent id reports failure without raising."""

    result = await db.soft_delete_tailor_run(99_999)

    assert result is False


@pytest.mark.asyncio
async def test_soft_delete_returns_false_when_already_deleted(
    db: DatabaseManager,
) -> None:
    """Re-deleting the same row reports `False` (idempotent at API layer)."""

    inserted = await db.insert_user_triggered_tailor_run(job_hash="9" * 40)
    assert inserted is not None
    first = await db.soft_delete_tailor_run(cast(int, inserted["id"]))
    second = await db.soft_delete_tailor_run(cast(int, inserted["id"]))

    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_soft_delete_sets_deleted_at_visible_on_get(
    db: DatabaseManager,
) -> None:
    """After soft-delete, `get_tailor_run` exposes the `deleted_at` stamp."""

    inserted = await db.insert_user_triggered_tailor_run(job_hash="8" * 40)
    assert inserted is not None
    await db.soft_delete_tailor_run(cast(int, inserted["id"]))

    row = await db.get_tailor_run(cast(int, inserted["id"]))

    assert row is not None
    assert row["deleted_at"] is not None


@pytest.mark.asyncio
async def test_mark_tailor_running_transitions_pending_row(
    db: DatabaseManager,
) -> None:
    """PENDING → RUNNING transition is observed on a subsequent fetch."""

    inserted = await db.insert_user_triggered_tailor_run(job_hash="7" * 40)
    assert inserted is not None

    await db.mark_tailor_running(run_id=cast(int, inserted["id"]))

    row = await db.get_tailor_run(cast(int, inserted["id"]))
    assert row is not None
    assert row["status"] == "RUNNING"


@pytest.mark.asyncio
async def test_mark_tailor_running_is_noop_for_terminal_status(
    db: DatabaseManager,
) -> None:
    """Calling `mark_tailor_running` on SUCCESS/FAILED is a silent no-op."""

    inserted = await db.insert_user_triggered_tailor_run(job_hash="6" * 40)
    assert inserted is not None
    await db.record_tailor_success(
        run_id=cast(int, inserted["id"]),
        artifact_yaml_path="/tmp/x.yaml",
        artifact_tex_path="/tmp/x.tex",
        artifact_pdf_path="/tmp/x.pdf",
        page_count=1,
    )

    await db.mark_tailor_running(run_id=cast(int, inserted["id"]))

    row = await db.get_tailor_run(cast(int, inserted["id"]))
    assert row is not None
    assert row["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_get_tailor_run_returns_none_for_missing_id(
    db: DatabaseManager,
) -> None:
    """Unknown ids resolve to `None` instead of raising."""

    row = await db.get_tailor_run(123_456)

    assert row is None


@pytest.mark.asyncio
async def test_get_latest_tailor_run_returns_most_recent_non_deleted(
    db: DatabaseManager,
) -> None:
    """The most recent non-deleted run is returned even when older rows exist."""

    job_hash = "5" * 40
    first = await db.insert_user_triggered_tailor_run(job_hash=job_hash)
    assert first is not None
    await db.record_tailor_failure(
        run_id=cast(int, first["id"]), error="failed", next_retry_at=None
    )

    second = await db.insert_user_triggered_tailor_run(job_hash=job_hash)
    assert second is not None

    latest = await db.get_latest_tailor_run_for_job(job_hash)

    assert latest is not None
    assert latest["id"] == second["id"]


@pytest.mark.asyncio
async def test_get_latest_tailor_run_excludes_deleted_rows(
    db: DatabaseManager,
) -> None:
    """Soft-deleted rows do not show up as the latest run."""

    job_hash = "4" * 40
    first = await db.insert_user_triggered_tailor_run(job_hash=job_hash)
    assert first is not None
    await db.soft_delete_tailor_run(cast(int, first["id"]))

    latest = await db.get_latest_tailor_run_for_job(job_hash)

    assert latest is None


@pytest.mark.asyncio
async def test_mark_stale_tailor_runs_reaps_running_status(
    db: DatabaseManager,
) -> None:
    """The stale sweep includes RUNNING rows, not just PENDING.

    Purpose:
        Workers crash mid-run; the row stays RUNNING until the lease
        expires. The sweep must convert it to FAILED so re-claim succeeds.
    """

    inserted = await db.insert_user_triggered_tailor_run(job_hash="3" * 40)
    assert inserted is not None
    await db.mark_tailor_running(run_id=cast(int, inserted["id"]))

    conn = db._require_conn()
    await conn.execute(
        "UPDATE tailor_runs SET started_at = datetime('now', '-99999 seconds') "
        "WHERE id = ?",
        (cast(int, inserted["id"]),),
    )
    await conn.commit()

    reaped = await db.mark_stale_tailor_runs_failed(lease_seconds=10)

    assert reaped == 1
    row = await db.get_tailor_run(cast(int, inserted["id"]))
    assert row is not None
    assert row["status"] == "FAILED"
