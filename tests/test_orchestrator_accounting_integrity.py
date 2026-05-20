"""Validate orchestrator failure isolation and crawl-accounting integrity."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

import main as discovery_main
import src.orchestrator.discovery as discovery_module
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting
from src.utils.deduplicator import Deduplicator


class _StaticFetcher:
    """Return deterministic postings for source-accounting tests."""

    def __init__(self, company_name: str, _identifier: str, **_kwargs: object) -> None:
        """Store constructor args for compatibility with real fetchers.

        Purpose:
            Keep fake fetcher signatures drop-in compatible with orchestrator
            source loops, including fetchers (e.g., WorkdayFetcher) that pass
            extra keyword arguments such as ``fetch_descriptions`` or
            ``search_text``.
        Args:
            self: Fake fetcher instance.
            company_name: Company label from orchestrator config.
            _identifier: Board URL or identifier from config.
            **_kwargs: Ignored extra keyword arguments forwarded by the
                production fetcher signatures.
        Output:
            Returns `None`.
        """

        self.company_name = company_name

    async def __aenter__(self) -> "_StaticFetcher":
        """Return self to satisfy async context-manager usage.

        Purpose:
            Match production fetcher context-manager protocol.
        Args:
            self: Fake fetcher instance.
        Output:
            Returns this fake fetcher instance.
        """

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Provide no-op async context cleanup for fake fetcher.

        Purpose:
            Keep deterministic tests aligned with production lifecycle calls.
        Args:
            self: Fake fetcher instance.
            exc_type: Exception type raised in context, if any.
            exc_val: Exception value raised in context, if any.
            exc_tb: Exception traceback raised in context, if any.
        Output:
            Returns `None`.
        """

        _ = (exc_type, exc_val, exc_tb)

    async def fetch_jobs(self) -> list[JobPosting]:
        """Return one deterministic posting for the configured company.

        Purpose:
            Keep accounting tests focused on orchestrator behavior.
        Args:
            self: Fake fetcher instance.
        Output:
            Returns one deterministic normalized posting.
        """

        return [
            JobPosting(
                source="fake",
                source_url=f"https://example.com/{self.company_name}",
                company=self.company_name,
                title=f"{self.company_name} Internship",
                description="Deterministic fetcher row",
            )
        ]


@pytest.mark.asyncio
async def test_greenhouse_start_crawl_failure_does_not_abort_other_companies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify one crawl-start failure does not stop later Greenhouse crawls.

    Purpose:
        Ensure per-company start-crawl exceptions are isolated so one DB hiccup
        cannot abort the entire source family.
    Args:
        monkeypatch: Pytest fixture used to patch fetcher and DB behavior.
    Output:
        Returns `None`; test passes when one company succeeds after one failure.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            original_start_crawl = db.start_crawl

            async def flaky_start_crawl(source: str, company: str | None = None) -> int:
                """Raise for one company to test failure isolation.

                Purpose:
                    Simulate transient DB failure while leaving other companies
                    processable in the same loop.
                Args:
                    source: Crawl source identifier.
                    company: Optional company name for the crawl.
                Output:
                    Returns inserted crawl ID for non-failing companies.
                """

                if company == "BadCo":
                    raise RuntimeError("start crawl failed")
                return await original_start_crawl(source, company)

            monkeypatch.setattr(discovery_main, "GreenhouseFetcher", _StaticFetcher)
            monkeypatch.setattr(db, "start_crawl", flaky_start_crawl)

            counters = await discovery_main.fetch_greenhouse_jobs(
                {
                    "BadCo": {"greenhouse_id": "bad"},
                    "GoodCo": {"greenhouse_id": "good"},
                },
                db,
                deduplicator,
            )

            assert db.conn is not None
            crawl_rows = await (
                await db.conn.execute(
                    "SELECT status FROM crawl_history ORDER BY id ASC"
                )
            ).fetchall()

    assert counters == (1, 1, 1, 1)
    assert [row[0] for row in crawl_rows] == ["SUCCESS"]


