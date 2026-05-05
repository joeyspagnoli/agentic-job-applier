"""Validate WorkdayFetcher parsing, enrichment, and end-to-end pagination."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from src.fetchers.errors import FetchError
from src.fetchers.workday_fetcher import WorkdayFetcher


FIXTURE_DIR = Path(__file__).parent / "fixtures"

IMF_BASE_URL = "https://imf.wd5.myworkdayjobs.com/IMF"


def _make_workday(
    *,
    company_name: str = "TestCo",
    workday_url: str = "https://testco.wd1.myworkdayjobs.com/Careers",
    fetch_descriptions: bool = True,
) -> WorkdayFetcher:
    """Build a fetcher with no HTTP setup for unit tests.

    Purpose:
        Provide a minimal Workday fetcher whose static helpers and parse methods
        can be exercised without spinning up an HTTP client.
    Args:
        company_name: Name passed to the constructor.
        workday_url: Public Workday URL passed to the constructor.
        fetch_descriptions: Toggle that controls detail enrichment in fetch.
    Output:
        Returns a `WorkdayFetcher` instance.
    """

    return WorkdayFetcher(
        company_name=company_name,
        workday_url=workday_url,
        fetch_descriptions=fetch_descriptions,
    )


def _load_fixture(name: str) -> dict:
    """Load a JSON fixture from the shared fixtures directory.

    Purpose:
        Centralize fixture loading so tests stay focused on behavior assertions.
    Args:
        name: File name within `tests/fixtures/`.
    Output:
        Returns the parsed JSON object.
    """

    path = FIXTURE_DIR / name
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------


def test_workday_parse_board_url_extracts_components() -> None:
    """Verify `_parse_board_url` extracts origin, tenant, and site cleanly."""

    origin, tenant, site = WorkdayFetcher._parse_board_url(
        "https://pfizer.wd1.myworkdayjobs.com/PfizerCareers"
    )

    assert origin == "https://pfizer.wd1.myworkdayjobs.com"
    assert tenant == "pfizer"
    assert site == "PfizerCareers"


def test_workday_parse_board_url_skips_locale_segment() -> None:
    """Verify locale path segments like `/en-US/` are ignored when picking site."""

    _, _, site = WorkdayFetcher._parse_board_url(
        "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite"
    )

    assert site == "NVIDIAExternalCareerSite"


def test_workday_parse_board_url_defaults_site_when_path_empty() -> None:
    """Verify the default `External` site is used when the path has no segments."""

    _, _, site = WorkdayFetcher._parse_board_url(
        "https://example.wd1.myworkdayjobs.com/"
    )

    assert site == "External"


# ---------------------------------------------------------------------------
# Listing parse
# ---------------------------------------------------------------------------


def test_workday_parse_listing_job_maps_fields_correctly() -> None:
    """Verify listing entries are normalized into JobPosting with expected fields."""

    fetcher = _make_workday()
    raw = {
        "title": "Senior Data Engineer",
        "externalPath": "/job/Remote/Senior-Data-Engineer_R-001",
        "locationsText": "Remote - USA",
        "postedOn": "Posted 5 Days Ago",
    }

    posting = fetcher._parse_listing_job(raw)

    assert posting.title == "Senior Data Engineer"
    assert posting.location == "Remote - USA"
    assert posting.posted_date == "Posted 5 Days Ago"
    assert posting.source_url.endswith("/Senior-Data-Engineer_R-001")
    assert posting.company == "TestCo"
    assert posting.source.startswith("workday_")


# ---------------------------------------------------------------------------
# Detail enrichment
# ---------------------------------------------------------------------------


def test_workday_enrich_with_detail_overrides_description_and_date() -> None:
    """Verify detail enrichment swaps in cleaned description and ISO start date."""

    fetcher = _make_workday()
    base = fetcher._parse_listing_job(
        {
            "title": "Economist",
            "externalPath": "/job/USA/Economist_R-1",
            "locationsText": "USA, Washington DC",
            "postedOn": "Posted Today",
        }
    )
    detail = {
        "jobPostingInfo": {
            "title": "Economist (Senior)",
            "jobDescription": "<p>Lead <b>economic</b> analysis.</p>",
            "externalUrl": "https://example.wd1.myworkdayjobs.com/Careers/job/Economist_R-1",
            "startDate": "2026-04-29",
        }
    }

    enriched = fetcher._enrich_with_detail(base, detail)

    assert enriched.title == "Economist (Senior)"
    assert enriched.description == "Lead economic analysis."
    assert enriched.posted_date == "2026-04-29"
    assert enriched.source_url.endswith("/Economist_R-1")
    assert "<b>" not in enriched.description


# ---------------------------------------------------------------------------
# HTML cleanup
# ---------------------------------------------------------------------------


def test_workday_clean_html_strips_tags_and_collapses_whitespace() -> None:
    """Verify `_clean_html` removes tags and collapses redundant whitespace."""

    cleaned = WorkdayFetcher._clean_html(
        "<p>Hello   <b>world</b></p>\n<ul><li>One</li><li>Two</li></ul>"
    )

    assert cleaned == "Hello world One Two"


def test_workday_clean_html_handles_empty_input() -> None:
    """Verify `_clean_html` returns an empty string for empty input."""

    assert WorkdayFetcher._clean_html("") == ""


# ---------------------------------------------------------------------------
# Cloudflare block detection
# ---------------------------------------------------------------------------


def test_workday_is_blocked_response_detects_cloudflare_html() -> None:
    """Verify Cloudflare interstitial HTML triggers the block heuristic."""

    body = "<!DOCTYPE html><html><head><title>Attention Required! | Cloudflare</title></head></html>"
    assert WorkdayFetcher._is_blocked_response(403, body) is True


def test_workday_is_blocked_response_returns_false_for_json_body() -> None:
    """Verify normal JSON bodies are not flagged as gated responses."""

    assert WorkdayFetcher._is_blocked_response(200, '{"jobPostings": []}') is False


# ---------------------------------------------------------------------------
# End-to-end fetch via httpx.MockTransport
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workday_fetcher_paginates_and_enriches_via_mock_transport() -> None:
    """Drive the full fetch path through canned IMF fixtures via MockTransport."""

    listing = _load_fixture("workday_imf_listing_page1.json")
    empty = _load_fixture("workday_imf_listing_empty.json")
    detail = _load_fixture("workday_imf_detail_economist.json")

    listing_calls: list[int] = []
    detail_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Route mock requests to listing or detail fixtures."""

        path = request.url.path
        if path.endswith("/jobs"):
            listing_calls.append(len(listing_calls))
            payload = listing if len(listing_calls) == 1 else empty
            return httpx.Response(200, json=payload)
        if "/job/" in path:
            detail_calls.append(path)
            return httpx.Response(200, json=detail)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    fetcher = _make_workday(
        company_name="IMF",
        workday_url=IMF_BASE_URL,
    )
    fetcher._client = httpx.AsyncClient(transport=transport)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()

    assert len(results) == 3
    assert results[0].title == "Economist/Sr. Economist (Contractual) - ICDCI"
    assert results[0].posted_date == "2026-04-29"
    assert "Economist" in results[0].description
    assert results[2].is_remote is True
    assert len(detail_calls) == 3


