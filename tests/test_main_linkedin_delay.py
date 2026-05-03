"""Unit tests for the inter-search delay behaviour in fetch_linkedin_jobs.

Purpose:
    Verify that the first search in a batch fires immediately (no delay) and
    that every subsequent search receives a random 30–90 s delay before its
    fetcher runs.  All external dependencies (DB, deduplicator, HTTP) are
    mocked so no real requests are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from main import fetch_linkedin_jobs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> MagicMock:
    db = MagicMock()
    db.start_crawl = AsyncMock(return_value=1)
    db.complete_crawl = AsyncMock()
    return db


def _make_deduplicator() -> MagicMock:
    dedup = MagicMock()
    dedup.filter_new_jobs = AsyncMock(return_value=[])
    return dedup


def _make_fetcher_cls_mock() -> MagicMock:
    inst = MagicMock()
    inst.fetch_jobs = AsyncMock(return_value=[])
    inst.__aenter__ = AsyncMock(return_value=inst)
    inst.__aexit__ = AsyncMock(return_value=None)
    cls = MagicMock(return_value=inst)
    return cls


# ---------------------------------------------------------------------------
# Inter-search delay tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_linkedin_jobs_single_search_fires_no_inter_search_delay() -> None:
    linkedin_config = {
        "searches": [{"search_term": "software intern", "location": "USA"}],
        "time_range_seconds": 86400,
        "max_pages": 1,
    }
    sleep_calls: list[float] = []

    async def capture_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("main.LinkedInFetcher", _make_fetcher_cls_mock()):
        with patch("main._insert_with_filters", new_callable=AsyncMock, return_value=(0, 0)):
            with patch("main.log_crawl_summary"):
                with patch("main.asyncio.sleep", side_effect=capture_sleep):
                    await fetch_linkedin_jobs(linkedin_config, _make_db(), _make_deduplicator())

    assert sleep_calls == []


@pytest.mark.asyncio
async def test_fetch_linkedin_jobs_second_search_gets_exactly_one_inter_search_delay() -> None:
    linkedin_config = {
        "searches": [
            {"search_term": "software intern", "location": "USA"},
            {"search_term": "data intern", "location": "USA"},
        ],
        "time_range_seconds": 86400,
        "max_pages": 1,
    }
    sleep_calls: list[float] = []

    async def capture_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("main.LinkedInFetcher", _make_fetcher_cls_mock()):
        with patch("main._insert_with_filters", new_callable=AsyncMock, return_value=(0, 0)):
            with patch("main.log_crawl_summary"):
                with patch("main.asyncio.sleep", side_effect=capture_sleep):
                    await fetch_linkedin_jobs(linkedin_config, _make_db(), _make_deduplicator())

    assert len(sleep_calls) == 1
    assert 30 <= sleep_calls[0] <= 90


@pytest.mark.asyncio
async def test_fetch_linkedin_jobs_three_searches_get_two_inter_search_delays() -> None:
    linkedin_config = {
        "searches": [
            {"search_term": "software intern", "location": "USA"},
            {"search_term": "data intern", "location": "USA"},
            {"search_term": "ml intern", "location": "USA"},
        ],
        "time_range_seconds": 86400,
        "max_pages": 1,
    }
    sleep_calls: list[float] = []

    async def capture_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("main.LinkedInFetcher", _make_fetcher_cls_mock()):
        with patch("main._insert_with_filters", new_callable=AsyncMock, return_value=(0, 0)):
            with patch("main.log_crawl_summary"):
                with patch("main.asyncio.sleep", side_effect=capture_sleep):
                    await fetch_linkedin_jobs(linkedin_config, _make_db(), _make_deduplicator())

    assert len(sleep_calls) == 2
    assert all(30 <= s <= 90 for s in sleep_calls)


@pytest.mark.asyncio
async def test_fetch_linkedin_jobs_delay_uses_raw_enumerate_index_not_valid_count() -> None:
    # The delay fires when search_index > 0 using the raw enumerate position.
    # A skipped empty-term entry still increments the index, so the first valid
    # search at position 1 receives the delay even though no prior search ran.
    linkedin_config = {
        "searches": [
            {"search_term": "", "location": "USA"},
            {"search_term": "software intern", "location": "USA"},
        ],
        "time_range_seconds": 86400,
        "max_pages": 1,
    }
    sleep_calls: list[float] = []

    async def capture_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("main.LinkedInFetcher", _make_fetcher_cls_mock()):
        with patch("main._insert_with_filters", new_callable=AsyncMock, return_value=(0, 0)):
            with patch("main.log_crawl_summary"):
                with patch("main.asyncio.sleep", side_effect=capture_sleep):
                    await fetch_linkedin_jobs(linkedin_config, _make_db(), _make_deduplicator())

    assert len(sleep_calls) == 1
    assert 30 <= sleep_calls[0] <= 90