@pytest.mark.asyncio
async def test_workday_start_crawl_failure_does_not_abort_other_companies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify one crawl-start failure does not stop later Workday crawls.

    Purpose:
        Ensure Workday loop handles start-crawl failures per company.
    Args:
        monkeypatch: Pytest fixture used to patch fetcher and DB behavior.
    Output:
        Returns `None`; test passes when one company succeeds after one failure.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)
            original_start_crawl = db.start_crawl

            async def flaky_start_crawl(source: str, company: str | None = None) -> int:
                """Raise for one company to test failure isolation.

                Purpose:
                    Simulate a transient start-crawl DB failure.
                Args:
                    source: Crawl source identifier.
                    company: Optional company name for the crawl.
                Output:
                    Returns inserted crawl ID for non-failing companies.
                """

                if company == "BadCo":
                    raise RuntimeError("start crawl failed")
                return await original_start_crawl(source, company)

            monkeypatch.setattr(discovery_main, "WorkdayFetcher", _StaticFetcher)
            monkeypatch.setattr(db, "start_crawl", flaky_start_crawl)

            counters = await discovery_main.fetch_workday_jobs(
                {
                    "BadCo": {"workday_url": "https://bad.wd1.myworkdayjobs.com/Careers"},
                    "GoodCo": {"workday_url": "https://good.wd1.myworkdayjobs.com/Careers"},
                },
                db,
                deduplicator,
            )

    assert counters == (1, 1, 1, 1)


@pytest.mark.asyncio
async def test_greenhouse_partial_insert_failure_persists_real_crawl_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify failed crawl rows keep discovered/new counts from partial insert.

    Purpose:
        Prevent misleading `0/0` crawl rows when exceptions happen after some
        jobs were already fetched and inserted.
    Args:
        monkeypatch: Pytest fixture used to patch fetcher and insert behavior.
    Output:
        Returns `None`; test passes when failed crawl stores `jobs_found=2,new=1`.
    """

    class TwoJobFetcher(_StaticFetcher):
        """Return two jobs to exercise partial-insert failure accounting."""

        async def fetch_jobs(self) -> list[JobPosting]:
            """Return two deterministic rows for one crawl attempt.

            Purpose:
                Ensure one insert can succeed before a forced failure.
            Args:
                self: Fake fetcher instance.
            Output:
                Returns two normalized postings.
            """

            return [
                JobPosting(
                    source="fake",
                    source_url="https://example.com/job-1",
                    company=self.company_name,
                    title="First",
                    description="first",
                ),
                JobPosting(
                    source="fake",
                    source_url="https://example.com/job-2",
                    company=self.company_name,
                    title="Second",
                    description="second",
                ),
            ]

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)
            original_insert_job = db.insert_job
            call_counter = {"count": 0}

            async def fail_on_second_insert(job_data: dict[str, Any]) -> bool:
                """Raise during second insert attempt to force partial failure.

                Purpose:
                    Exercise crawl-accounting behavior when insert loop fails
                    after at least one successful write.
                Args:
                    job_data: Normalized insert payload.
                Output:
                    Returns insert result for first call, raises on second.
                """

                call_counter["count"] += 1
                if call_counter["count"] == 2:
                    raise RuntimeError("insert failed after first row")
                return await original_insert_job(job_data)

            monkeypatch.setattr(discovery_main, "GreenhouseFetcher", TwoJobFetcher)
            monkeypatch.setattr(db, "insert_job", fail_on_second_insert)

            counters = await discovery_main.fetch_greenhouse_jobs(
                {"Example": {"greenhouse_id": "example"}},
                db,
                deduplicator,
            )

            assert db.conn is not None
            crawl_row = await (
                await db.conn.execute(
                    """
                    SELECT status, jobs_found, jobs_new, error_message
                    FROM crawl_history
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
            ).fetchone()

    assert counters == (2, 1, 0, 1)
    assert crawl_row is not None
    assert tuple(crawl_row[:3]) == ("FAILED", 2, 1)
    assert "insert failed after first row" in crawl_row[3]


