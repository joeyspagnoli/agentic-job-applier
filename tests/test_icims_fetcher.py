"""Validate ICIMSFetcher parsing, pagination, and error-handling behavior."""

from __future__ import annotations

import unittest.mock
from pathlib import Path

import httpx
import pytest

from src.fetchers.errors import FetchError
from src.fetchers.icims_fetcher import (
    INTER_PAGE_SLEEP,
    MAX_RETRIES,
    RETRY_BASE_DELAY,
    ICIMSFetcher,
    _ats_id,
    _resolve_base_url,
    _strip,
)
from src.models.job_posting import JobPosting


FIXTURE_DIR = Path(__file__).parent / "fixtures"

DOLLAR_GENERAL_SUBDOMAIN = "jobs-dollargeneral.icims.com"
DOLLAR_GENERAL_BASE = "https://jobs-dollargeneral.icims.com"


def _make_icims(
    *,
    company_name: str = "Dollar General",
    icims_subdomain: str = DOLLAR_GENERAL_SUBDOMAIN,
) -> ICIMSFetcher:
    """Build a fetcher with no HTTP setup for unit tests.

    Args:
        company_name: Name passed to the constructor.
        icims_subdomain: Subdomain or URL passed to the constructor.

    Returns:
        An ``ICIMSFetcher`` instance without an HTTP client attached.
    """
    return ICIMSFetcher(company_name=company_name, icims_subdomain=icims_subdomain)


def _load_fixture(name: str) -> str:
    """Load an HTML fixture from the shared fixtures directory.

    Args:
        name: File name within ``tests/fixtures/``.

    Returns:
        The raw HTML string.
    """
    return (FIXTURE_DIR / name).read_text()


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------


def test_resolve_base_url_bare_subdomain() -> None:
    """Bare subdomain gets ``https://`` prepended and no trailing slash."""

    result = _resolve_base_url(DOLLAR_GENERAL_SUBDOMAIN)

    assert result == DOLLAR_GENERAL_BASE


def test_resolve_base_url_full_https_url_passthrough() -> None:
    """Full HTTPS URL passes through unchanged (no double prefix)."""

    full_url = "https://uscareers-nyu.icims.com"
    result = _resolve_base_url(full_url)

    assert result == full_url


def test_resolve_base_url_uscareers_prefix() -> None:
    """``uscareers-`` subdomain is handled as a bare subdomain correctly."""

    result = _resolve_base_url("uscareers-nyu.icims.com")

    assert result == "https://uscareers-nyu.icims.com"


def test_resolve_base_url_strips_trailing_slash_from_bare_subdomain() -> None:
    """Trailing slash on a bare subdomain is removed after prepending ``https://``."""

    result = _resolve_base_url("jobs-dollargeneral.icims.com/")

    assert result == DOLLAR_GENERAL_BASE


def test_resolve_base_url_strips_trailing_slash_from_full_https_url() -> None:
    """Trailing slash on a full HTTPS URL is stripped on passthrough."""

    result = _resolve_base_url("https://uscareers-nyu.icims.com/")

    assert result == "https://uscareers-nyu.icims.com"


def test_resolve_base_url_http_prefix_passes_through() -> None:
    """A full ``http://`` URL is passed through unchanged (not upgraded to https)."""

    result = _resolve_base_url("http://jobs.icims.com")

    assert result == "http://jobs.icims.com"


def test_resolve_base_url_careers_prefix_bare_subdomain() -> None:
    """``careers-`` prefix is treated as a bare subdomain and gets ``https://``."""

    result = _resolve_base_url("careers-phc.icims.com")

    assert result == "https://careers-phc.icims.com"


# ---------------------------------------------------------------------------
# Source name
# ---------------------------------------------------------------------------


def test_get_source_name_normalizes_spaces_and_case() -> None:
    """Company name with spaces and mixed case maps to snake_case source key."""

    fetcher = _make_icims(company_name="Dollar General")

    assert fetcher.get_source_name() == "icims_dollar_general"


