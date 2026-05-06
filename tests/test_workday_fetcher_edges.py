"""Cover WorkdayFetcher contract edges, error paths, and lazy-init behavior.

Purpose:
    Augment ``tests/test_workday_fetcher.py`` with edge cases the original
    suite skipped: ``get_source_name`` shape, two-letter locale skipping,
    malformed URLs, full Cloudflare/Akamai marker matrix, partial detail
    failures, every HTTP error path documented in the testing handoff, and
    the offset-terminator / PAGE_CAP pagination invariants.
"""

from __future__ import annotations

import httpx
import pytest

from src.fetchers.errors import FetchError
from src.fetchers.workday_fetcher import WorkdayFetcher


def _make_workday(
    *,
    company_name: str = "TestCo",
    workday_url: str = "https://testco.wd1.myworkdayjobs.com/Careers",
    fetch_descriptions: bool = True,
) -> WorkdayFetcher:
    """Construct a WorkdayFetcher without performing any I/O.

    Purpose:
        Provide a minimal fetcher whose pure helpers can be exercised and whose
        ``_client`` slot can be wired to a ``MockTransport`` in integration tests.
    Args:
        company_name: Human-readable company label for the fetcher.
        workday_url: Public Workday board URL passed to the constructor.
        fetch_descriptions: Toggle for per-job detail enrichment.
    Output:
        Returns a ready-to-use ``WorkdayFetcher`` instance.
    """

    return WorkdayFetcher(
        company_name=company_name,
        workday_url=workday_url,
        fetch_descriptions=fetch_descriptions,
    )


# ---------------------------------------------------------------------------
# get_source_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("company_name", "expected_source"),
    [
        ("IMF", "workday_imf"),
        ("Big Pharma Co", "workday_big_pharma_co"),
        ("ALL CAPS", "workday_all_caps"),
        ("already_snake", "workday_already_snake"),
        ("  Padded  ", "workday___padded__"),
    ],
)
def test_get_source_name_returns_workday_underscore_lowercase(
    company_name: str, expected_source: str
) -> None:
    """Verify ``get_source_name`` lowercases and underscore-joins the company.

    Purpose:
        Lock the exact source label shape promised by the handoff so DB rows
        and crawl history rows stay parseable by ``api/main._source_label``.
    Args:
        company_name: Input company name fed to the fetcher constructor.
        expected_source: Source label the fetcher must report.
    Output:
        Returns ``None``; passes when ``get_source_name`` matches expected.
    """

    fetcher = _make_workday(company_name=company_name)

    source_name = fetcher.get_source_name()

    assert source_name == expected_source


# ---------------------------------------------------------------------------
# _parse_board_url edges
# ---------------------------------------------------------------------------


def test_parse_board_url_skips_two_letter_locale_segment() -> None:
    """Verify a bare ``/en/`` locale segment is skipped before the site name.

    Purpose:
        Risk Areas in the handoff explicitly call out that 2-letter locale
        segments must be skipped, not selected as the site identifier.
    Args:
        None.
    Output:
        Returns ``None``; passes when ``site`` resolves to the trailing path.
    """

    _, _, site = WorkdayFetcher._parse_board_url(
        "https://acme.wd1.myworkdayjobs.com/en/Careers"
    )

    assert site == "Careers"


def test_parse_board_url_defaults_site_when_only_locale_present() -> None:
    """Verify a path containing only a locale falls back to ``External``.

    Purpose:
        Confirm the locale-skip filter cannot strip the site value down to an
        empty string and silently pass it on to CXS endpoints.
    Args:
        None.
    Output:
        Returns ``None``; passes when site equals ``External``.
    """

    _, _, site = WorkdayFetcher._parse_board_url(
        "https://acme.wd1.myworkdayjobs.com/en-US"
    )

    assert site == "External"


def test_parse_board_url_prepends_scheme_when_missing() -> None:
    """Verify a scheme-less URL is normalized to ``https://`` before parsing.

    Purpose:
        Some onboarding configs carry ``imf.wd5.myworkdayjobs.com/IMF`` without
        a scheme; the parser must still extract origin/tenant/site.
    Args:
        None.
    Output:
        Returns ``None``; passes when origin/tenant/site come back populated.
    """

    origin, tenant, site = WorkdayFetcher._parse_board_url(
        "imf.wd5.myworkdayjobs.com/IMF"
    )

    assert origin == "https://imf.wd5.myworkdayjobs.com"
    assert tenant == "imf"
    assert site == "IMF"


