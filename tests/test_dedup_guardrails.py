"""Cover deduplication and insert-integrity guardrails."""

from __future__ import annotations

import tempfile
from pathlib import Path

import aiosqlite
import pytest

from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting
from src.utils.deduplicator import Deduplicator


def test_job_hash_distinguishes_similar_jobs_with_distinct_identity_fields() -> None:
    """Verify similar postings are not collapsed when identity fields differ.

    Purpose:
        Protect against false dedup where postings share generic intros but are
        actually distinct roles with different URLs, locations, or posted dates.
    Args:
        None.
    Output:
        Returns `None`; the test passes when hashes differ.
    """

    intro = "We build reliable software for customers. " * 40
    job_one = JobPosting(
        source="greenhouse_example",
        source_url="https://example.com/jobs/1001",
        company="Example",
        title="Software Engineer",
        location="New York, NY",
        posted_date="2026-03-10",
        description=intro + "Role focused on platform APIs.",
    )
    job_two = JobPosting(
        source="greenhouse_example",
        source_url="https://example.com/jobs/1002",
        company="Example",
        title="Software Engineer",
        location="Remote",
        posted_date="2026-03-12",
        description=intro + "Role focused on data pipelines.",
    )

    assert job_one.job_hash != job_two.job_hash


@pytest.mark.asyncio
async def test_insert_job_raises_non_duplicate_integrity_errors() -> None:
    """Verify non-duplicate integrity violations are not masked as duplicates.

    Purpose:
        Ensure callers can distinguish true duplicate-hash inserts from real
        data contract failures like required-column violations.
    Args:
        None.
    Output:
        Returns `None`; the test passes when an integrity error is raised.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()

            job = JobPosting(
                source="test_source",
                source_url="https://example.com/job/1",
                company="Example Co",
                title="Engineer",
                description="Role details",
            )
            invalid_job = job.to_db_dict()
            invalid_job["source"] = None

            with pytest.raises(aiosqlite.IntegrityError):
                await db.insert_job(invalid_job)


@pytest.mark.asyncio
async def test_deduplicator_filters_in_batch_duplicates_before_db_lookup() -> None:
    """Verify duplicate rows in one batch are removed before DB checks.

    Purpose:
        Confirm in-memory dedup prevents repeated hash lookups for duplicate
        rows inside the same fetch response.
    Args:
        None.
    Output:
        Returns `None`; the test passes when one DB batch call occurs and only
        one copy of the duplicate hash is returned.
    """

    class FakeDb:
        """Track `get_existing_job_hashes` calls for dedup tests."""

        def __init__(self) -> None:
            """Initialize call tracking state.

            Purpose:
                Capture how the deduplicator queries the database.
            Args:
                self: Fake database instance.
            Output:
                Returns `None`.
            """

            self.calls: list[list[str]] = []

        async def get_existing_job_hashes(self, job_hashes: list[str]) -> set[str]:
            """Record hash batches and return an empty existing set.

            Purpose:
                Emulate the DB batch lookup API while tracking invocation data.
            Args:
                self: Fake database instance.
                job_hashes: Candidate hashes from the deduplicator.
            Output:
                Returns an empty set to simulate no persisted duplicates.
            """

            self.calls.append(job_hashes)
            return set()

    fake_db = FakeDb()
    deduplicator = Deduplicator(fake_db)  # type: ignore[arg-type]

    job = JobPosting(
        source="test",
        source_url="https://example.com/job/1",
        company="Example",
        title="Engineer",
        description="Role details",
    )

    new_jobs = await deduplicator.filter_new_jobs([job, job, job])

    assert len(new_jobs) == 1
    assert len(fake_db.calls) == 1
    assert fake_db.calls[0] == [job.job_hash]


@pytest.mark.asyncio
async def test_deduplicator_uses_batch_lookup_for_persisted_hashes() -> None:
    """Verify persisted hashes are removed while unseen jobs survive.

    Purpose:
        Ensure batch hash lookup correctly filters persisted duplicates and
        keeps only unique unseen postings for insert.
    Args:
        None.
    Output:
        Returns `None`; the test passes when only the unseen job remains.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            existing_job = JobPosting(
                source="test",
                source_url="https://example.com/job/1",
                company="Example",
                title="Engineer",
                description="Existing posting",
            )
            new_job = JobPosting(
                source="test",
                source_url="https://example.com/job/2",
                company="Example",
                title="Senior Engineer",
                description="New posting",
            )

            await db.insert_job(existing_job.to_db_dict())
            filtered = await deduplicator.filter_new_jobs(
                [existing_job, new_job, existing_job]
            )

    assert [job.source_url for job in filtered] == ["https://example.com/job/2"]

