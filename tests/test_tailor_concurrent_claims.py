"""Tests for concurrent tailor job claim behavior.

Purpose:
    Validate that atomic claim logic prevents double-claiming under concurrent
    access, that multiple jobs can be claimed correctly, and that stale cleanup
    enables reclaim under concurrent access.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio

from src.database.db_manager import DatabaseManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Create a temporary database with base tables and tailor schema.

    Purpose:
        Provide a clean, isolated database for each test case with both
        the core schema and the tailor_runs table already migrated.
    Arg(s):
        tmp_path: Pytest temporary directory fixture.
    Output:
        Yields a connected DatabaseManager instance.
    """

    db_path = str(tmp_path / "test.db")
    manager = DatabaseManager(db_path)
    await manager.connect()
    await manager.create_tables()
    await manager.migrate_agent_schema()
    await manager.migrate_tailor_schema()
    yield manager
    await manager.close()


async def _insert_qualified_job(db: DatabaseManager, job_hash: str) -> None:
    """Insert a minimal QUALIFIED job row for testing.

    Purpose:
        Provide a reusable helper that creates a job row in the state
        the tailor worker expects to claim from.
    Arg(s):
        db: Connected database manager.
        job_hash: Unique hash for the test job.
    Output:
        Returns `None` after inserting and committing.
    """

    conn = db._require_conn()
    await conn.execute(
        """
        INSERT INTO job_postings (
            job_hash, source, source_url, company, title, status
        ) VALUES (?, 'test', 'https://example.com', 'TestCo', 'Engineer', 'QUALIFIED')
        """,
        (job_hash,),
    )
    await conn.commit()


async def _claim_with_own_conn(db_path: str, max_retries: int) -> dict[str, object] | None:
    """Open a separate DB connection, claim one job, then close.

    Purpose:
        Simulate a truly independent worker process by using a distinct
        DatabaseManager connection, which is the correct model for testing
        SQLite's BEGIN IMMEDIATE locking behavior across concurrent callers.
    Arg(s):
        db_path: Filesystem path to the shared SQLite database.
        max_retries: Maximum FAILED runs before a job is excluded.
    Output:
        Returns the claimed job dict, or None if no job is available.
    """

    mgr = DatabaseManager(db_path)
    await mgr.connect()
    try:
        return await mgr.claim_next_tailor_job(max_retries=max_retries)
    finally:
        await mgr.close()


# ---------------------------------------------------------------------------
# Test: concurrent claims do not double-claim a single job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_claim_no_double_claim(db: DatabaseManager) -> None:
    """Verify two concurrent connections claim a single job exactly once.

    Purpose:
        Validate the BEGIN IMMEDIATE transaction prevents double-claiming
        when two independent connections race to claim the same job.
    """

    await _insert_qualified_job(db, "a" * 32)

    db_path = db.db_path
    results = await asyncio.gather(
        _claim_with_own_conn(db_path, max_retries=2),
        _claim_with_own_conn(db_path, max_retries=2),
    )

    successful_claims = [r for r in results if r is not None]
    assert len(successful_claims) == 1
    assert successful_claims[0]["job_hash"] == "a" * 32


# ---------------------------------------------------------------------------
# Test: three tasks claim from two jobs — exactly two succeed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_three_tasks_claim_from_two_jobs(db: DatabaseManager) -> None:
    """Verify three concurrent connections claiming two jobs results in exactly two claims.

    Purpose:
        Validate that claim logic scales correctly when there are more workers
        than available jobs under concurrent access.
    """

    await _insert_qualified_job(db, "b" * 32)
    await _insert_qualified_job(db, "c" * 32)

    db_path = db.db_path
    results = await asyncio.gather(
        _claim_with_own_conn(db_path, max_retries=2),
        _claim_with_own_conn(db_path, max_retries=2),
        _claim_with_own_conn(db_path, max_retries=2),
    )

    successful_claims = [r for r in results if r is not None]
    none_claims = [r for r in results if r is None]

    assert len(successful_claims) == 2
    assert len(none_claims) == 1
    claimed_hashes = {r["job_hash"] for r in successful_claims}
    assert claimed_hashes == {"b" * 32, "c" * 32}


# ---------------------------------------------------------------------------
# Test: claim with invalid max_retries raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_with_invalid_max_retries_raises(db: DatabaseManager) -> None:
    """Verify max_retries=0 and max_retries=-1 both raise ValueError.

    Purpose:
        Validate M-007: the guard at the start of claim_next_tailor_job
        prevents nonsensical retry limits before any DB access.
    """

    with pytest.raises(ValueError, match="max_retries must be at least 1"):
        await db.claim_next_tailor_job(max_retries=0)

    with pytest.raises(ValueError, match="max_retries must be at least 1"):
        await db.claim_next_tailor_job(max_retries=-1)


# ---------------------------------------------------------------------------
# Test: stale cleanup enables reclaim under concurrent access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_cleanup_enables_reclaim_under_concurrent_access(
    db: DatabaseManager,
) -> None:
    """Verify that backdated stale PENDING row is reclaimable after cleanup.

    Purpose:
        Validate crash-recovery behavior: after stale PENDING runs are marked
        FAILED, a concurrent pair of independent connections results in exactly
        one successful claim.
    """

    job_hash = "e" * 32
    await _insert_qualified_job(db, job_hash)

    # Claim the job to create a PENDING run.
    claimed = await db.claim_next_tailor_job(max_retries=2)
    assert claimed is not None

    # Backdate the started_at so it is considered stale.
    conn = db._require_conn()
    await conn.execute(
        "UPDATE tailor_runs SET started_at = datetime('now', '-9999 seconds') WHERE id = ?",
        (claimed["_tailor_run_id"],),
    )
    await conn.commit()

    # Cleanup stale runs.
    stale_count = await db.mark_stale_tailor_runs_failed(lease_seconds=100)
    assert stale_count == 1

    # Two concurrent independent connections — exactly one should succeed.
    db_path = db.db_path
    results = await asyncio.gather(
        _claim_with_own_conn(db_path, max_retries=2),
        _claim_with_own_conn(db_path, max_retries=2),
    )

    successful_claims = [r for r in results if r is not None]
    assert len(successful_claims) == 1
    assert successful_claims[0]["job_hash"] == job_hash