def test_get_source_name_preserves_non_space_punctuation() -> None:
    """Punctuation other than spaces is preserved, not stripped."""

    fetcher = _make_icims(company_name="AT&T")

    assert fetcher.get_source_name() == "icims_at&t"


def test_get_source_name_single_word_company() -> None:
    """Single-word company name produces no extra underscores."""

    fetcher = _make_icims(company_name="Amazon")

    assert fetcher.get_source_name() == "icims_amazon"


def test_get_source_name_already_lowercase_company() -> None:
    """Already-lowercase name with a space still maps correctly."""

    fetcher = _make_icims(company_name="acme corp")

    assert fetcher.get_source_name() == "icims_acme_corp"


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------


def test_parse_page_happy_path_returns_three_jobs() -> None:
    """Three valid anchors in the fixture produce three normalized postings."""

    fetcher = _make_icims()
    html_text = _load_fixture("icims_listing_page_0.html")

    jobs = fetcher._parse_page(html_text)

    assert len(jobs) == 3
    titles = {j.title for j in jobs}
    assert "Store Manager" in titles
    assert "Cashier" in titles
    assert "Logistics Specialist" in titles
    assert all(j.company == "Dollar General" for j in jobs)
    assert all(j.location is None for j in jobs)
    assert all(j.description == "" for j in jobs)
    assert all(j.source_url.startswith(DOLLAR_GENERAL_BASE) for j in jobs)


def test_parse_page_deduplicates_same_id_within_page() -> None:
    """Two anchors sharing the same job ID produce only one posting."""

    fetcher = _make_icims()
    html_text = """
    <a href="https://jobs-dollargeneral.icims.com/jobs/99999/manager/job" class="iCIMS_Anchor">
      <h3>Manager</h3>
    </a>
    <a href="https://jobs-dollargeneral.icims.com/jobs/99999/manager/job?in_iframe=1" class="iCIMS_Anchor">
      <h3>Manager</h3>
    </a>
    """

    jobs = fetcher._parse_page(html_text)

    assert len(jobs) == 1
    assert jobs[0].title == "Manager"


def test_parse_page_skips_anchor_without_h3() -> None:
    """An anchor missing the ``<h3>`` title element is silently skipped."""

    fetcher = _make_icims()
    html_text = """
    <a href="https://jobs-dollargeneral.icims.com/jobs/11111/role/job" class="iCIMS_Anchor">
      <p>No H3 here</p>
    </a>
    <a href="https://jobs-dollargeneral.icims.com/jobs/22222/cashier/job" class="iCIMS_Anchor">
      <h3>Cashier</h3>
    </a>
    """

    jobs = fetcher._parse_page(html_text)

    assert len(jobs) == 1
    assert jobs[0].title == "Cashier"


def test_parse_page_empty_html_returns_empty_list() -> None:
    """Page with no iCIMS anchors returns an empty list without error."""

    fetcher = _make_icims()
    html_text = _load_fixture("icims_listing_empty.html")

    jobs = fetcher._parse_page(html_text)

    assert jobs == []


def test_parse_page_class_before_href_returns_empty_list() -> None:
    """Known limitation: regex requires href before class; class-first yields no jobs."""

    fetcher = _make_icims()
    html_text = _load_fixture("icims_class_before_href.html")

    jobs = fetcher._parse_page(html_text)

    assert jobs == []


def test_parse_page_raw_data_contains_ats_id() -> None:
    """Each posting carries the numeric job ID in ``raw_data["ats_id"]``."""

    fetcher = _make_icims()
    html_text = _load_fixture("icims_listing_page_0.html")

    jobs = fetcher._parse_page(html_text)

    assert all("ats_id" in j.raw_data for j in jobs)
    assert all(j.raw_data["ats_id"].isdigit() for j in jobs)  # type: ignore[union-attr]