@pytest.mark.asyncio
async def test_jobspy_partial_insert_failure_persists_real_crawl_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify JobSpy failures persist non-zero counters after partial inserts.

    Purpose:
        Keep crawl-history counts accurate when a crawl variant fails mid-loop.
    Args:
        monkeypatch: Pytest fixture used to patch fetcher and insert behavior.
    Output:
        Returns `None`; test passes when failed crawl stores `jobs_found=2,new=1`.
    """

    class TwoJobJobSpyFetcher:
        """Return two deterministic jobs for JobSpy accounting tests."""

        def __init__(self, *_: object, **__: object) -> None:
            """Accept production constructor args without using them.

            Purpose:
                Keep this fake class signature-compatible with orchestrator.
            Args:
                *_: Ignored positional args.
                **__: Ignored keyword args.
            Output:
                Returns `None`.
            """

        async def fetch_jobs(self) -> list[JobPosting]:
            """Return two deterministic postings for one variant crawl.

            Purpose:
                Ensure one insert can succeed before forced failure.
            Args:
                self: Fake JobSpy fetcher instance.
            Output:
                Returns two normalized postings.
            """

            return [
                JobPosting(
                    source="jobspy",
                    source_url="https://example.com/jobspy-1",
                    company="Example",
                    title="One",
                    description="first",
                ),
                JobPosting(
                    source="jobspy",
                    source_url="https://example.com/jobspy-2",
                    company="Example",
                    title="Two",
                    description="second",
                ),
            ]

    async def fast_sleep(_: float) -> None:
        """Replace inter-crawl sleep with no-op for test speed.

        Purpose:
            Keep tests deterministic and fast while preserving call shape.
        Args:
            _: Sleep duration requested by production code.
        Output:
            Returns `None`.
        """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)
            original_insert_job = db.insert_job
            call_counter = {"count": 0}

            async def fail_on_second_insert(job_data: dict[str, Any]) -> bool:
                """Raise during second insert attempt to force partial failure.

                Purpose:
                    Exercise crawl-accounting behavior when insert loop fails
                    after at least one successful write.
                Args:
                    job_data: Normalized insert payload.
                Output:
                    Returns insert result for first call, raises on second.
                """

                call_counter["count"] += 1
                if call_counter["count"] == 2:
                    raise RuntimeError("insert failed after first row")
                return await original_insert_job(job_data)

            monkeypatch.setattr(discovery_main, "JobSpyFetcher", TwoJobJobSpyFetcher)
            monkeypatch.setattr(discovery_main.asyncio, "sleep", fast_sleep)
            monkeypatch.setattr(db, "insert_job", fail_on_second_insert)

            counters = await discovery_main.fetch_jobspy_jobs(
                {
                    "indeed": {
                        "enabled": True,
                        "search_terms": ["ml intern"],
                        "locations": ["Remote"],
                        "results_wanted": 10,
                    }
                },
                db,
                deduplicator,
            )

            assert db.conn is not None
            crawl_row = await (
                await db.conn.execute(
                    """
                    SELECT status, jobs_found, jobs_new, error_message
                    FROM crawl_history
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
            ).fetchone()

    assert counters == (2, 1, 0, 1)
    assert crawl_row is not None
    assert tuple(crawl_row[:3]) == ("FAILED", 2, 1)
    assert "insert failed after first row" in crawl_row[3]