def test_parse_board_url_preserves_multi_section_subdomain() -> None:
    """Verify the origin keeps every subdomain label, not only the tenant.

    Purpose:
        ``wd1.myworkdayjobs.com`` and ``wd5.myworkdayjobs.com`` are different
        regions; collapsing them would break the CXS POST URLs.
    Args:
        None.
    Output:
        Returns ``None``; passes when the full host survives in ``origin``.
    """

    origin, tenant, _ = WorkdayFetcher._parse_board_url(
        "https://acme.wd103.myworkdayjobs.com/en-US/Careers"
    )

    assert origin == "https://acme.wd103.myworkdayjobs.com"
    assert tenant == "acme"


@pytest.mark.parametrize(
    "bad_url",
    ["", "https:///path", "https://", "/just/a/path"],
)
def test_parse_board_url_raises_value_error_on_unparseable_input(
    bad_url: str,
) -> None:
    """Verify ``_parse_board_url`` rejects URLs with no parseable host.

    Purpose:
        Guard the orchestrator from silently constructing CXS calls against
        empty hosts when a config file ships an invalid value.
    Args:
        bad_url: Input that lacks a usable network location.
    Output:
        Returns ``None``; passes when ``ValueError`` is raised.
    """

    with pytest.raises(ValueError, match="Invalid Workday URL"):
        WorkdayFetcher._parse_board_url(bad_url)


# ---------------------------------------------------------------------------
# _is_blocked_response marker matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "blocked_body",
    [
        "<html>cloudflare ray</html>",
        "<html>cf-chl-bypass</html>",
        "Attention Required! please solve the challenge",
        "<html>akamai reference #abc</html>",
        "Access Denied. You don't have permission",
        "<!DOCTYPE html><html><body>any html</body></html>",
    ],
)
def test_is_blocked_response_detects_known_gating_markers(
    blocked_body: str,
) -> None:
    """Verify every documented marker triggers the gating heuristic.

    Purpose:
        The handoff Risk section warns about false negatives when a new gate
        vendor appears; this matrix locks the existing marker set in place.
    Args:
        blocked_body: Response body containing one known gating marker.
    Output:
        Returns ``None``; passes when ``_is_blocked_response`` returns True.
    """

    assert WorkdayFetcher._is_blocked_response(403, blocked_body) is True


def test_is_blocked_response_returns_true_for_empty_body_with_403() -> None:
    """Verify an empty 403 body is treated as a gate response.

    Purpose:
        Some bot-mitigation gates return an empty body with a bare 403; the
        crawler must fail-soft instead of treating it as a fatal auth error.
    Args:
        None.
    Output:
        Returns ``None``; passes when the helper returns True.
    """

    assert WorkdayFetcher._is_blocked_response(403, "") is True


def test_is_blocked_response_returns_true_for_empty_body_with_401() -> None:
    """Verify an empty 401 body is treated as a gate response.

    Purpose:
        Mirror the 403 branch so 401 gating responses are also fail-soft.
    Args:
        None.
    Output:
        Returns ``None``; passes when the helper returns True.
    """

    assert WorkdayFetcher._is_blocked_response(401, "") is True


def test_is_blocked_response_returns_false_for_empty_body_with_200() -> None:
    """Verify a 200 with an empty body is not flagged as blocked.

    Purpose:
        Avoid mis-classifying tenants that legitimately return an empty 200
        as gated; only 401/403 bodies count when the body is empty.
    Args:
        None.
    Output:
        Returns ``None``; passes when the helper returns False.
    """

    assert WorkdayFetcher._is_blocked_response(200, "") is False


# ---------------------------------------------------------------------------
# _enrich_with_detail edges
# ---------------------------------------------------------------------------


def test_enrich_with_detail_keeps_listing_fields_when_jobpostinginfo_missing() -> None:
    """Verify a missing ``jobPostingInfo`` block leaves listing fields intact.

    Purpose:
        Detail responses occasionally omit the nested object; the enricher must
        not blank out the listing-derived posting in that case.
    Args:
        None.
    Output:
        Returns ``None``; passes when title/description/source_url survive.
    """

    fetcher = _make_workday()
    base = fetcher._parse_listing_job(
        {
            "title": "Listing Title",
            "externalPath": "/job/USA/Listing-Title_R-1",
            "locationsText": "USA",
            "postedOn": "Posted Today",
        }
    )

    enriched = fetcher._enrich_with_detail(base, {})

    assert enriched.title == "Listing Title"
    assert enriched.description == base.description
    assert enriched.source_url == base.source_url
    assert enriched.posted_date == "Posted Today"


