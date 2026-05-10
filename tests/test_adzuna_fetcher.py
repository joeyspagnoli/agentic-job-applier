"""Unit tests for ``AdzunaFetcher`` pagination, error handling, and parsing.

Purpose:
    Drive the Adzuna fetcher through ``httpx.MockTransport`` so the entire
    fetch path — pagination cap, short-page short-circuit, soft-fail on
    auth/rate limits, optional location parameter, and malformed payloads —
    is exercised without any network access.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from src.fetchers.adzuna_fetcher import AdzunaFetcher


# Cap and per-page values the suite asserts pagination math against.
PAGE_SIZE = 50
CAP = 80
TWO_PAGES_OF_RESULTS = 100


def _make_fetcher(
    *,
    location: str | None = None,
    results_wanted: int = 50,
    results_per_page: int = PAGE_SIZE,
    country: str = "us",
) -> AdzunaFetcher:
    """Construct an AdzunaFetcher without performing any I/O.

    Purpose:
        Provide a minimal fetcher whose ``_client`` slot can be wired to a
        ``MockTransport`` for hermetic tests.
    Args:
        location: Optional ``where`` value forwarded to Adzuna.
        results_wanted: Cap on total normalized postings.
        results_per_page: Per-page request size (clamped by the constructor).
        country: Two-letter country code used in the request path.
    Output:
        Returns a constructed ``AdzunaFetcher`` instance.
    """

    return AdzunaFetcher(
        app_id="test-id",
        app_key="test-key",
        search_term="software engineer",
        location=location,
        country=country,
        results_per_page=results_per_page,
        results_wanted=results_wanted,
    )


def _result(idx: int) -> dict[str, Any]:
    """Build one well-formed Adzuna search-result dict.

    Purpose:
        Provide a deterministic minimal result so pagination tests can count
        produced postings without worrying about parser-side filtering.
    Args:
        idx: Numeric ID used to make the title and URL unique.
    Output:
        Returns a dict shaped like an Adzuna API result.
    """

    return {
        "title": f"Software Engineer {idx}",
        "redirect_url": f"https://example.com/jobs/{idx}",
        "company": {"display_name": "Example Co"},
        "location": {"display_name": "Remote", "area": ["US", "Remote"]},
        "description": "We are hiring.",
        "salary_min": 100_000,
        "salary_max": 150_000,
        "created": "2026-05-01T00:00:00Z",
    }


def _attach_transport(
    fetcher: AdzunaFetcher,
    handler: Any,
) -> httpx.AsyncClient:
    """Replace the fetcher's HTTP client with a ``MockTransport``-backed one.

    Purpose:
        Centralize the boilerplate of swapping the production async client for
        a hermetic transport so each test reads as Arrange/Act/Assert.
    Args:
        fetcher: The fetcher whose ``_client`` slot is being overridden.
        handler: ``httpx`` request handler used by ``MockTransport``.
    Output:
        Returns the constructed ``httpx.AsyncClient`` so callers can close it.
    """

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    fetcher._client = client
    return client


# ---------------------------------------------------------------------------
# Pagination behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_jobs_stops_at_results_wanted_cap() -> None:
    """Verify pagination stops once ``results_wanted`` postings are collected.

    Purpose:
        With ``results_wanted=80`` and 50 results per page, the fetcher must
        request a second page, stop mid-page after 30 more results, and never
        request a third page.
    """

    pages_seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.path.rsplit("/", 1)[-1])
        pages_seen.append(page)
        return httpx.Response(200, json={"results": [_result(i) for i in range(PAGE_SIZE)]})

    fetcher = _make_fetcher(results_wanted=CAP)
    client = _attach_transport(fetcher, handler)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await client.aclose()

    assert len(results) == CAP
    assert pages_seen == [1, 2]


@pytest.mark.asyncio
async def test_fetch_jobs_stops_on_short_page() -> None:
    """Verify pagination terminates when a page returns fewer than the page size.

    Purpose:
        Adzuna returns at most ``results_per_page`` rows per page, so a short
        page means the result set is exhausted and pagination must stop even
        though the cap has not been reached.
    """

    pages_seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.path.rsplit("/", 1)[-1])
        pages_seen.append(page)
        # First page is short (3 < PAGE_SIZE) so the loop must end here.
        return httpx.Response(200, json={"results": [_result(i) for i in range(3)]})

    fetcher = _make_fetcher(results_wanted=200)
    client = _attach_transport(fetcher, handler)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await client.aclose()

    assert len(results) == 3
    assert pages_seen == [1]


@pytest.mark.asyncio
async def test_fetch_jobs_stops_on_empty_first_page() -> None:
    """Verify an empty results array breaks the pagination loop immediately.

    Purpose:
        An empty page is treated as an authoritative end-of-results signal and
        must not be followed by another HTTP call.
    """

    pages_seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.path.rsplit("/", 1)[-1])
        pages_seen.append(page)
        return httpx.Response(200, json={"results": []})

    fetcher = _make_fetcher(results_wanted=200)
    client = _attach_transport(fetcher, handler)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await client.aclose()

    assert results == []
    assert pages_seen == [1]


# ---------------------------------------------------------------------------
# Soft-fail HTTP error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_jobs_returns_partial_on_401() -> None:
    """Verify a 401 mid-pagination returns the postings collected so far.

    Purpose:
        The orchestrator treats Adzuna 401 as a soft failure (likely bad keys)
        so the fetcher must surface whatever it had before the auth break
        rather than raising.
    """

    call_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.path.rsplit("/", 1)[-1])
        call_pages.append(page)
        if page == 1:
            return httpx.Response(200, json={"results": [_result(i) for i in range(PAGE_SIZE)]})
        return httpx.Response(401, json={"error": "auth"})

    fetcher = _make_fetcher(results_wanted=TWO_PAGES_OF_RESULTS)
    client = _attach_transport(fetcher, handler)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await client.aclose()

    assert len(results) == PAGE_SIZE
    assert call_pages == [1, 2]


@pytest.mark.asyncio
async def test_fetch_jobs_returns_partial_on_429() -> None:
    """Verify a 429 mid-pagination returns the postings collected so far.

    Purpose:
        Rate limits are transient; the fetcher must hand back any results it
        already has so the orchestrator records a non-zero crawl rather than
        propagating the failure.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.path.rsplit("/", 1)[-1])
        if page == 1:
            return httpx.Response(200, json={"results": [_result(i) for i in range(PAGE_SIZE)]})
        return httpx.Response(429, json={"error": "rate_limited"})

    fetcher = _make_fetcher(results_wanted=TWO_PAGES_OF_RESULTS)
    client = _attach_transport(fetcher, handler)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await client.aclose()

    assert len(results) == PAGE_SIZE


