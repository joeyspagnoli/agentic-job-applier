"""Unit tests for LinkedInFetcher without making any network requests.

Purpose:
    Validate parameter building, HTML parsing, pagination logic, 429 backoff,
    and network error handling in isolation.  All HTTP calls are monkeypatched
    so no real LinkedIn requests are made.
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.fetchers.linkedin_fetcher import LinkedInFetcher
from src.models.job_posting import JobPosting


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
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(
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
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(
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
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(return_value=_make_mock_response(429))

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
    from curl_cffi.requests import errors as curl_errors

    fetcher = _make_fetcher(max_pages=2)
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(
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
    fetcher._session = MagicMock()
    fetcher._session.get = fake_get

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
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(
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


# ---------------------------------------------------------------------------
# _build_params — missing contract coverage
# ---------------------------------------------------------------------------


_CARD_WITHOUT_SUBTITLE_ANCHOR = """
<div class="base-card base-search-card">
  <h3 class="base-search-card__title">Some Role</h3>
  <h4 class="base-search-card__subtitle">Direct Text Company</h4>
  <span class="job-search-card__location">New York, NY</span>
</div></li>
"""

_CARD_WITHOUT_COMPANY = """
<div class="base-card base-search-card">
  <h3 class="base-search-card__title">Orphan Role</h3>
  <span class="job-search-card__location">Remote</span>
</div></li>
"""

_CARD_WITHOUT_LOCATION = """
<div class="base-card base-search-card">
  <h3 class="base-search-card__title">No Location Role</h3>
  <h4 class="base-search-card__subtitle"><a href="/company/acme">Acme</a></h4>
</div></li>
"""

_CARD_WITHOUT_URL = """
<div class="base-card base-search-card">
  <h3 class="base-search-card__title">No URL Role</h3>
  <h4 class="base-search-card__subtitle"><a href="/company/acme">Acme</a></h4>
  <span class="job-search-card__location">Remote</span>