def test_enrich_with_detail_keeps_listing_url_when_externalurl_missing() -> None:
    """Verify the listing source_url is preserved when detail omits externalUrl.

    Purpose:
        Some detail payloads carry no canonical URL; the enricher must not
        clobber the listing URL with an empty string.
    Args:
        None.
    Output:
        Returns ``None``; passes when source_url remains the listing URL.
    """

    fetcher = _make_workday()
    base = fetcher._parse_listing_job(
        {
            "title": "Role",
            "externalPath": "/job/USA/Role_R-1",
            "locationsText": "USA",
        }
    )
    detail = {"jobPostingInfo": {"title": "Role", "jobDescription": "<p>Body</p>"}}

    enriched = fetcher._enrich_with_detail(base, detail)

    assert enriched.source_url == base.source_url
    assert enriched.description == "Body"


# ---------------------------------------------------------------------------
# fetch_jobs HTTP edges via httpx.MockTransport
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetcher_returns_empty_on_429_rate_limit() -> None:
    """Verify a 429 fails-soft to an empty list rather than raising.

    Purpose:
        Rate limits should not fail the entire crawl cycle; the orchestrator
        treats an empty list as a clean run that increments success counters.
    Args:
        None.
    Output:
        Returns ``None``; passes when fetch_jobs returns an empty list.
    """

    transport = httpx.MockTransport(lambda _: httpx.Response(429))
    fetcher = _make_workday()
    fetcher._client = httpx.AsyncClient(transport=transport)

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()

    assert results == []


@pytest.mark.asyncio
async def test_fetcher_raises_fetch_error_on_unblocked_403() -> None:
    """Verify a 403 with no gating markers escalates to ``FetchError``.

    Purpose:
        A genuine authorization failure must surface so the orchestrator can
        record the FAILED crawl row instead of silently skipping the company.
    Args:
        None.
    Output:
        Returns ``None``; passes when ``FetchError`` is raised.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        """Return a non-blocked 403 with a JSON body to bypass the gate path."""

        return httpx.Response(
            403,
            json={"error": "forbidden"},
            headers={"content-type": "application/json"},
        )

    fetcher = _make_workday()
    fetcher._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    try:
        with pytest.raises(FetchError, match="Authorization failure"):
            await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()


@pytest.mark.asyncio
async def test_fetcher_raises_fetch_error_on_unexpected_non_json_2xx() -> None:
    """Verify a 200 HTML response without gate markers raises ``FetchError``.

    Purpose:
        If a tenant ever serves real HTML on the CXS endpoint without any
        gating markers we can detect, treat it as a hard failure rather than
        masking the contract break.
    Args:
        None.
    Output:
        Returns ``None``; passes when ``FetchError`` is raised.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        """Return a 200 HTML response that does not look like a gate."""

        return httpx.Response(
            200,
            text="<xml><result>ok</result></xml>",
            headers={"content-type": "application/xml"},
        )

    fetcher = _make_workday()
    fetcher._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    try:
        with pytest.raises(FetchError, match="non-JSON"):
            await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()


@pytest.mark.asyncio
async def test_fetcher_raises_fetch_error_on_invalid_json_2xx() -> None:
    """Verify a malformed JSON body on a 200 response raises ``FetchError``.

    Purpose:
        An advertised JSON content-type with a body that fails to decode is a
        hard tenant bug, not a fail-soft case.
    Args:
        None.
    Output:
        Returns ``None``; passes when ``FetchError`` is raised.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        """Return broken JSON despite the proper content-type header."""

        return httpx.Response(
            200,
            text="{not-json",
            headers={"content-type": "application/json"},
        )

    fetcher = _make_workday()
    fetcher._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    try:
        with pytest.raises(FetchError, match="Invalid JSON"):
            await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()


@pytest.mark.asyncio
async def test_fetcher_raises_fetch_error_on_network_failure() -> None:
    """Verify an httpx transport error bubbles up as ``FetchError``.

    Purpose:
        Any low-level network failure must reach the orchestrator so the
        FAILED crawl row records a meaningful error message.
    Args:
        None.
    Output:
        Returns ``None``; passes when ``FetchError`` wraps the transport error.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        """Raise an httpx transport error to simulate a connection drop."""

        raise httpx.ConnectError("connection reset")

    fetcher = _make_workday()
    fetcher._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    try:
        with pytest.raises(FetchError, match="Network error"):
            await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()