def test_parse_page_raw_data_contains_base_url() -> None:
    """Each posting carries the fetcher's base URL in ``raw_data["base_url"]``."""

    fetcher = _make_icims()
    html_text = _load_fixture("icims_listing_page_0.html")

    jobs = fetcher._parse_page(html_text)

    assert all(j.raw_data["base_url"] == DOLLAR_GENERAL_BASE for j in jobs)


def test_parse_page_source_url_is_unescaped_href() -> None:
    """HTML entities in the href attribute are unescaped in ``source_url``."""

    fetcher = _make_icims()
    html_text = (
        '<a href="https://jobs-dollargeneral.icims.com/jobs/33333/role/job'
        '?foo=1&amp;bar=2" class="iCIMS_Anchor"><h3>Role</h3></a>'
    )

    jobs = fetcher._parse_page(html_text)

    assert len(jobs) == 1
    assert "&amp;" not in jobs[0].source_url
    assert "foo=1&bar=2" in jobs[0].source_url


def test_parse_page_location_is_none() -> None:
    """iCIMS listing pages do not provide location — field is always ``None``."""

    fetcher = _make_icims()
    html_text = _load_fixture("icims_listing_page_0.html")

    jobs = fetcher._parse_page(html_text)

    assert all(j.location is None for j in jobs)


def test_parse_page_description_is_empty_string() -> None:
    """iCIMS listing pages do not provide description — field is always ``""``."""

    fetcher = _make_icims()
    html_text = _load_fixture("icims_listing_page_0.html")

    jobs = fetcher._parse_page(html_text)

    assert all(j.description == "" for j in jobs)


def test_parse_page_posted_date_is_none() -> None:
    """iCIMS listing pages do not provide a posted date — field is always ``None``."""

    fetcher = _make_icims()
    html_text = _load_fixture("icims_listing_page_0.html")

    jobs = fetcher._parse_page(html_text)

    assert all(j.posted_date is None for j in jobs)


def test_parse_page_title_with_html_entities_unescaped() -> None:
    """HTML entities inside the ``<h3>`` title are unescaped in the posting title."""

    fetcher = _make_icims()
    html_text = (
        '<a href="https://jobs-dollargeneral.icims.com/jobs/44444/role/job"'
        ' class="iCIMS_Anchor"><h3>Software &amp; Data Engineer</h3></a>'
    )

    jobs = fetcher._parse_page(html_text)

    assert len(jobs) == 1
    assert jobs[0].title == "Software & Data Engineer"


def test_strip_removes_tags_and_collapses_whitespace() -> None:
    """``_strip`` cleans HTML entities and tags from raw title inner HTML."""

    result = _strip("<b>Software &amp; Data</b>   Engineer")

    assert result == "Software & Data Engineer"
    assert "<b>" not in result
    assert "&amp;" not in result


def test_strip_empty_string_returns_empty_string() -> None:
    """Empty input produces an empty output without raising."""

    result = _strip("")

    assert result == ""


def test_strip_whitespace_only_returns_empty_string() -> None:
    """Input containing only whitespace is collapsed to an empty string."""

    result = _strip("   \t\n   ")

    assert result == ""


def test_strip_plain_text_with_extra_spaces_collapses_whitespace() -> None:
    """Plain text with multiple internal spaces is collapsed to single spaces."""

    result = _strip("Software   Engineer")

    assert result == "Software Engineer"


def test_strip_nested_html_tags_all_removed() -> None:
    """Nested tags are all stripped, leaving only the inner text."""

    result = _strip("<div><span><b>Senior</b> Developer</span></div>")

    assert result == "Senior Developer"


def test_strip_html_entity_lt_gt_unescaped() -> None:
    """``&lt;`` and ``&gt;`` entities are unescaped to ``<`` and ``>``."""

    result = _strip("A &lt; B &gt; C")

    assert result == "A < B > C"


def test_strip_unicode_characters_preserved() -> None:
    """Non-ASCII characters inside tags survive tag stripping intact."""

    result = _strip("<b>Ünïcödé Rôle</b>")

    assert result == "Ünïcödé Rôle"