</div></li>
"""


@pytest.mark.parametrize(
    "level,expected_code",
    [
        ("internship", "1"),
        ("entry", "2"),
        ("associate", "3"),
        ("mid-senior", "4"),
        ("director", "5"),
        ("executive", "6"),
    ],
)
def test_build_params_maps_all_experience_level_strings(
    level: str, expected_code: str
) -> None:
    fetcher = _make_fetcher(experience_level=level)

    params = fetcher._build_params(0)

    assert params["f_E"] == expected_code


@pytest.mark.parametrize(
    "work_type,expected_code",
    [
        ("on-site", "1"),
        ("remote", "2"),
        ("hybrid", "3"),
    ],
)
def test_build_params_maps_all_work_type_strings(
    work_type: str, expected_code: str
) -> None:
    fetcher = _make_fetcher(work_type=work_type)

    params = fetcher._build_params(0)

    assert params["f_WT"] == expected_code


def test_build_params_omits_work_type_when_unknown() -> None:
    fetcher = _make_fetcher(work_type="fulltime")

    params = fetcher._build_params(0)

    assert "f_WT" not in params


def test_build_params_coerces_start_to_string() -> None:
    fetcher = _make_fetcher()

    params = fetcher._build_params(7)

    assert params["start"] == "7"


def test_build_params_with_large_start_value() -> None:
    fetcher = _make_fetcher()

    params = fetcher._build_params(999)

    assert params["start"] == "999"


def test_build_params_with_zero_time_range() -> None:
    fetcher = _make_fetcher(time_range_seconds=0)

    params = fetcher._build_params(0)

    assert params["f_TPR"] == "r0"


def test_build_params_mixed_case_experience_level_matches_internship() -> None:
    fetcher = _make_fetcher(experience_level="Internship")

    params = fetcher._build_params(0)

    assert params["f_E"] == "1"


def test_build_params_excludes_optional_filter_keys_when_neither_set() -> None:
    fetcher = _make_fetcher()

    params = fetcher._build_params(0)

    assert "f_E" not in params
    assert "f_WT" not in params


# ---------------------------------------------------------------------------
# _parse_single_card — missing source field, description, company fallbacks
# ---------------------------------------------------------------------------


def test_parse_single_card_source_matches_get_source_name() -> None:
    fetcher = _make_fetcher(search_term="software engineer intern")

    result = fetcher._parse_single_card(_MINIMAL_CARD_HTML)

    assert result is not None
    assert result.source == fetcher.get_source_name()


def test_parse_single_card_description_uses_exact_linkedin_format() -> None:
    fetcher = _make_fetcher(search_term="software engineer intern")

    result = fetcher._parse_single_card(_MINIMAL_CARD_HTML)

    assert result is not None
    assert result.description == "LinkedIn job posting: Software Engineer Intern at Acme Corp"


def test_parse_single_card_extracts_company_from_direct_subtitle_text() -> None:
    fetcher = _make_fetcher()

    result = fetcher._parse_single_card(_CARD_WITHOUT_SUBTITLE_ANCHOR)

    assert result is not None
    assert result.company == "Direct Text Company"


def test_parse_single_card_defaults_company_to_unknown_when_absent() -> None:
    fetcher = _make_fetcher()

    result = fetcher._parse_single_card(_CARD_WITHOUT_COMPANY)

    assert result is not None
    assert result.company == "Unknown"


def test_parse_single_card_sets_empty_location_when_absent() -> None:
    fetcher = _make_fetcher()

    result = fetcher._parse_single_card(_CARD_WITHOUT_LOCATION)

    assert result is not None
    assert result.location == ""


def test_parse_single_card_sets_empty_source_url_when_no_href() -> None:
    fetcher = _make_fetcher()

    result = fetcher._parse_single_card(_CARD_WITHOUT_URL)

    assert result is not None
    assert result.source_url == ""


def test_parse_single_card_includes_job_id_in_raw_data() -> None:
    fetcher = _make_fetcher()

    result = fetcher._parse_single_card(_MINIMAL_CARD_HTML)

    assert result is not None
    assert result.raw_data["job_id"] == "123"


def test_parse_single_card_includes_card_html_length_in_raw_data() -> None:
    fetcher = _make_fetcher()

    result = fetcher._parse_single_card(_MINIMAL_CARD_HTML)

    assert result is not None
    assert isinstance(result.raw_data["card_html_length"], int)
    assert result.raw_data["card_html_length"] > 0


def test_parse_single_card_sets_empty_job_id_when_url_lacks_jobs_view() -> None:
    fetcher = _make_fetcher()

    result = fetcher._parse_single_card(_CARD_WITHOUT_URL)

    assert result is not None
    assert result.raw_data["job_id"] == ""


# ---------------------------------------------------------------------------
# Constructor — state is stored correctly for all config options
# ---------------------------------------------------------------------------


def test_fetcher_stores_proxy_url_from_constructor() -> None:
    fetcher = LinkedInFetcher("test role", proxy_url="http://proxy:8080")

    assert fetcher.proxy_url == "http://proxy:8080"


def test_fetcher_initial_session_is_none_before_context_entry() -> None:
    fetcher = _make_fetcher()

    assert fetcher._session is None


def test_fetcher_stores_max_pages_from_constructor() -> None:
    fetcher = _make_fetcher(max_pages=5)

    assert fetcher.max_pages == 5


def test_fetcher_stores_experience_level_from_constructor() -> None:
    fetcher = _make_fetcher(experience_level="internship")

    assert fetcher.experience_level == "internship"


def test_fetcher_stores_work_type_from_constructor() -> None:
    fetcher = _make_fetcher(work_type="remote")

    assert fetcher.work_type == "remote"


# ---------------------------------------------------------------------------
# _parse_job_cards — multi-card and titleless-skip coverage
# ---------------------------------------------------------------------------


def test_parse_job_cards_skips_card_without_title() -> None:
    fetcher = _make_fetcher()

    result = fetcher._parse_job_cards(_CARD_WITHOUT_TITLE)

    assert result == []


def test_parse_job_cards_finds_all_cards_in_two_card_blob() -> None:
    fetcher = _make_fetcher()
    two_cards = _MINIMAL_CARD_HTML * 2

    result = fetcher._parse_job_cards(two_cards)

    assert len(result) == 2


# ---------------------------------------------------------------------------
# get_source_name — missing length-cap contract coverage
# ---------------------------------------------------------------------------


def test_get_source_name_truncates_slug_to_give_at_most_39_chars() -> None:
    fetcher = _make_fetcher(search_term="a" * 100)

    source = fetcher.get_source_name()

    assert len(source) <= 39


# ---------------------------------------------------------------------------
# fetch_jobs — inter-page sleep, non-200/non-429, dual-429-then-200, 300s-never-slept
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_jobs_sleeps_exactly_once_between_two_successful_pages() -> None:
    fetcher = _make_fetcher(max_pages=2)
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(
        return_value=_make_mock_response(200, _MINIMAL_CARD_HTML)
    )
    sleep_calls: list[float] = []

    async def capture_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("src.fetchers.linkedin_fetcher.asyncio.sleep", side_effect=capture_sleep):
        jobs = await fetcher.fetch_jobs()

    assert len(jobs) == 2
    assert len(sleep_calls) == 1
    assert 8.0 <= sleep_calls[0] <= 20.0


@pytest.mark.asyncio
async def test_fetch_jobs_does_not_sleep_after_last_page() -> None:
    fetcher = _make_fetcher(max_pages=1)
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(
        return_value=_make_mock_response(200, _MINIMAL_CARD_HTML)
    )
    sleep_calls: list[float] = []

    async def capture_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("src.fetchers.linkedin_fetcher.asyncio.sleep", side_effect=capture_sleep):
        jobs = await fetcher.fetch_jobs()

    assert len(jobs) == 1
    assert sleep_calls == []


@pytest.mark.asyncio
async def test_fetch_jobs_breaks_loop_on_non_200_non_429_status() -> None:
    fetcher = _make_fetcher(max_pages=2)
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(return_value=_make_mock_response(503))

    jobs = await fetcher.fetch_jobs()

    assert jobs == []


@pytest.mark.asyncio
async def test_fetch_jobs_returns_first_page_jobs_when_second_page_is_503() -> None:
    fetcher = _make_fetcher(max_pages=2)
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(
        side_effect=[
            _make_mock_response(200, _MINIMAL_CARD_HTML),
            _make_mock_response(503),
        ]
    )

    with patch("src.fetchers.linkedin_fetcher.asyncio.sleep", new_callable=AsyncMock):
        jobs = await fetcher.fetch_jobs()

    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_fetch_jobs_two_leading_429s_then_success_returns_job_and_correct_sleeps() -> None:
    fetcher = _make_fetcher(max_pages=1)
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(
        side_effect=[
            _make_mock_response(429),
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
    assert sleep_calls == [60, 120]


@pytest.mark.asyncio
async def test_fetch_jobs_exhaustion_never_sleeps_for_300s() -> None:
    # The third _BACKOFF_SECONDS entry (300) is never slept — the code returns
    # immediately on the third 429 without waiting, contrary to the handoff spec.
    fetcher = _make_fetcher(max_pages=1)
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(return_value=_make_mock_response(429))
    sleep_calls: list[float] = []

    async def capture_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("src.fetchers.linkedin_fetcher.asyncio.sleep", side_effect=capture_sleep):
        jobs = await fetcher.fetch_jobs()

    assert jobs == []
    assert 300 not in sleep_calls


# ---------------------------------------------------------------------------
# Property-based tests — get_source_name invariants
# ---------------------------------------------------------------------------


@given(st.text(min_size=1, max_size=200))
@settings(max_examples=100)
def test_get_source_name_always_starts_with_linkedin_prefix(search_term: str) -> None:
    fetcher = _make_fetcher(search_term=search_term)

    source = fetcher.get_source_name()

    assert source.startswith("linkedin_")


@given(st.text(min_size=1, max_size=200))
@settings(max_examples=100)
def test_get_source_name_never_exceeds_39_chars(search_term: str) -> None:
    fetcher = _make_fetcher(search_term=search_term)

    source = fetcher.get_source_name()

    assert len(source) <= 39


@given(st.text(min_size=1, max_size=200))
@settings(max_examples=100)
def test_get_source_name_contains_only_valid_chars(search_term: str) -> None:
    fetcher = _make_fetcher(search_term=search_term)

    source = fetcher.get_source_name()

    assert re.fullmatch(r"[a-z0-9_]+", source) is not None


# ---------------------------------------------------------------------------
# Property-based tests — _build_params invariants
# ---------------------------------------------------------------------------


@given(
    st.integers(min_value=0, max_value=10_000),
    st.integers(min_value=0, max_value=10_000_000),
)
@settings(max_examples=100)
def test_build_params_always_includes_required_keys(start: int, time_range: int) -> None:
    fetcher = _make_fetcher(time_range_seconds=time_range)

    params = fetcher._build_params(start)

    assert "keywords" in params
    assert "location" in params
    assert "start" in params
    assert "f_TPR" in params


@given(st.integers(min_value=0, max_value=10_000))
@settings(max_examples=100)
def test_build_params_start_is_always_stringified_integer(start: int) -> None:
    fetcher = _make_fetcher()

    params = fetcher._build_params(start)

    assert params["start"] == str(start)


# ---------------------------------------------------------------------------
# Fuzz tests — _parse_job_cards and _parse_single_card crash safety
# ---------------------------------------------------------------------------


@given(st.text(max_size=5000))
@settings(max_examples=1000)
def test_parse_job_cards_never_raises_on_arbitrary_html(html: str) -> None:
    fetcher = _make_fetcher()

    result = fetcher._parse_job_cards(html)

    assert isinstance(result, list)


@given(st.text(max_size=5000))
@settings(max_examples=1000)
def test_parse_single_card_never_raises_on_arbitrary_html(card_html: str) -> None:
    fetcher = _make_fetcher()

    result = fetcher._parse_single_card(card_html)

    assert result is None or isinstance(result, JobPosting)


# ---------------------------------------------------------------------------
# Constructor — default parameter values
# ---------------------------------------------------------------------------


def test_fetcher_default_location_is_united_states() -> None:
    fetcher = LinkedInFetcher("some role")

    assert fetcher.location == "United States"


def test_fetcher_default_time_range_seconds_is_86400() -> None:
    fetcher = LinkedInFetcher("some role")

    assert fetcher.time_range_seconds == 86400


def test_fetcher_default_fetch_descriptions_is_false() -> None:
    fetcher = LinkedInFetcher("some role")

    assert fetcher.fetch_descriptions is False


def test_fetcher_default_max_pages_is_two() -> None:
    fetcher = LinkedInFetcher("some role")

    assert fetcher.max_pages == 2


# ---------------------------------------------------------------------------
# __aenter__ — AsyncSession is created with correct arguments
# ---------------------------------------------------------------------------

_EXPECTED_HEADERS: dict[str, str] = {
    "authority": "www.linkedin.com",
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "priority": "u=0, i",
    "sec-ch-ua": '"Chromium";v="120", "Google Chrome";v="120", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


@pytest.mark.asyncio
async def test_aenter_creates_session_with_chrome120_impersonation_and_30s_timeout() -> None:
    fetcher = _make_fetcher()

    with patch("src.fetchers.linkedin_fetcher.AsyncSession") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.close = AsyncMock()
        mock_cls.return_value = mock_instance
        await fetcher.__aenter__()

    mock_cls.assert_called_once_with(
        impersonate="chrome120",
        proxies=None,
        headers=_EXPECTED_HEADERS,
        timeout=30,
    )
    assert fetcher._session is mock_instance


@pytest.mark.asyncio
async def test_aenter_passes_proxy_dict_with_all_key_when_proxy_url_set() -> None:
    fetcher = LinkedInFetcher("dev role", proxy_url="http://proxy:8080")

    with patch("src.fetchers.linkedin_fetcher.AsyncSession") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.close = AsyncMock()
        mock_cls.return_value = mock_instance
        await fetcher.__aenter__()

    actual_proxies = mock_cls.call_args.kwargs["proxies"]
    assert actual_proxies == {"all": "http://proxy:8080"}


@pytest.mark.asyncio
async def test_aenter_passes_full_headers_dict_to_session() -> None:
    fetcher = _make_fetcher()

    with patch("src.fetchers.linkedin_fetcher.AsyncSession") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.close = AsyncMock()
        mock_cls.return_value = mock_instance
        await fetcher.__aenter__()

    actual_headers = mock_cls.call_args.kwargs["headers"]
    assert actual_headers == _EXPECTED_HEADERS


# ---------------------------------------------------------------------------
# __aexit__ — session is cleared to None on exit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aexit_sets_session_to_none_after_context_exit() -> None:
    fetcher = _make_fetcher()

    with patch("src.fetchers.linkedin_fetcher.AsyncSession") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.close = AsyncMock()
        mock_cls.return_value = mock_instance
        async with fetcher:
            pass

    assert fetcher._session is None


# ---------------------------------------------------------------------------
# fetch_jobs — correct LinkedIn URL used in session.get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_jobs_calls_session_get_with_correct_linkedin_guest_url() -> None:
    fetcher = _make_fetcher(max_pages=1)
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(
        return_value=_make_mock_response(200, _MINIMAL_CARD_HTML)
    )

    await fetcher.fetch_jobs()

    actual_url = fetcher._session.get.call_args.args[0]
    assert actual_url == "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"


# ---------------------------------------------------------------------------
# fetch_jobs — inter-page delay uses correct random range constants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_jobs_inter_page_delay_calls_random_uniform_with_correct_bounds() -> None:
    fetcher = _make_fetcher(max_pages=2)
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(
        return_value=_make_mock_response(200, _MINIMAL_CARD_HTML)
    )

    with patch("src.fetchers.linkedin_fetcher.random.uniform", return_value=10.0) as mock_uniform:
        with patch("src.fetchers.linkedin_fetcher.asyncio.sleep", new_callable=AsyncMock):
            await fetcher.fetch_jobs()

    mock_uniform.assert_called_once_with(8.0, 20.0)


# ---------------------------------------------------------------------------
# fetch_jobs — break on non-200 stops all subsequent pages (not continue)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_jobs_non_200_middle_page_stops_further_requests() -> None:
    fetcher = _make_fetcher(max_pages=3)
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(
        side_effect=[
            _make_mock_response(200, _MINIMAL_CARD_HTML),
            _make_mock_response(503),
            _make_mock_response(200, _MINIMAL_CARD_HTML),
        ]
    )

    with patch("src.fetchers.linkedin_fetcher.asyncio.sleep", new_callable=AsyncMock):
        jobs = await fetcher.fetch_jobs()

    assert len(jobs) == 1
    assert fetcher._session.get.call_count == 2


# ---------------------------------------------------------------------------
# fetch_jobs — start offset accumulates across pages (not reset each page)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_jobs_start_offset_accumulates_correctly_across_three_pages() -> None:
    fetcher = _make_fetcher(max_pages=3)
    fetcher._session = MagicMock()
    fetcher._session.get = AsyncMock(
        side_effect=[
            _make_mock_response(200, _MINIMAL_CARD_HTML * 7),
            _make_mock_response(200, _MINIMAL_CARD_HTML * 3),
            _make_mock_response(200, _MINIMAL_CARD_HTML * 2),
        ]
    )

    with patch("src.fetchers.linkedin_fetcher.asyncio.sleep", new_callable=AsyncMock):
        jobs = await fetcher.fetch_jobs()

    assert len(jobs) == 12
    call_list = fetcher._session.get.call_args_list
    assert call_list[0].kwargs["params"]["start"] == "0"
    assert call_list[1].kwargs["params"]["start"] == "7"
    assert call_list[2].kwargs["params"]["start"] == "10"
