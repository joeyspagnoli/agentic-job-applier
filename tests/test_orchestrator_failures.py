"""Cover orchestrator accounting behavior for source success and failure paths."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import main as discovery_main
from src.database.db_manager import DatabaseManager
from src.utils.deduplicator import Deduplicator


@pytest.mark.asyncio
async def test_fetch_workday_jobs_runs_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Workday crawling runs without any environment credentials.

    Purpose:
        The free WorkdayFetcher hits the public CXS endpoint directly, so the
        orchestrator must no longer gate on `APIFY_API_TOKEN` and should reach
        the per-company crawl loop unconditionally.
    Args:
        monkeypatch: Pytest fixture used to replace the Workday fetcher.
    Output:
        Returns `None`; the test passes when the empty-result fake fetcher
        produces a clean (0, 0, 1, 0) counter tuple.
    """

    class EmptyWorkdayFetcher:
        """Return an empty job list to exercise the success accounting path."""

        def __init__(self, *_: object, **__: object) -> None:
            """Accept production-shape arguments without storing state."""

        async def __aenter__(self) -> "EmptyWorkdayFetcher":
            """Return this stub for use as an async context manager."""

            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: object,
        ) -> None:
            """Implement no-op async cleanup for the stub fetcher."""

        async def fetch_jobs(self) -> list[object]:
            """Return an empty list to mirror a healthy zero-result crawl."""

            return []

    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.setattr(discovery_main, "WorkdayFetcher", EmptyWorkdayFetcher)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            counters = await discovery_main.fetch_workday_jobs(
                {"ExampleCo": {"workday_url": "https://example.wd1.myworkdayjobs.com/Careers"}},
                db,
                deduplicator,
            )

    assert counters == (0, 0, 1, 0)


@pytest.mark.asyncio
async def test_fetch_workday_jobs_counts_fetch_exceptions_as_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Workday fetch exceptions increment failure counters and history.

    Purpose:
        Confirm that fetcher failures are recorded as failed crawl attempts
        instead of being reported as successful empty crawls.
    Args:
        monkeypatch: Pytest fixture used to replace the Workday fetcher.
    Output:
        Returns `None`; the test passes when the failed crawl is counted and
        persisted with FAILED status.
    """

    class BrokenWorkdayFetcher:
        """Raise a deterministic exception from the fetch path."""

        def __init__(self, *_: object, **__: object) -> None:
            """Store no state for the deterministic failure stub.

            Purpose:
                Keep the fake fetcher constructor compatible with production
                call sites without carrying any runtime behavior.
            Args:
                *_: Ignored positional arguments.
                **__: Ignored keyword arguments.
            Output:
                Returns `None`.
            """

        async def __aenter__(self) -> "BrokenWorkdayFetcher":
            """Return this stub instance for async context manager use.

            Purpose:
                Match the production fetcher context-manager interface.
            Args:
                self: The stub fetcher instance.
            Output:
                Returns `self`.
            """

            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: object,
        ) -> None:
            """Implement no-op async cleanup for the stub fetcher.

            Purpose:
                Satisfy context-manager protocol parity with production fetchers.
            Args:
                self: The stub fetcher instance.
                exc_type: Exception type raised in context, if any.
                exc_val: Exception instance raised in context, if any.
                exc_tb: Exception traceback raised in context, if any.
            Output:
                Returns `None`.
            """

        async def fetch_jobs(self) -> list[object]:
            """Raise a deterministic provider failure.

            Purpose:
                Simulate an upstream Workday CXS failure for accounting tests.
            Args:
                self: The stub fetcher instance.
            Output:
                Raises `RuntimeError`.
            """

            raise RuntimeError("simulated workday outage")

    monkeypatch.setattr(discovery_main, "WorkdayFetcher", BrokenWorkdayFetcher)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            counters = await discovery_main.fetch_workday_jobs(
                {"ExampleCo": {"workday_url": "https://example.wd1.myworkdayjobs.com/Careers"}},
                db,
                deduplicator,
            )

            assert counters == (0, 0, 0, 1)
            assert db.conn is not None
            row = await (
                await db.conn.execute(
                    "SELECT status, error_message FROM crawl_history ORDER BY id DESC LIMIT 1"
                )
            ).fetchone()

    assert row is not None
    assert row[0] == "FAILED"
    assert "simulated workday outage" in row[1]


@pytest.mark.asyncio
async def test_fetch_jobspy_jobs_counts_fetch_exceptions_as_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify JobSpy fetch exceptions are tracked as source failures.

    Purpose:
        Ensure JobSpy scrape failures are reflected in both return counters and
        persisted crawl history rows.
    Args:
        monkeypatch: Pytest fixture used to replace the JobSpy fetcher and sleep.
    Output:
        Returns `None`; the test passes when failures are counted and persisted.
    """

    class BrokenJobSpyFetcher:
        """Raise a deterministic scrape error from `fetch_jobs`."""

        def __init__(self, *_: object, **__: object) -> None:
            """Store no state for this deterministic failure stub.

            Purpose:
                Keep the stub constructor compatible with production call sites.
            Args:
                *_: Ignored positional arguments.
                **__: Ignored keyword arguments.
            Output:
                Returns `None`.
            """

        async def fetch_jobs(self) -> list[object]:
            """Raise a deterministic scrape failure.

            Purpose:
                Simulate a JobSpy provider outage for orchestrator accounting.
            Args:
                self: The stub fetcher instance.
            Output:
                Raises `RuntimeError`.
            """

            raise RuntimeError("simulated jobspy outage")

    async def fast_sleep(_: float) -> None:
        """Replace inter-crawl sleep with a no-op.

        Purpose:
            Keep orchestrator failure tests fast and deterministic.
        Args:
            _: Ignored sleep duration.
        Output:
            Returns `None`.
        """

    monkeypatch.setattr(discovery_main, "JobSpyFetcher", BrokenJobSpyFetcher)
    monkeypatch.setattr(discovery_main.asyncio, "sleep", fast_sleep)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            counters = await discovery_main.fetch_jobspy_jobs(
                {
                    "indeed": {
                        "enabled": True,
                        "search_terms": ["python engineer"],
                        "locations": ["Remote"],
                        "results_wanted": 5,
                    }
                },
                db,
                deduplicator,
            )

            assert counters == (0, 0, 0, 1)
            assert db.conn is not None
            row = await (
                await db.conn.execute(
                    "SELECT status, error_message FROM crawl_history ORDER BY id DESC LIMIT 1"
                )
            ).fetchone()

    assert row is not None
    assert row[0] == "FAILED"
    assert "simulated jobspy outage" in row[1]


