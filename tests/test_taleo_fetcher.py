"""Validate TaleoFetcher parsing, location handling, portal discovery, and pagination."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from src.fetchers.errors import FetchError
from src.fetchers.taleo_fetcher import TaleoFetcher, _normalize_company_name


FIXTURE_DIR = Path(__file__).parent / "fixtures"

WIPO_TENANT = "wipo"
WIPO_SECTION = "wp_2"
WIPO_PORTAL = "101430233"


def _make_taleo(
    *,
    company_name: str = "TestCo",
    tenant_id: str = "testco",
    career_section: str = "ex",
    portal_id: str | None = None,
) -> TaleoFetcher:
    """Build a TaleoFetcher with no HTTP client for unit tests.

    Purpose:
        Provide a minimal fetcher whose pure helper methods can be exercised
        without touching the network.
    Args:
        company_name: Company name passed to the constructor.
        tenant_id: Taleo tenant subdomain.
        career_section: Taleo career section ID.
        portal_id: Optional pre-discovered portal ID.
    Output:
        Returns a ``TaleoFetcher`` instance with ``_client`` set to ``None``.
    """
    return TaleoFetcher(
        company_name=company_name,
        tenant_id=tenant_id,
        career_section=career_section,
        portal_id=portal_id,
    )


def _load_fixture_json(name: str) -> dict:
    """Load a JSON fixture from the shared fixtures directory.

    Purpose:
        Centralise fixture loading so tests stay focused on behaviour.
    Args:
        name: File name within ``tests/fixtures/``.
    Output:
        Returns the parsed JSON object.
    """
    return json.loads((FIXTURE_DIR / name).read_text())


def _load_fixture_text(name: str) -> str:
    """Load a text fixture from the shared fixtures directory.

    Purpose:
        Centralise fixture loading for non-JSON fixture files.
    Args:
        name: File name within ``tests/fixtures/``.
    Output:
        Returns the raw file contents as a string.
    """
    return (FIXTURE_DIR / name).read_text()


# ---------------------------------------------------------------------------
# Source name normalisation
# ---------------------------------------------------------------------------


def test_get_source_name_simple_company() -> None:
    """Verify simple company names produce the expected snake_case source label."""

    fetcher = _make_taleo(company_name="Citigroup")

    assert fetcher.get_source_name() == "taleo_citigroup"


def test_get_source_name_normalizes_special_chars() -> None:
    """Verify ``&`` expands to ``and`` and punctuation is stripped."""

    assert _normalize_company_name("Johnson & Johnson") == "johnson_and_johnson"


def test_get_source_name_multi_word_with_punctuation() -> None:
    """Verify spaces become underscores and trailing parens are stripped."""

    assert _normalize_company_name("Burns & McDonnell (External)") == "burns_and_mcdonnell_external"


def test_get_source_name_format() -> None:
    """Verify the full source name follows the ``taleo_`` prefix convention."""

    fetcher = _make_taleo(company_name="Johnson & Johnson")

    assert fetcher.get_source_name() == "taleo_johnson_and_johnson"


# ---------------------------------------------------------------------------
# Location parsing
# ---------------------------------------------------------------------------


def test_parse_location_extracts_city_state_country() -> None:
    """Verify JSON location string is parsed into ``City, State, Country``."""

    fetcher = _make_taleo()
    raw = '{"city":"Seattle","state":"WA","country":"United States"}'

    result = fetcher._parse_location(raw)

    assert result == "Seattle, WA, United States"


def test_parse_location_omits_empty_state() -> None:
    """Verify empty state field is omitted from the assembled location string."""

    fetcher = _make_taleo()
    raw = '{"city":"Geneva","state":"","country":"Switzerland"}'

    result = fetcher._parse_location(raw)

    assert result == "Geneva, Switzerland"


def test_parse_location_falls_back_on_bad_json() -> None:
    """Verify malformed JSON returns the raw string as a safe fallback."""

    fetcher = _make_taleo()
    raw = "not valid json"

    result = fetcher._parse_location(raw)

    assert result == "not valid json"


def test_parse_location_returns_none_for_empty_string() -> None:
    """Verify an empty raw value returns ``None``."""

    fetcher = _make_taleo()

    assert fetcher._parse_location("") is None


# ---------------------------------------------------------------------------
# Job parsing
# ---------------------------------------------------------------------------


def test_parse_job_maps_column_fields() -> None:
    """Verify ``column[0]/[3]/[5]`` map to title, location, and posted_date."""

    fetcher = _make_taleo(company_name="WIPO", tenant_id="wipo", career_section="wp_2")
    raw = {
        "contestNo": "99999",
        "column": [
            "Software Engineer",
            "",
            "WIPO",
            '{"city":"Geneva","state":"","country":"Switzerland"}',
            "IT",
            "2026-04-28",
        ],
    }

    posting = fetcher._parse_job(raw, contest_no="99999", description="Test description.")

    assert posting.title == "Software Engineer"
    assert posting.location == "Geneva, Switzerland"
    assert posting.posted_date == "2026-04-28"
    assert posting.description == "Test description."
    assert posting.company == "WIPO"
    assert posting.source == "taleo_wipo"
    assert "job=99999" in posting.source_url


def test_parse_job_handles_short_column_array() -> None:
    """Verify bounds-safe column access when the array is shorter than expected."""

    fetcher = _make_taleo()
    raw: dict = {"contestNo": "55555", "column": ["Only Title"]}

    posting = fetcher._parse_job(raw, contest_no="55555")

    assert posting.title == "Only Title"
    assert posting.location is None
    assert posting.posted_date is None


def test_parse_job_falls_back_title_when_column_empty() -> None:
    """Verify ``Unknown Title`` is used when column[0] is absent."""

    fetcher = _make_taleo()
    raw: dict = {"contestNo": "00000", "column": []}

    posting = fetcher._parse_job(raw, contest_no="00000")

    assert posting.title == "Unknown Title"


# ---------------------------------------------------------------------------
# Portal ID discovery
# ---------------------------------------------------------------------------


def test_discover_portal_id_extracts_from_html() -> None:
    """Verify the portal ID regex extracts a numeric ID from typical Taleo HTML."""

    html = """
    <html><body>
    <script>
      var portalId = '101430233';
      Taleo.init({portalId: '101430233', lang: 'en'});
    </script>
    </body></html>
    """
    from src.fetchers.taleo_fetcher import _PORTAL_ID_RE

    m = _PORTAL_ID_RE.search(html)

    assert m is not None
    assert m.group(1) == "101430233"


def test_discover_portal_id_handles_assignment_format() -> None:
    """Verify the regex also handles ``portalId=12345`` assignment syntax."""

    html = "setupPortal(portalId=9876543)"
    from src.fetchers.taleo_fetcher import _PORTAL_ID_RE

    m = _PORTAL_ID_RE.search(html)

    assert m is not None
    assert m.group(1) == "9876543"


# ---------------------------------------------------------------------------
# End-to-end pagination via httpx.MockTransport
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pagination_stops_at_total_count() -> None:
    """Verify the fetch loop exits when cumulative jobs equal totalCount."""

    page1 = _load_fixture_json("taleo_wipo_page1.json")
    page2 = _load_fixture_json("taleo_wipo_page2.json")
    detail_html = _load_fixture_text("taleo_wipo_detail.html")

    request_count: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Route mock requests to listing fixtures or a detail HTML response."""

        path = request.url.path
        if "searchjobs" in path:
            request_count.append(1)
            body = json.loads(request.content)
            page_no = body.get("pageNo", 1)
            if page_no == 1:
                return httpx.Response(200, json=page1)
            return httpx.Response(200, json=page2)
        if "jobdetail" in path:
            return httpx.Response(200, text=detail_html)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    fetcher = _make_taleo(
        company_name="WIPO",
        tenant_id=WIPO_TENANT,
        career_section=WIPO_SECTION,
        portal_id=WIPO_PORTAL,
    )
    fetcher._client = httpx.AsyncClient(transport=transport)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()

    assert len(results) == 7
    assert results[0].title == "Software Engineer"
    assert results[0].company == "WIPO"
    assert results[0].source == "taleo_wipo"
    assert len(request_count) == 2