def test_strip_tags_only_returns_empty_string() -> None:
    """Input with nothing but empty HTML tags collapses to an empty string."""

    result = _strip("<div><span></span></div>")

    assert result == ""


# ---------------------------------------------------------------------------
# _ats_id helper
# ---------------------------------------------------------------------------


def test_ats_id_returns_id_string_from_raw_data() -> None:
    """``_ats_id`` extracts the ``ats_id`` key from ``raw_data``."""

    posting = JobPosting(
        source="icims_test",
        source_url="https://jobs.icims.com/jobs/99/role/job",
        company="Test Co",
        title="Engineer",
        raw_data={"ats_id": "99"},
    )

    result = _ats_id(posting)

    assert result == "99"


def test_ats_id_falls_back_to_source_url_when_no_ats_id_key() -> None:
    """``_ats_id`` falls back to ``source_url`` when ``raw_data`` lacks ``ats_id``."""

    posting = JobPosting(
        source="icims_test",
        source_url="https://jobs.icims.com/jobs/99/role/job",
        company="Test Co",
        title="Engineer",
        raw_data={},
    )

    result = _ats_id(posting)

    assert result == "https://jobs.icims.com/jobs/99/role/job"


# ---------------------------------------------------------------------------
# End-to-end fetch via httpx.MockTransport
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_jobs_paginates_across_two_pages_and_stops() -> None:
    """Page 0 yields 3 jobs, page 1 yields 1 job, page 2 yields 0 → 4 total."""

    page_0 = _load_fixture("icims_listing_page_0.html")
    page_1 = _load_fixture("icims_listing_page_1.html")
    empty = _load_fixture("icims_listing_empty.html")
    pages_requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Route by ``pr`` query param to the correct fixture."""

        pr = request.url.params.get("pr", "0")
        pages_requested.append(pr)
        if pr == "0":
            return httpx.Response(200, text=page_0)
        if pr == "1":
            return httpx.Response(200, text=page_1)
        return httpx.Response(200, text=empty)

    fetcher = _make_icims()
    fetcher._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock):
        try:
            results = await fetcher.fetch_jobs()
        finally:
            await fetcher._client.aclose()

    assert len(results) == 4
    assert "0" in pages_requested
    assert "1" in pages_requested
    assert "2" in pages_requested


@pytest.mark.asyncio
async def test_fetch_jobs_404_returns_empty_list() -> None:
    """404 on the first page fails-soft to an empty list without raising."""

    def handler(_: httpx.Request) -> httpx.Response:
        """Return 404 for every request."""
        return httpx.Response(404)

    fetcher = _make_icims()
    fetcher._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()

    assert results == []


@pytest.mark.asyncio
async def test_fetch_jobs_429_retries_then_returns_empty() -> None:
    """429 on every attempt exhausts retries and fails-soft to an empty list."""

    def handler(_: httpx.Request) -> httpx.Response:
        """Return 429 for every request."""
        return httpx.Response(429, headers={"Retry-After": "1"})

    fetcher = _make_icims()
    fetcher._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock):
        try:
            results = await fetcher.fetch_jobs()
        finally:
            await fetcher._client.aclose()

    assert results == []


@pytest.mark.asyncio
async def test_fetch_jobs_5xx_retries_then_returns_empty() -> None:
    """503 on every attempt exhausts retries and fails-soft to an empty list."""

    def handler(_: httpx.Request) -> httpx.Response:
        """Return 503 for every request."""
        return httpx.Response(503)

    fetcher = _make_icims()
    fetcher._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock):
        try:
            results = await fetcher.fetch_jobs()
        finally:
            await fetcher._client.aclose()

    assert results == []


@pytest.mark.asyncio
async def test_fetch_jobs_transport_error_raises_fetch_error() -> None:
    """A transport-level connection error surfaces as ``FetchError``."""

    def handler(_: httpx.Request) -> httpx.Response:
        """Simulate a connection failure."""
        raise httpx.ConnectError("Connection refused")

    fetcher = _make_icims()
    fetcher._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    try:
        with pytest.raises(FetchError):
            await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()


@pytest.mark.asyncio
async def test_fetch_jobs_cross_page_dedup_prevents_duplicate_ids() -> None:
    """A job ID seen on page 0 is not re-added when it appears on page 1."""

    # Both pages return the same job ID — only one posting should result.
    duplicate_html = """
    <a href="https://jobs-dollargeneral.icims.com/jobs/77777/manager/job" class="iCIMS_Anchor">
      <h3>Manager</h3>
    </a>
    """
    empty = _load_fixture("icims_listing_empty.html")
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return httpx.Response(200, text=duplicate_html)
        return httpx.Response(200, text=empty)

    fetcher = _make_icims()
    fetcher._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock):
        try:
            results = await fetcher.fetch_jobs()
        finally:
            await fetcher._client.aclose()

    # The duplicate on page 1 causes the page-new check to fail → loop stops.
    # Only one posting from page 0 should be in results.
    assert len(results) == 1
    assert results[0].title == "Manager"


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
async def test_fetch_jobs_all_retryable_codes_exhaust_retries_and_return_empty(
    status_code: int,
) -> None:
    """All 429/5xx codes exhaust MAX_RETRIES retries and fail-soft to an empty list."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code)

    fetcher = _make_icims()
    fetcher._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    with unittest.mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock):
        try:
            results = await fetcher.fetch_jobs()
        finally:
            await fetcher._client.aclose()

    assert results == []


