"""Cover atomic queue-claim semantics and retry fairness ordering."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


async def _insert_job(
    db: DatabaseManager,
    *,
    source_url: str,
    title: str,
) -> JobPosting:
    """Insert one deterministic NEW job row for queueing tests.

    Purpose:
        Reduce test boilerplate while creating predictable rows for queue claim
        and ordering assertions.
    Args:
        db: Connected database manager used for inserts.
        source_url: Stable URL used as part of dedup hash generation.
        title: Job title value for readability in test assertions.
    Output:
        Returns the inserted `JobPosting` instance.
    """

    job = JobPosting(
        source="test",
        source_url=source_url,
        company="QueueCo",
        title=title,
        description="Queue semantics test row",
    )
    await db.insert_job(job.to_db_dict())
    return job


@pytest.mark.asyncio
async def test_concurrent_workers_do_not_claim_same_row() -> None:
    """Verify concurrent workers cannot claim the same pending row.

    Purpose:
        Enforce atomic-claim behavior so parallel workers do not duplicate work.
    Args:
        None.
    Output:
        Returns `None`; test passes when only one worker receives the row.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as seed_db:
            await seed_db.create_tables()
            await seed_db.migrate_agent_schema()
            await _insert_job(
                seed_db,
                source_url="https://example.com/jobs/one",
                title="Row One",
            )

        async with DatabaseManager(str(db_path)) as worker_one_db:
            await worker_one_db.create_tables()
            await worker_one_db.migrate_agent_schema()

            async with DatabaseManager(str(db_path)) as worker_two_db:
                await worker_two_db.create_tables()
                await worker_two_db.migrate_agent_schema()

                first_claim, second_claim = await asyncio.gather(
                    worker_one_db.get_jobs_pending_agent_processing(limit=1),
                    worker_two_db.get_jobs_pending_agent_processing(limit=1),
                )

    total_claimed = len(first_claim) + len(second_claim)
    assert total_claimed == 1


@pytest.mark.asyncio
async def test_claimed_rows_are_not_returned_twice_without_release() -> None:
    """Verify a claimed row is hidden from immediate subsequent claim calls.

    Purpose:
        Ensure same-worker repeated polling does not re-claim active rows.
    Args:
        None.
    Output:
        Returns `None`; test passes when second claim call returns no rows.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()
            await _insert_job(
                db,
                source_url="https://example.com/jobs/one",
                title="Row One",
            )

            first_claim = await db.get_jobs_pending_agent_processing(limit=1)
            second_claim = await db.get_jobs_pending_agent_processing(limit=1)

    assert len(first_claim) == 1
    assert second_claim == []


@pytest.mark.asyncio
async def test_retry_due_ordering_prefers_oldest_due_retry() -> None:
    """Verify queue ordering is FIFO by retry due time and fetched time.

    Purpose:
        Prevent older due retries from starving behind newer due/new rows.
    Args:
        None.
    Output:
        Returns `None`; test passes when oldest due retry is claimed first.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()

            oldest_retry = await _insert_job(
                db,
                source_url="https://example.com/jobs/oldest-retry",
                title="Oldest Retry",
            )
            newer_retry = await _insert_job(
                db,
                source_url="https://example.com/jobs/newer-retry",
                title="Newer Retry",
            )
            newest_new = await _insert_job(
                db,
                source_url="https://example.com/jobs/newest-new",
                title="Newest New",
            )

            assert db.conn is not None
            await db.conn.execute(
                """
                UPDATE job_postings
                SET agent_next_retry_at = datetime('now', '-2 hours'),
                    fetched_at = datetime('now', '-3 days')
                WHERE job_hash = ?
                """,
                (oldest_retry.job_hash,),
            )
            await db.conn.execute(
                """
                UPDATE job_postings
                SET agent_next_retry_at = datetime('now', '-1 hour'),
                    fetched_at = datetime('now', '-2 days')
                WHERE job_hash = ?
                """,
                (newer_retry.job_hash,),
            )
            await db.conn.execute(
                """
                UPDATE job_postings
                SET fetched_at = datetime('now')
                WHERE job_hash = ?
                """,
                (newest_new.job_hash,),
            )
            await db.conn.commit()

            claimed_rows = await db.get_jobs_pending_agent_processing(limit=1)

    assert len(claimed_rows) == 1
    assert claimed_rows[0]["job_hash"] == oldest_retry.job_hash


@pytest.mark.asyncio
async def test_fifo_ordering_for_new_rows_uses_oldest_fetched_at() -> None:
    """Verify NEW rows without retry timestamps are claimed oldest-first.

    Purpose:
        Keep deterministic backlog draining order when no retry schedule exists.
    Args:
        None.
    Output:
        Returns `None`; test passes when claims follow fetched-at FIFO order.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()

            oldest = await _insert_job(
                db,
                source_url="https://example.com/jobs/oldest",
                title="Oldest",
            )
            middle = await _insert_job(
                db,
                source_url="https://example.com/jobs/middle",
                title="Middle",
            )
            newest = await _insert_job(
                db,
                source_url="https://example.com/jobs/newest",
                title="Newest",
            )

            assert db.conn is not None
            await db.conn.execute(
                "UPDATE job_postings SET fetched_at = datetime('now', '-3 days') WHERE job_hash = ?",
                (oldest.job_hash,),
            )
            await db.conn.execute(
                "UPDATE job_postings SET fetched_at = datetime('now', '-2 days') WHERE job_hash = ?",
                (middle.job_hash,),
            )
            await db.conn.execute(
                "UPDATE job_postings SET fetched_at = datetime('now', '-1 day') WHERE job_hash = ?",
                (newest.job_hash,),
            )
            await db.conn.commit()

            first_batch = await db.get_jobs_pending_agent_processing(limit=2)

    assert [row["job_hash"] for row in first_batch] == [
        oldest.job_hash,
        middle.job_hash,
    ]


@pytest.mark.asyncio
async def test_retry_rows_reenter_queue_after_retry_state_update() -> None:
    """Verify retry updates release claim state and requeue rows correctly.

    Purpose:
        Ensure failed attempts release row claims so later worker cycles can
        claim the same row once retry window is due.
    Args:
        None.
    Output:
        Returns `None`; test passes when row can be reclaimed after retry update.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()
            job = await _insert_job(
                db,
                source_url="https://example.com/jobs/retry",
                title="Retry Row",
            )

            first_claim = await db.get_jobs_pending_agent_processing(limit=1)
            assert len(first_claim) == 1

            await db.record_agent_retry(
                job_hash=job.job_hash,
                error="transient",
                retry_count=1,
                next_retry_at="2000-01-01 00:00:00",
            )

            second_claim = await db.get_jobs_pending_agent_processing(limit=1)

    assert len(second_claim) == 1
    assert second_claim[0]["job_hash"] == job.job_hash