@pytest.mark.asyncio
async def test_pagination_stops_on_empty_list() -> None:
    """Verify the fetch loop exits immediately when requisitionList is empty."""

    empty_response = {
        "requisitionList": [],
        "pagingData": {"totalCount": 0, "pageSize": 25, "currentPageNumber": 1},
    }

    def handler(_: httpx.Request) -> httpx.Response:
        """Return an empty job list for every listing request."""
        return httpx.Response(200, json=empty_response)

    transport = httpx.MockTransport(handler)
    fetcher = _make_taleo(portal_id="12345")
    fetcher._client = httpx.AsyncClient(transport=transport)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()

    assert results == []


@pytest.mark.asyncio
async def test_detail_fetch_failure_returns_empty_description() -> None:
    """Verify a 404 detail response yields ``description=""`` without raising."""

    listing_response = {
        "requisitionList": [
            {"contestNo": "99", "column": ["Test Job", "", "", "", "", "2026-01-01"]}
        ],
        "pagingData": {"totalCount": 1, "pageSize": 25, "currentPageNumber": 1},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a valid listing but 404 on every detail request."""

        if "searchjobs" in request.url.path:
            return httpx.Response(200, json=listing_response)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    fetcher = _make_taleo(portal_id="12345")
    fetcher._client = httpx.AsyncClient(transport=transport)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()

    assert len(results) == 1
    assert results[0].description == ""
    assert results[0].title == "Test Job"


@pytest.mark.asyncio
async def test_non_json_response_raises_fetch_error() -> None:
    """Verify a non-JSON search response raises FetchError rather than crashing."""

    def handler(_: httpx.Request) -> httpx.Response:
        """Return maintenance HTML instead of JSON."""

        return httpx.Response(
            200,
            text="<html><body>System under maintenance</body></html>",
            headers={"content-type": "text/html"},
        )

    transport = httpx.MockTransport(handler)
    fetcher = _make_taleo(portal_id="12345")
    fetcher._client = httpx.AsyncClient(transport=transport)

    with pytest.raises(FetchError):
        try:
            await fetcher.fetch_jobs()
        finally:
            await fetcher._client.aclose()


@pytest.mark.asyncio
async def test_non_200_response_raises_fetch_error() -> None:
    """Verify an HTTP 500 from the search endpoint raises FetchError."""

    def handler(_: httpx.Request) -> httpx.Response:
        """Return HTTP 500 for every request."""

        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    fetcher = _make_taleo(portal_id="12345")
    fetcher._client = httpx.AsyncClient(transport=transport)

    with pytest.raises(FetchError):
        try:
            await fetcher.fetch_jobs()
        finally:
            await fetcher._client.aclose()