@pytest.mark.asyncio
async def test_fetch_jobs_unexpected_status_raises_fetch_error() -> None:
    """An unexpected HTTP status (401) that is not 200/404/429/5xx raises FetchError."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    fetcher = _make_icims()
    fetcher._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    try:
        with pytest.raises(FetchError):
            await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()


@pytest.mark.asyncio
async def test_fetch_jobs_retry_after_non_integer_uses_exponential_backoff() -> None:
    """Non-integer Retry-After header triggers exponential back-off, not header value."""

    mock_sleep = unittest.mock.AsyncMock()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "not-a-number"})

    fetcher = _make_icims()
    fetcher._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    with unittest.mock.patch("asyncio.sleep", mock_sleep):
        try:
            results = await fetcher.fetch_jobs()
        finally:
            await fetcher._client.aclose()

    assert results == []
    retry_sleep_delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert len(retry_sleep_delays) == MAX_RETRIES - 1
    assert all(d >= RETRY_BASE_DELAY for d in retry_sleep_delays)


@pytest.mark.asyncio
async def test_fetch_jobs_inter_page_sleep_not_called_after_last_page() -> None:
    """Inter-page sleep fires after productive pages but not after the stopping page."""

    page_0 = _load_fixture("icims_listing_page_0.html")
    empty = _load_fixture("icims_listing_empty.html")
    mock_sleep = unittest.mock.AsyncMock()
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(200, text=page_0)
        return httpx.Response(200, text=empty)

    fetcher = _make_icims()
    fetcher._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )

    with unittest.mock.patch("asyncio.sleep", mock_sleep):
        try:
            results = await fetcher.fetch_jobs()
        finally:
            await fetcher._client.aclose()

    assert len(results) == 3
    assert mock_sleep.call_count == 1
    assert mock_sleep.call_args_list[0].args[0] == INTER_PAGE_SLEEP


@pytest.mark.live_agent_e2e
@pytest.mark.asyncio
async def test_fetch_jobs_live_dollar_general_returns_postings() -> None:
    """Live smoke test: Dollar General iCIMS portal returns real job postings."""

    async with ICIMSFetcher(
        "Dollar General",
        "jobs-dollargeneral.icims.com",
    ) as fetcher:
        jobs = await fetcher.fetch_jobs()

    assert len(jobs) > 0
    assert all(j.title for j in jobs)
    assert all(j.source_url.startswith("https://jobs-dollargeneral.icims.com") for j in jobs)