@pytest.mark.asyncio
async def test_run_job_discovery_updates_daily_stats_with_mixed_source_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify cycle-level daily stats aggregate source tuples correctly.

    Purpose:
        Protect the final daily stats rollup from regressions in aggregation
        logic when source families return mixed success/failure counts.
    Args:
        monkeypatch: Pytest fixture used to isolate config and source functions.
    Output:
        Returns `None`; the test passes when the persisted row matches expected
        aggregate counts.
    """

    async def fake_greenhouse(*_: object, **__: object) -> tuple[int, int, int, int]:
        """Return deterministic Greenhouse counters.

        Purpose:
            Isolate daily-stats aggregation from real network behavior.
        Args:
            *_: Ignored positional arguments.
        Output:
            Returns a deterministic counter tuple.
        """

        return 10, 4, 1, 1

    async def fake_workday(*_: object, **__: object) -> tuple[int, int, int, int]:
        """Return deterministic Workday counters.

        Purpose:
            Isolate daily-stats aggregation from real network behavior.
        Args:
            *_: Ignored positional arguments.
        Output:
            Returns a deterministic counter tuple.
        """

        return 5, 2, 1, 0

    async def fake_jobspy(*_: object, **__: object) -> tuple[int, int, int, int]:
        """Return deterministic JobSpy counters.

        Purpose:
            Isolate daily-stats aggregation from real network behavior.
        Args:
            *_: Ignored positional arguments.
            **__: Ignored keyword arguments.
        Output:
            Returns a deterministic counter tuple.
        """

        return 7, 3, 2, 1

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        monkeypatch.setattr(discovery_main, "resolve_database_path", lambda: db_path)
        monkeypatch.setattr(
            discovery_main,
            "load_yaml",
            lambda _path: {
                "greenhouse_companies": {"A": {"greenhouse_id": "a"}},
                "workday_companies": {"B": {"workday_url": "https://b"}},
                "job_boards": {"indeed": {"enabled": True}},
            },
        )
        monkeypatch.setattr(discovery_main, "fetch_greenhouse_jobs", fake_greenhouse)
        monkeypatch.setattr(discovery_main, "fetch_workday_jobs", fake_workday)
        monkeypatch.setattr(discovery_main, "fetch_jobspy_jobs", fake_jobspy)

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
    assert tuple(row) == (22, 9, 13, 4, 2)
