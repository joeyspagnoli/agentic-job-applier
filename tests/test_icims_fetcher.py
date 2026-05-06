"""Validate ICIMSFetcher parsing, pagination, and error-handling behavior."""

from __future__ import annotations

import unittest.mock
from pathlib import Path

import httpx
import pytest

from src.fetchers.errors import FetchError
from src.fetchers.icims_fetcher import ICIMSFetcher, _resolve_base_url, _strip


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


# ---------------------------------------------------------------------------
# Source name
# ---------------------------------------------------------------------------


def test_get_source_name_normalizes_spaces_and_case() -> None:
    """Company name with spaces and mixed case maps to snake_case source key."""

    fetcher = _make_icims(company_name="Dollar General")

    assert fetcher.get_source_name() == "icims_dollar_general"


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


def test_strip_removes_tags_and_collapses_whitespace() -> None:
    """``_strip`` cleans HTML entities and tags from raw title inner HTML."""

    result = _strip("<b>Software &amp; Data</b>   Engineer")

    assert result == "Software & Data Engineer"
    assert "<b>" not in result
    assert "&amp;" not in result


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
