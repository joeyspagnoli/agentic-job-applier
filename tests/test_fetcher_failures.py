"""Validate failure signaling behavior in source fetchers."""

from __future__ import annotations

import pytest

from src.fetchers.apify_fetcher import ApifyWorkdayFetcher
from src.fetchers.errors import FetchError
from src.fetchers.jobspy_fetcher import JobSpyFetcher


@pytest.mark.asyncio
async def test_apify_fetcher_raises_fetch_error_when_actor_call_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify actor-call failures bubble up as `FetchError`.

    Purpose:
        Ensure orchestrator accounting can distinguish provider failures from
        legitimate empty result sets.
    Args:
        monkeypatch: Pytest fixture used to force actor-call failure.
    Output:
        Returns `None`; the test passes when `FetchError` is raised.
    """

    def raise_actor_error():
        """Raise a deterministic actor failure.

        Purpose:
            Trigger Apify failure handling in `fetch_jobs`.
        Args:
            None.
        Output:
            Raises `RuntimeError`.
        """

        raise RuntimeError("actor failed")

    fetcher = ApifyWorkdayFetcher("Example", "https://example.workday.com")
    fetcher._client = object()
    monkeypatch.setattr(fetcher, "_run_actor_sync", raise_actor_error)

    with pytest.raises(FetchError):
        await fetcher.fetch_jobs()


@pytest.mark.asyncio
async def test_jobspy_fetcher_raises_fetch_error_when_scrape_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify scrape failures bubble up as `FetchError`.

    Purpose:
        Ensure upstream JobSpy errors are exposed to the orchestrator failure
        accounting path.
    Args:
        monkeypatch: Pytest fixture used to force scrape failure.
    Output:
        Returns `None`; the test passes when `FetchError` is raised.
    """

    def raise_scrape_error():
        """Raise a deterministic scrape failure.

        Purpose:
            Trigger JobSpy failure handling in `fetch_jobs`.
        Args:
            None.
        Output:
            Raises `RuntimeError`.
        """

        raise RuntimeError("scrape failed")

    fetcher = JobSpyFetcher(
        site_name="indeed",
        search_term="software engineer",
        location="Remote",
        results_wanted=5,
    )
    monkeypatch.setattr(fetcher, "_scrape_sync", raise_scrape_error)

    with pytest.raises(FetchError):
        await fetcher.fetch_jobs()