@pytest.mark.asyncio
async def test_fetcher_stops_paginating_when_offset_meets_total() -> None:
    """Verify pagination terminates as soon as ``offset >= total``.

    Purpose:
        Risk Areas flag this as bug-prone; the loop must stop before issuing
        an extra empty-page request when the server reports a finite total.
    Args:
        None.
    Output:
        Returns ``None``; passes when fetch_jobs stops after one listing call.
    """

    listing_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve a single full page declaring an exact total of LIMIT."""

        nonlocal listing_calls
        if request.url.path.endswith("/jobs"):
            listing_calls += 1
            return httpx.Response(
                200,
                json={
                    "total": WorkdayFetcher.LIMIT,
                    "jobPostings": [
                        {
                            "title": f"Role {idx}",
                            "externalPath": f"/job/USA/Role-{idx}_R-{idx}",
                            "locationsText": "USA",
                        }
                        for idx in range(WorkdayFetcher.LIMIT)
                    ],
                },
                headers={"content-type": "application/json"},
            )
        return httpx.Response(200, json={}, headers={"content-type": "application/json"})

    fetcher = _make_workday(fetch_descriptions=False)
    fetcher._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()

    assert len(results) == WorkdayFetcher.LIMIT
    assert listing_calls == 1


@pytest.mark.asyncio
async def test_fetcher_keeps_listing_posting_when_detail_call_fails() -> None:
    """Verify a failing detail call leaves the listing posting in the result.

    Purpose:
        The handoff promises that one bad detail response must not drop the
        listing-derived posting; the orchestrator depends on this for partial
        crawls under flaky tenants.
    Args:
        None.
    Output:
        Returns ``None``; passes when the posting is returned with empty body.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a single-row listing then a 500 on the detail call."""

        if request.url.path.endswith("/jobs"):
            return httpx.Response(
                200,
                json={
                    "total": 1,
                    "jobPostings": [
                        {
                            "title": "Role",
                            "externalPath": "/job/USA/Role_R-1",
                            "locationsText": "USA",
                        }
                    ],
                },
                headers={"content-type": "application/json"},
            )
        return httpx.Response(500, text="upstream broken")

    fetcher = _make_workday()
    fetcher._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()

    assert len(results) == 1
    assert results[0].title == "Role"
    assert results[0].description == ""


@pytest.mark.asyncio
async def test_fetcher_keeps_listing_posting_when_detail_call_hits_network_error() -> None:
    """Verify a network error on the detail call leaves the listing posting intact.

    Purpose:
        ``_fetch_detail`` swallows ``httpx.RequestError`` and returns ``None``;
        this test pins that fail-soft contract so a flaky tenant cannot drop
        listing rows from the crawl results.
    Args:
        None.
    Output:
        Returns ``None``; passes when the listing posting survives unenriched.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a single-row listing then raise on the detail GET."""

        if request.url.path.endswith("/jobs"):
            return httpx.Response(
                200,
                json={
                    "total": 1,
                    "jobPostings": [
                        {
                            "title": "Role",
                            "externalPath": "/job/USA/Role_R-1",
                            "locationsText": "USA",
                        }
                    ],
                },
                headers={"content-type": "application/json"},
            )
        raise httpx.ConnectTimeout("detail timeout")

    fetcher = _make_workday()
    fetcher._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    try:
        results = await fetcher.fetch_jobs()
    finally:
        await fetcher._client.aclose()

    assert len(results) == 1
    assert results[0].title == "Role"
    assert results[0].description == ""


@pytest.mark.asyncio
async def test_fetcher_lazy_inits_client_when_called_outside_context_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify ``fetch_jobs`` builds a client when none was set by ``__aenter__``.

    Purpose:
        The handoff claims this should raise, but the implementation lazy-inits
        the client. Pin the actual behavior so the lazy-init path cannot
        regress silently — and document the contract drift between the handoff
        and the production code.
    Args:
        monkeypatch: Pytest fixture used to redirect ``_build_client`` to a
            ``MockTransport``-backed client so no real network call occurs.
    Output:
        Returns ``None``; passes when fetch_jobs runs without raising.
    """

    def empty_handler(_: httpx.Request) -> httpx.Response:
        """Return an immediate empty CXS page for the lazy-init test."""

        return httpx.Response(
            200,
            json={"total": 0, "jobPostings": []},
            headers={"content-type": "application/json"},
        )

    fetcher = _make_workday()
    monkeypatch.setattr(
        fetcher,
        "_build_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(empty_handler)),
    )
    initial_client = fetcher._client

    results = await fetcher.fetch_jobs()

    assert initial_client is None
    assert isinstance(fetcher._client, httpx.AsyncClient)
    await fetcher._client.aclose()
    assert results == []