@pytest.mark.asyncio
async def test_fetch_jobs_raises_on_non_softfail_5xx() -> None:
    """Verify HTTP errors outside 401/429 propagate as ``HTTPStatusError``.

    Purpose:
        A 500 from Adzuna is not a soft-fail case — the orchestrator records
        the FAILED crawl row from the raised exception.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    fetcher = _make_fetcher(results_wanted=10)
    client = _attach_transport(fetcher, handler)

    try:
        with pytest.raises(httpx.HTTPStatusError):
            await fetcher.fetch_jobs()
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Query-string round-tripping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_jobs_forwards_location_as_where_param() -> None:
    """Verify the ``location`` argument round-trips into the ``where`` query param.

    Purpose:
        The orchestrator passes per-search location strings through; missing
        them on the request would silently widen every search to the whole
        country.
    """

    captured_params: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_params.append(dict(request.url.params))
        return httpx.Response(200, json={"results": []})

    fetcher = _make_fetcher(location="New York", results_wanted=10)
    client = _attach_transport(fetcher, handler)

    try:
        await fetcher.fetch_jobs()
    finally:
        await client.aclose()

    assert captured_params, "expected at least one Adzuna request"
    params = captured_params[0]
    assert params["where"] == "New York"
    assert params["what"] == "software engineer"
    assert params["app_id"] == "test-id"
    assert params["app_key"] == "test-key"


@pytest.mark.asyncio
async def test_fetch_jobs_omits_where_param_when_location_unset() -> None:
    """Verify the ``where`` param is omitted entirely when no location is given.

    Purpose:
        Sending an empty ``where`` value would change Adzuna's interpretation
        compared to omitting the parameter; the fetcher's contract is the
        latter.
    """

    captured_params: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_params.append(dict(request.url.params))
        return httpx.Response(200, json={"results": []})

    fetcher = _make_fetcher(location=None, results_wanted=10)
    client = _attach_transport(fetcher, handler)

    try:
        await fetcher.fetch_jobs()
    finally:
        await client.aclose()

    assert "where" not in captured_params[0]


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_jobs_skips_results_missing_redirect_url() -> None:
    """Verify results without a redirect URL are dropped, not raised on.

    Purpose:
        Adzuna occasionally returns rows missing key fields; the fetcher must
        skip them silently so a single bad row does not blow up a whole crawl.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        good = _result(1)
        bad_no_url = {**_result(2), "redirect_url": ""}
        bad_no_title = {**_result(3), "title": ""}
        return httpx.Response(200, json={"results": [good, bad_no_url, bad_no_title]})

    fetcher = _make_fetcher(results_wanted=50)
    client = _attach_transport(fetcher, handler)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await client.aclose()

    assert len(results) == 1
    assert results[0].source_url == "https://example.com/jobs/1"


