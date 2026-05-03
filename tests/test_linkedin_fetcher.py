"""Unit tests for LinkedInFetcher without making any network requests.

Purpose:
    Validate parameter building, HTML parsing, pagination logic, 429 backoff,
    and network error handling in isolation.  All HTTP calls are monkeypatched
    so no real LinkedIn requests are made.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.fetchers.linkedin_fetcher import LinkedInFetcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_CARD_HTML = """
<div class="base-card base-search-card" data-entity-urn="urn:li:jobPosting:123">
  <a href="https://www.linkedin.com/jobs/view/123?trackingId=abc" class="base-card__full-link">
    <h3 class="base-search-card__title">Software Engineer Intern</h3>
    <h4 class="base-search-card__subtitle">
      <a href="/company/acme">Acme Corp</a>
    </h4>
    <span class="job-search-card__location">San Francisco, CA</span>
    <time datetime="2026-05-01">1 week ago</time>
  </a>
</div></li>
"""

_CARD_WITHOUT_TITLE = """
<div class="base-card base-search-card">
  <span class="job-search-card__location">Nowhere</span>
</div></li>
"""


def _make_fetcher(**kwargs: Any) -> LinkedInFetcher:
    """Construct a LinkedInFetcher with test defaults.

    Purpose:
        Avoid repeating constructor arguments across every test.
    Args:
        **kwargs: Overrides for LinkedInFetcher constructor parameters.
    Returns:
        A LinkedInFetcher configured for testing (no HTTP session opened).
    """
    defaults: dict[str, Any] = {
        "search_term": "software engineer intern",
        "location": "United States",
        "max_pages": 2,
    }
    defaults.update(kwargs)
    return LinkedInFetcher(**defaults)


def _make_mock_response(status_code: int, text: str = "") -> MagicMock:
    """Build a mock HTTP response object.

    Purpose:
        Provide a response with a controllable status_code and text body
        for use in monkeypatched session.get calls.
    Args:
        status_code: HTTP status to return.
        text: Response body text to return.
    Returns:
        A MagicMock configured with the given status_code and text.
    """
    mock = MagicMock()
    mock.status_code = status_code
    mock.text = text
    return mock


# ---------------------------------------------------------------------------
# _build_params tests
# ---------------------------------------------------------------------------


def test_build_params_includes_required_fields() -> None:
    """Verify _build_params always emits keywords, location, start, and f_TPR.

    Purpose:
        Confirm the four required LinkedIn API query parameters are present
        for a minimal fetcher with no optional filters set.
    Args:
        None.
    Returns:
        None; asserts on param keys and values.
    """
    fetcher = _make_fetcher(search_term="EE intern", time_range_seconds=3600)

    params = fetcher._build_params(0)

    assert params["keywords"] == "EE intern"
    assert params["location"] == "United States"
    assert params["start"] == "0"
    assert params["f_TPR"] == "r3600"


def test_build_params_adds_experience_level_when_set() -> None:
    """Verify f_E is added when experience_level is recognized.

    Purpose:
        Confirm the experience level filter maps the string to its integer
        code and includes it in the parameter dict.
    Args:
        None.
    Returns:
        None; asserts f_E equals the expected code string.
    """
    fetcher = _make_fetcher(experience_level="internship")

    params = fetcher._build_params(0)

    assert params["f_E"] == "1"


def test_build_params_omits_experience_level_when_unknown() -> None:
    """Verify f_E is absent when experience_level value is not in the lookup.

    Purpose:
        Guard against sending a malformed f_E value when the config contains
        an unrecognized string.
    Args:
        None.
    Returns:
        None; asserts f_E key is absent.
    """
    fetcher = _make_fetcher(experience_level="unicorn")

    params = fetcher._build_params(0)

    assert "f_E" not in params


def test_build_params_adds_work_type_when_set() -> None:
    """Verify f_WT is added when work_type is recognized.

    Purpose:
        Confirm the work type filter maps the string to its integer code.
    Args:
        None.
    Returns:
        None; asserts f_WT equals the expected code string.
    """
    fetcher = _make_fetcher(work_type="remote")

    params = fetcher._build_params(0)

    assert params["f_WT"] == "2"


# ---------------------------------------------------------------------------
# _parse_job_cards tests
# ---------------------------------------------------------------------------


def test_parse_job_cards_returns_empty_for_blank_html() -> None:
    """Verify _parse_job_cards returns an empty list given empty HTML.

    Purpose:
        Confirm the parser handles the empty-page termination case without
        raising an exception.
    Args:
        None.
    Returns:
        None; asserts result is an empty list.
    """
    fetcher = _make_fetcher()

    result = fetcher._parse_job_cards("")

    assert result == []


def test_parse_single_card_returns_none_when_title_missing() -> None:
    """Verify _parse_single_card returns None when no title element is found.

    Purpose:
        Confirm the parser rejects cards that lack a base-search-card__title
        element so that title-less postings are not inserted into the DB.
    Args:
        None.
    Returns:
        None; asserts the result is None.
    """
    fetcher = _make_fetcher()

    result = fetcher._parse_single_card(_CARD_WITHOUT_TITLE)

    assert result is None


def test_parse_single_card_extracts_fields_from_minimal_html() -> None:
    """Verify _parse_single_card extracts title, company, location, and date.

    Purpose:
        Confirm that a correctly structured card fragment produces a
        JobPosting with populated fields.
    Args:
        None.
    Returns:
        None; asserts individual JobPosting field values.
    """
    fetcher = _make_fetcher(search_term="software engineer intern")

    result = fetcher._parse_single_card(_MINIMAL_CARD_HTML)

    assert result is not None
    assert result.title == "Software Engineer Intern"
    assert result.company == "Acme Corp"
    assert result.location == "San Francisco, CA"
    assert result.posted_date == "2026-05-01"
    assert "linkedin.com/jobs/view/123" in result.source_url


# ---------------------------------------------------------------------------
# get_source_name tests
# ---------------------------------------------------------------------------


def test_get_source_name_slugifies_search_term() -> None:
    """Verify get_source_name produces a lowercase, punctuation-free slug.

    Purpose:
        Ensure the source identifier is stable and machine-friendly so that
        deduplication logic can match across polling cycles.
    Args:
        None.
    Returns:
        None; asserts slug format and prefix.
    """
    fetcher = _make_fetcher(search_term="EE Internship!")

    source = fetcher.get_source_name()

    assert source.startswith("linkedin_")
    assert source == "linkedin_ee_internship_"


# ---------------------------------------------------------------------------
# fetch_jobs async tests (monkeypatched session)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_jobs_stops_on_empty_second_page() -> None:
    """Verify the page loop terminates when a page returns no job cards.

    Purpose:
        Confirm that an empty HTML response on page 2 stops pagination
        and the jobs from page 1 are still returned.
    Args:
        None.
    Returns:
        None; asserts only page-1 jobs are present.
    """
    fetcher = _make_fetcher(max_pages=3)
    fetcher._session = MagicMock()  # type: ignore[assignment]
    fetcher._session.get = AsyncMock(  # type: ignore[union-attr]
        side_effect=[
            _make_mock_response(200, _MINIMAL_CARD_HTML),
            _make_mock_response(200, ""),
        ]
    )

    with patch("src.fetchers.linkedin_fetcher.asyncio.sleep", new_callable=AsyncMock):
        jobs = await fetcher.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].title == "Software Engineer Intern"


@pytest.mark.asyncio
async def test_fetch_jobs_returns_all_jobs_on_success() -> None:
    """Verify all jobs from multiple pages are accumulated and returned.

    Purpose:
        Confirm that pagination collects results across all pages up to
        max_pages when every page returns results.
    Args:
        None.
    Returns:
        None; asserts total job count equals two pages of one job each.
    """
    fetcher = _make_fetcher(max_pages=2)
    fetcher._session = MagicMock()  # type: ignore[assignment]
    fetcher._session.get = AsyncMock(  # type: ignore[union-attr]
        return_value=_make_mock_response(200, _MINIMAL_CARD_HTML)
    )

    with patch("src.fetchers.linkedin_fetcher.asyncio.sleep", new_callable=AsyncMock):
        jobs = await fetcher.fetch_jobs()

    assert len(jobs) == 2


@pytest.mark.asyncio
async def test_fetch_jobs_returns_early_on_429_after_all_backoffs() -> None:
    """Verify fetch_jobs gives up and returns collected jobs after three 429s.

    Purpose:
        Confirm that the exponential backoff schedule exhausts after 3
        attempts and returns whatever jobs were collected before the block.
    Args:
        None.
    Returns:
        None; asserts an empty list is returned after three 429 responses.
    """
    fetcher = _make_fetcher(max_pages=2)
    fetcher._session = MagicMock()  # type: ignore[assignment]
    fetcher._session.get = AsyncMock(return_value=_make_mock_response(429))  # type: ignore[union-attr]

    sleep_calls: list[float] = []

    async def capture_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("src.fetchers.linkedin_fetcher.asyncio.sleep", side_effect=capture_sleep):
        jobs = await fetcher.fetch_jobs()

    assert jobs == []
    # Two backoff sleeps fired (60s and 120s) before the third attempt gives up.
    assert sleep_calls == [60, 120]


@pytest.mark.asyncio
async def test_fetch_jobs_handles_network_error() -> None:
    """Verify a curl_cffi network exception returns jobs collected so far.

    Purpose:
        Confirm that a mid-pagination network error does not crash the
        fetcher; it returns an empty list and logs the error.
    Args:
        None.
    Returns:
        None; asserts an empty list is returned.
    """
    from curl_cffi.requests import errors as curl_errors  # type: ignore[import-untyped]

    fetcher = _make_fetcher(max_pages=2)
    fetcher._session = MagicMock()  # type: ignore[assignment]
    fetcher._session.get = AsyncMock(  # type: ignore[union-attr]
        side_effect=curl_errors.RequestsError("connection refused")
    )

    jobs = await fetcher.fetch_jobs()

    assert jobs == []


@pytest.mark.asyncio
async def test_pagination_uses_actual_page_size_not_constant() -> None:
    """Verify the start offset increments by actual result count, not 25.

    Purpose:
        Guard against the old bug where start += RESULTS_PER_PAGE (25)
        skipped results when LinkedIn returned fewer than 25 per page.
        Confirms start on the second request equals the count of jobs
        returned on the first page.
    Args:
        None.
    Returns:
        None; asserts the start param on the second GET is "7".
    """
    seven_cards = _MINIMAL_CARD_HTML * 7

    call_count = 0
    captured_starts: list[str] = []

    async def fake_get(_url: str, params: dict[str, str] | None = None) -> MagicMock:
        nonlocal call_count
        captured_starts.append((params or {}).get("start", ""))
        call_count += 1
        if call_count == 1:
            return _make_mock_response(200, seven_cards)
        return _make_mock_response(200, "")

    fetcher = _make_fetcher(max_pages=2)
    fetcher._session = MagicMock()  # type: ignore[assignment]
    fetcher._session.get = fake_get  # type: ignore[assignment,union-attr]

    with patch("src.fetchers.linkedin_fetcher.asyncio.sleep", new_callable=AsyncMock):
        await fetcher.fetch_jobs()

    assert captured_starts[0] == "0"
    assert captured_starts[1] == "7"


@pytest.mark.asyncio
async def test_fetch_jobs_retries_once_on_429_then_succeeds() -> None:
    """Verify fetch_jobs retries after a 429 and returns results on success.

    Purpose:
        Confirm that a single 429 triggers one backoff sleep and the
        subsequent successful response is processed normally.
    Args:
        None.
    Returns:
        None; asserts one job is returned and one sleep was called.
    """
    fetcher = _make_fetcher(max_pages=1)
    fetcher._session = MagicMock()  # type: ignore[assignment]
    fetcher._session.get = AsyncMock(  # type: ignore[union-attr]
        side_effect=[
            _make_mock_response(429),
            _make_mock_response(200, _MINIMAL_CARD_HTML),
        ]
    )

    sleep_calls: list[float] = []

    async def capture_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("src.fetchers.linkedin_fetcher.asyncio.sleep", side_effect=capture_sleep):
        jobs = await fetcher.fetch_jobs()

    assert len(jobs) == 1
    assert sleep_calls == [60]
