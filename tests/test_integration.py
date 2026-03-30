"""Validate the core persistence and normalization behavior of the repo."""

import tempfile
from pathlib import Path

import pytest

from src.fetchers.jobspy_fetcher import JobSpyFetcher
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting
from src.utils.deduplicator import Deduplicator
from src.utils.paths import resolve_database_path


@pytest.mark.asyncio
async def test_database_lifecycle() -> None:
    """Verify schema creation, insert behavior, and hash lookup work together.

    Purpose:
        Confirm that a fresh database can be initialized, accept a new job,
        reject a duplicate hash, and return the stored row correctly.
    Args:
        None.
    Output:
        Returns `None`; the test passes when the database lifecycle behaves as
        expected and fails through assertions otherwise.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()

            # The test job uses the minimum fields required to exercise inserts,
            # deduplication, and retrieval from the fresh schema.
            job = JobPosting(
                source="test_source",
                source_url="https://example.com/job/123",
                company="Test Company",
                title="Software Engineer",
                description="Test job description",
            )

            inserted = await db.insert_job(job.to_db_dict())
            assert inserted is True

            duplicate = await db.insert_job(job.to_db_dict())
            assert duplicate is False

            found = await db.get_job_by_hash(job.job_hash)
            assert found is not None
            assert found["title"] == "Software Engineer"

            count = await db.get_job_count()
            assert count == 1


@pytest.mark.asyncio
async def test_deduplicator() -> None:
    """Verify the deduplicator keeps only unseen jobs.

    Purpose:
        Confirm that duplicate detection compares stored hashes correctly and
        preserves only jobs that are genuinely new.
    Args:
        None.
    Output:
        Returns `None`; the test passes when only the unseen job survives the
        deduplication step.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            dedup = Deduplicator(db)

            # Two jobs are created with different content so only the one that
            # was not pre-inserted should remain after filtering.
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

            await db.insert_job(job1.to_db_dict())
            new_jobs = await dedup.filter_new_jobs([job1, job2])

            assert len(new_jobs) == 1
            assert new_jobs[0].source_url == "https://example.com/2"


@pytest.mark.asyncio
async def test_crawl_tracking() -> None:
    """Verify crawl-history rows record start and completion state correctly.

    Purpose:
        Confirm that the crawl tracking helpers create a history row, update it
        on completion, and persist the expected counts and status.
    Args:
        None.
    Output:
        Returns `None`; the test passes when the stored crawl row matches the
        expected success values.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()

            crawl_id = await db.start_crawl("test_source", "test_company")
            assert crawl_id > 0

            await db.complete_crawl(crawl_id, jobs_found=10, jobs_new=5)

            # The direct SQL check verifies the helper wrote the expected values
            # into the crawl_history table, not just that no exception was raised.
            assert db.conn is not None
            cursor = await db.conn.execute(
                "SELECT status, jobs_found, jobs_new FROM crawl_history WHERE id = ?",
                (crawl_id,),
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == "SUCCESS"
            assert row[1] == 10
            assert row[2] == 5


def test_job_posting_hash() -> None:
    """Verify normalized URL variants still produce the same deduplication hash.

    Purpose:
        Confirm that deduplication hash canonicalization ignores tracking URL
        differences while preserving stable posting identity.
    Args:
        None.
    Output:
        Returns `None`; the test passes when both postings hash to the same
        value and fails through assertions otherwise.
    """

    job1 = JobPosting(
        source="test",
        source_url="https://example.com/1/?utm_source=linkedin&gh_src=foo",
        company="Test Co",
        title="Engineer",
        description="Test description",
    )
    job2 = JobPosting(
        source="test",
        source_url="https://example.com/1",
        company="Test Co",
        title="Engineer",
        description="Test description",
    )

    # Tracking query params are stripped so the same posting URL normalizes to
    # one dedup identity.
    assert job1.job_hash == job2.job_hash


def test_job_posting_normalization() -> None:
    """Verify the model-level normalization hooks fill derived fields correctly.

    Purpose:
        Confirm that remote detection and job-type normalization happen inside
        the shared model before jobs are stored or processed further.
    Args:
        None.
    Output:
        Returns `None`; the test passes when the normalized fields match the
        expected derived values.
    """

    job = JobPosting(
        source="test",
        source_url="https://example.com/1",
        company="Test Co",
        title="Engineer",
        location="Remote - San Francisco",
        job_type="full-time",  # type: ignore[arg-type]  # normalize_job_type validator handles "full-time" → "Full-time"
        description="Test",
    )

    assert job.is_remote is True
    assert job.job_type == "Full-time"


def test_resolve_database_path_uses_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify database path resolution respects `DATABASE_PATH`.

    Purpose:
        Confirm that operational scripts can target a non-default database path
        through the documented environment variable.
    Args:
        monkeypatch: Pytest fixture used to isolate environment changes.
    Output:
        Returns `None`; the test passes when the resolved path matches the
        repo-root-relative environment override.
    """

    repo_root = Path(__file__).resolve().parent.parent
    monkeypatch.setenv("DATABASE_PATH", "data/custom/jobs.db")

    assert resolve_database_path() == repo_root / "data" / "custom" / "jobs.db"


def test_jobspy_salary_normalization_accepts_common_interval_variants() -> None:
    """Verify JobSpy salary intervals are normalized case-insensitively.

    Purpose:
        Prevent common source labels like `Hourly` or `Per Year` from falling
        back to an incorrect annualization multiplier.
    Args:
        None.
    Output:
        Returns `None`; the test passes when interval variants map to the
        expected annualized salary values.
    """

    fetcher = JobSpyFetcher(site_name="indeed", search_term="engineer")

    hourly_min, hourly_max = fetcher._normalize_salary(50, 60, "Hourly")
    yearly_min, yearly_max = fetcher._normalize_salary(150000, 180000, "Per Year")

    assert (hourly_min, hourly_max) == (10400000, 12480000)
    assert (yearly_min, yearly_max) == (15000000, 18000000)