@pytest.mark.asyncio
async def test_fetch_jobs_skips_malformed_salary_without_crashing() -> None:
    """Verify non-numeric ``salary_min``/``salary_max`` does not raise.

    Purpose:
        Adzuna responses occasionally carry strings like ``"on request"`` in
        salary fields; those rows must still produce a JobPosting with the
        salary set to ``None``.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        item = {**_result(1), "salary_min": "negotiable", "salary_max": "tbd"}
        return httpx.Response(200, json={"results": [item]})

    fetcher = _make_fetcher(results_wanted=10)
    client = _attach_transport(fetcher, handler)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await client.aclose()

    assert len(results) == 1
    assert results[0].salary_min is None
    assert results[0].salary_max is None
    assert results[0].salary_source == "not_listed"


@pytest.mark.asyncio
async def test_fetch_jobs_parses_numeric_salary_into_cents() -> None:
    """Verify Adzuna salary dollars are stored as integer cents.

    Purpose:
        Downstream filters compare against cents; a regression that stored
        dollars would silently break every salary filter.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [_result(1)]})

    fetcher = _make_fetcher(results_wanted=10)
    client = _attach_transport(fetcher, handler)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await client.aclose()

    assert results[0].salary_min == 100_000 * 100
    assert results[0].salary_max == 150_000 * 100
    assert results[0].salary_source == "direct"


@pytest.mark.asyncio
async def test_fetch_jobs_falls_back_to_unknown_when_company_missing() -> None:
    """Verify a missing ``company.display_name`` is replaced by ``"Unknown"``.

    Purpose:
        The pipeline requires a non-empty ``company`` string to dedupe and
        display jobs; the fetcher's contract substitutes a placeholder rather
        than dropping otherwise-valid postings.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        item = {**_result(1), "company": {}}
        return httpx.Response(200, json={"results": [item]})

    fetcher = _make_fetcher(results_wanted=10)
    client = _attach_transport(fetcher, handler)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await client.aclose()

    assert results[0].company == "Unknown"


# ---------------------------------------------------------------------------
# Constructor invariants
# ---------------------------------------------------------------------------


def test_constructor_clamps_results_per_page_to_max() -> None:
    """Verify ``results_per_page`` above ``MAX_RESULTS_PER_PAGE`` is clamped.

    Purpose:
        Adzuna rejects per-page values above 50; clamping in the constructor
        keeps the fetcher safe even if a YAML config says 1000.
    """

    fetcher = _make_fetcher(results_per_page=10_000)

    assert fetcher._results_per_page == PAGE_SIZE


def test_constructor_clamps_results_per_page_to_min() -> None:
    """Verify ``results_per_page`` below 1 is clamped up to 1.

    Purpose:
        A zero or negative per-page value would create an infinite or invalid
        request; the constructor must guarantee ``>= 1``.
    """

    fetcher = _make_fetcher(results_per_page=0)

    assert fetcher._results_per_page == 1


def test_get_source_name_includes_country() -> None:
    """Verify the source label embeds the country code for parseability.

    Purpose:
        Crawl history rows need a stable, parseable source name so dashboards
        can split Adzuna activity by country.
    """

    fetcher = _make_fetcher(country="gb")

    assert fetcher.get_source_name() == "adzuna_gb"