@pytest.mark.asyncio
async def test_workday_fetcher_returns_empty_on_cloudflare_block() -> None:
    """Verify a Cloudflare 403 interstitial fails-soft to an empty list."""

    def handler(_: httpx.Request) -> httpx.Response:
        """Return a Cloudflare-style HTML 403 for every request."""

        return httpx.Response(
            403,
            text="<!DOCTYPE html><html><head><title>Attention Required | Cloudflare</title></head></html>",
            headers={"content-type": "text/html"},
        )

    transport = httpx.MockTransport(handler)
    fetcher = _make_workday()
    fetcher._client = httpx.AsyncClient(transport=transport)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()

    assert results == []


@pytest.mark.asyncio
async def test_workday_fetcher_retries_on_404_then_returns_empty() -> None:
    """Verify a 404 on `/jobs` triggers a `/jobs/search` retry."""

    paths_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return 404 for both listing endpoints to exhaust the retry path."""

        paths_seen.append(request.url.path)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    fetcher = _make_workday()
    fetcher._client = httpx.AsyncClient(transport=transport)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()

    assert results == []
    assert any(path.endswith("/jobs") for path in paths_seen)
    assert any(path.endswith("/jobs/search") for path in paths_seen)


@pytest.mark.asyncio
async def test_workday_fetcher_raises_fetch_error_on_unexpected_500() -> None:
    """Verify unexpected 5xx responses surface as `FetchError` to the orchestrator."""

    def handler(_: httpx.Request) -> httpx.Response:
        """Return a deterministic 500 for every request."""

        return httpx.Response(500, json={"error": "boom"})

    transport = httpx.MockTransport(handler)
    fetcher = _make_workday()
    fetcher._client = httpx.AsyncClient(transport=transport)

    try:
        with pytest.raises(FetchError):
            await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()


@pytest.mark.asyncio
async def test_workday_fetcher_skips_detail_when_disabled() -> None:
    """Verify `fetch_descriptions=False` skips the detail GET path entirely."""

    listing = _load_fixture("workday_imf_listing_page1.json")
    empty = _load_fixture("workday_imf_listing_empty.json")

    listing_calls: list[int] = []
    detail_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Track listing vs. detail call distribution."""

        path = request.url.path
        if path.endswith("/jobs"):
            listing_calls.append(len(listing_calls))
            payload = listing if len(listing_calls) == 1 else empty
            return httpx.Response(200, json=payload)
        detail_calls.append(path)
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    fetcher = _make_workday(
        company_name="IMF",
        workday_url=IMF_BASE_URL,
        fetch_descriptions=False,
    )
    fetcher._client = httpx.AsyncClient(transport=transport)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()

    assert len(results) == 3
    assert detail_calls == []
    assert results[0].posted_date == "Posted Today"
