"""Basic integration tests for the job discovery system."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting
from src.utils.deduplicator import Deduplicator


@pytest.mark.asyncio
async def test_database_lifecycle():
    """Test database creation, insert, and query."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        async with DatabaseManager(str(db_path)) as db:
            # Create tables
            await db.create_tables()

            # Create a test job
            job = JobPosting(
                source="test_source",
                source_url="https://example.com/job/123",
                company="Test Company",
                title="Software Engineer",
                description="Test job description",
            )

            # Insert job
            inserted = await db.insert_job(job.to_db_dict())
            assert inserted is True

            # Try to insert duplicate (should fail)
            duplicate = await db.insert_job(job.to_db_dict())
            assert duplicate is False

            # Query job by hash
            found = await db.get_job_by_hash(job.job_hash)
            assert found is not None
            assert found["title"] == "Software Engineer"

            # Check count
            count = await db.get_job_count()
            assert count == 1


@pytest.mark.asyncio
async def test_deduplicator():
    """Test deduplicator filtering."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            dedup = Deduplicator(db)

            # Create test jobs
            job1 = JobPosting(
                source="test",
                source_url="https://example.com/1",
                company="Company A",
                title="Engineer",
                description="Job 1",
            )

            job2 = JobPosting(
                source="test",
                source_url="https://example.com/2",
                company="Company B",
                title="Engineer",
                description="Job 2",
            )

            # Insert first job
            await db.insert_job(job1.to_db_dict())

            # Filter jobs (job1 should be duplicate, job2 should be new)
            new_jobs = await dedup.filter_new_jobs([job1, job2])

            assert len(new_jobs) == 1
            assert new_jobs[0].source_url == "https://example.com/2"


@pytest.mark.asyncio
async def test_crawl_tracking():
    """Test crawl history tracking."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()

            # Start crawl
            crawl_id = await db.start_crawl("test_source", "test_company")
            assert crawl_id > 0

            # Complete crawl
            await db.complete_crawl(crawl_id, jobs_found=10, jobs_new=5)

            # Verify (manual SQL check)
            cursor = await db.conn.execute(
                "SELECT status, jobs_found, jobs_new FROM crawl_history WHERE id = ?",
                (crawl_id,),
            )
            row = await cursor.fetchone()
            assert row[0] == "SUCCESS"
            assert row[1] == 10
            assert row[2] == 5


def test_job_posting_hash():
    """Test job hash generation."""
    job1 = JobPosting(
        source="test",
        source_url="https://example.com/1",
        company="Test Co",
        title="Engineer",
        description="Test description",
    )

    job2 = JobPosting(
        source="test",
        source_url="https://example.com/2",  # Different URL
        company="Test Co",
        title="Engineer",
        description="Test description",
    )

    # Same company/title/description = same hash (deduplication)
    assert job1.job_hash == job2.job_hash


def test_job_posting_normalization():
    """Test field normalization."""
    job = JobPosting(
        source="test",
        source_url="https://example.com/1",
        company="Test Co",
        title="Engineer",
        location="Remote - San Francisco",
        job_type="full-time",
        description="Test",
    )

    # Remote detection
    assert job.is_remote is True

    # Job type normalization
    assert job.job_type == "Full-time"