@pytest.mark.asyncio
async def test_run_job_discovery_updates_daily_stats_with_start_crawl_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify daily stats still persist when one company start-crawl fails.

    Purpose:
        Ensure source-level failures do not prevent cycle-level rollup writes.
    Args:
        monkeypatch: Pytest fixture used to patch config, fetcher, and DB start.
    Output:
        Returns `None`; test passes when daily stats are persisted with mixed outcomes.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        monkeypatch.setattr(discovery_main, "resolve_database_path", lambda: db_path)
        monkeypatch.setattr(discovery_main, "GreenhouseFetcher", _StaticFetcher)
        monkeypatch.setattr(
            discovery_main,
            "load_yaml",
            lambda _path: {
                "greenhouse_companies": {
                    "BadCo": {"greenhouse_id": "bad"},
                    "GoodCo": {"greenhouse_id": "good"},
                },
                "workday_companies": {},
                "job_boards": {},
            },
        )
        from src.orchestrator.config_loader import load_optional_yaml as _real_load_optional_yaml

        monkeypatch.setattr(
            discovery_module,
            "load_optional_yaml",
            lambda path: None if Path(path).name == "filters.yaml" else _real_load_optional_yaml(path),
        )

        original_start_crawl = DatabaseManager.start_crawl

        async def flaky_start_crawl(
            self: DatabaseManager,
            source: str,
            company: str | None = None,
        ) -> int:
            """Raise for one company and delegate otherwise.

            Purpose:
                Simulate per-company crawl-start DB failure during full cycle.
            Args:
                self: Database manager instance.
                source: Crawl source identifier.
                company: Optional company name for the crawl.
            Output:
                Returns crawl ID for non-failing companies.
            """

            if source == "greenhouse" and company == "BadCo":
                raise RuntimeError("start crawl failed")
            return await original_start_crawl(self, source, company)

        monkeypatch.setattr(DatabaseManager, "start_crawl", flaky_start_crawl)

        await discovery_main.run_job_discovery()

        async with DatabaseManager(str(db_path)) as db:
            await db.connect()
            assert db.conn is not None
            row = await (
                await db.conn.execute(
                    """
                    SELECT total_jobs_discovered, jobs_new, jobs_duplicate,
                           sources_crawled, sources_failed
                    FROM daily_stats
                    ORDER BY date DESC
                    LIMIT 1
                    """
                )
            ).fetchone()

    assert row is not None
    assert tuple(row) == (1, 1, 0, 1, 1)


@pytest.mark.asyncio
async def test_jobspy_invalid_search_term_types_do_not_fan_out_per_character(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify scalar config values are ignored instead of character fan-out.

    Purpose:
        Ensure malformed `search_terms`/`locations` values do not create one
        crawl per character and noisy fetch failures.
    Args:
        monkeypatch: Pytest fixture used to patch JobSpy fetcher and sleep.
    Output:
        Returns `None`; test passes when one normalized crawl variant is used.
    """

    captured_variants: list[tuple[str, str]] = []

    class CapturingJobSpyFetcher:
        """Capture requested search variants and return no rows."""

        def __init__(
            self,
            *,
            site_name: str,
            search_term: str,
            location: str,
            results_wanted: int,
        ) -> None:
            """Store captured crawl variant arguments.

            Purpose:
                Verify orchestrator normalization before fetch fan-out.
            Args:
                self: Fake fetcher instance.
                site_name: Job board site name.
                search_term: Search term used for this crawl.
                location: Location used for this crawl.
                results_wanted: Result limit passed to fetcher.
            Output:
                Returns `None`.
            """

            _ = (site_name, results_wanted)
            captured_variants.append((search_term, location))

        async def fetch_jobs(self) -> list[JobPosting]:
            """Return an empty list for deterministic normalization tests.

            Purpose:
                Keep assertions focused on fan-out behavior, not persistence.
            Args:
                self: Fake fetcher instance.
            Output:
                Returns an empty posting list.
            """

            return []

    async def fast_sleep(_: float) -> None:
        """Replace inter-crawl sleeps with no-op for test speed.

        Purpose:
            Keep normalization test deterministic and fast.
        Args:
            _: Requested sleep duration.
        Output:
            Returns `None`.
        """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)
            monkeypatch.setattr(discovery_main, "JobSpyFetcher", CapturingJobSpyFetcher)
            monkeypatch.setattr(discovery_main.asyncio, "sleep", fast_sleep)

            counters = await discovery_main.fetch_jobspy_jobs(
                {
                    "indeed": {
                        "enabled": True,
                        "search_terms": "ml intern",
                        "locations": "Remote",
                        "results_wanted": "10",
                    }
                },
                db,
                deduplicator,
                default_search_terms=["normalized term"],
            )

    assert counters == (0, 0, 1, 0)
    assert captured_variants == [("normalized term", "Remote")]
