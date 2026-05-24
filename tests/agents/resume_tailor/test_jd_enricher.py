"""Behavior tests for the lazy JD-enrichment helper.

Covers:
    * Pure helpers (``_description_is_usable``, ``_extract_linkedin_job_id``,
      ``_force_in_iframe``, ``_strip_html``, JSON-LD / DOM iCIMS parsers).
    * Per-source fetchers with mocked HTTP clients at the import boundary
      (``AsyncSession`` for LinkedIn, ``httpx.AsyncClient`` for iCIMS).
    * End-to-end ``_maybe_enrich_job_description`` against a real SQLite
      database — per project rule, no DB mocks.  The load-bearing
      requirement ("tailor must not fail because of enrichment") is
      exercised explicitly via raising fetchers and short-body returns.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio

from src.agents.resume_tailor import jd_enricher
from src.database.db_manager import DatabaseManager


# ---------- Fixtures ----------


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Provide a migrated DB so enrichment can write through to a real table."""

    manager = DatabaseManager(str(tmp_path / "enricher.db"))
    await manager.connect()
    await manager.create_tables()
    yield manager
    await manager.close()


def _insert_payload(
    *,
    job_hash: str,
    source: str,
    source_url: str,
    description: str,
) -> dict[str, Any]:
    """Build the minimum payload accepted by ``insert_job``."""

    return {
        "job_hash": job_hash,
        "source": source,
        "source_url": source_url,
        "company": "TestCo",
        "company_url": None,
        "title": "Engineer Intern",
        "location": "Remote",
        "is_remote": True,
        "job_type": "intern",
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "salary_source": "not_listed",
        "description": description,
        "requirements": "",
        "posted_date": None,
        "raw_data": "{}",
    }


# ---------- _description_is_usable ----------


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", "\n\t  ", "LinkedIn job posting: SWE Intern at PlusAI"],
)
def test_description_is_unusable_for_stub_values(value: str | None) -> None:
    """None, blank, and LinkedIn placeholders all count as unusable."""

    assert jd_enricher._description_is_usable(value) is False


def test_description_unusable_when_under_threshold() -> None:
    """Real-looking but short descriptions still trigger re-fetch."""

    short = "Engineering intern. Build stuff. 12 weeks."

    assert jd_enricher._description_is_usable(short) is False


def test_description_usable_when_above_threshold() -> None:
    """A 200+ char real description is accepted as-is."""

    real = "x" * jd_enricher.WEAK_DESCRIPTION_THRESHOLD_CHARS

    assert jd_enricher._description_is_usable(real) is True


# ---------- _extract_linkedin_job_id ----------


def test_extract_linkedin_job_id_returns_trailing_run() -> None:
    """Canonical LinkedIn URLs end with the job id after the slug."""

    url = (
        "https://www.linkedin.com/jobs/view/"
        "research-engineer-intern-control-at-plusai-4414358640"
    )

    assert jd_enricher._extract_linkedin_job_id(url) == "4414358640"


def test_extract_linkedin_job_id_skips_short_numeric_tokens() -> None:
    """Slugs containing years (``2026``) must not shadow the real id."""

    url = (
        "https://www.linkedin.com/jobs/view/"
        "2026-internship-ai-science-at-samsung-sds-america-4418407172"
    )

    assert jd_enricher._extract_linkedin_job_id(url) == "4418407172"


@pytest.mark.parametrize("value", [None, "", "https://example.com/no-digits-here"])
def test_extract_linkedin_job_id_returns_none_when_absent(value: str | None) -> None:
    """No id → caller skips the network entirely."""

    assert jd_enricher._extract_linkedin_job_id(value) is None


# ---------- _force_in_iframe ----------


def test_force_in_iframe_appends_when_param_missing() -> None:
    """A bare URL gets the iframe flag appended with ``?``."""

    url = "https://careers-phc.icims.com/jobs/53912/physiotherapist-new-grad/job"

    assert jd_enricher._force_in_iframe(url) == url + "?in_iframe=1"


def test_force_in_iframe_uses_amp_when_other_params_exist() -> None:
    """Existing query strings get an ``&`` separator, not ``?``."""

    url = "https://careers.icims.com/jobs/1/job?utm=foo"

    assert jd_enricher._force_in_iframe(url) == url + "&in_iframe=1"


def test_force_in_iframe_overrides_zero_value() -> None:
    """``in_iframe=0`` is the SEO wrapper — overwrite it."""

    url = "https://careers.icims.com/jobs/1/job?in_iframe=0"

    assert jd_enricher._force_in_iframe(url) == (
        "https://careers.icims.com/jobs/1/job?in_iframe=1"
    )


def test_force_in_iframe_preserves_when_already_one() -> None:
    """Idempotent when already set to ``1``."""

    url = "https://careers.icims.com/jobs/1/job?in_iframe=1"

    assert jd_enricher._force_in_iframe(url) == url


# ---------- _strip_html ----------


def test_strip_html_decodes_entities_and_collapses_whitespace() -> None:
    """Entities decoded, tags removed, runs of whitespace collapsed.

    ``&nbsp;`` decodes to U+00A0 which Python's ``\\s`` treats as
    whitespace, so it collapses into the surrounding spaces — that's
    the intended behavior for prompt text.
    """

    raw = "<p>Hello&nbsp;world</p>\n<p>  Second   line  </p>"

    assert jd_enricher._strip_html(raw) == "Hello world Second line"


def test_strip_html_returns_empty_for_empty_input() -> None:
    """Empty in → empty out (no AttributeError on ``re.sub`` boundary)."""

    assert jd_enricher._strip_html("") == ""


# ---------- iCIMS parsers ----------


_ICIMS_JSONLD_HTML = """\
<html><head>
<script type="application/ld+json">
{"@type": "BreadcrumbList", "itemListElement": []}
</script>
<script type="application/ld+json">
{"@type": "JobPosting", "title": "RN", "description": "<p>Care for patients. <strong>Real responsibilities</strong> here.</p>"}
</script>
</head><body>Other content</body></html>
"""


def test_parse_icims_jsonld_picks_jobposting_node() -> None:
    """Skips BreadcrumbList, picks JobPosting, strips inner HTML."""

    description = jd_enricher._parse_icims_jsonld(_ICIMS_JSONLD_HTML)

    assert description == "Care for patients. Real responsibilities here."


def test_parse_icims_jsonld_handles_graph_wrapper() -> None:
    """iCIMS sometimes wraps nodes in a Schema.org ``@graph`` array."""

    html = (
        '<script type="application/ld+json">'
        + json.dumps(
            {
                "@context": "https://schema.org",
                "@graph": [
                    {"@type": "Organization", "name": "Acme"},
                    {
                        "@type": "JobPosting",
                        "description": "<p>Build cool things.</p>",
                    },
                ],
            }
        )
        + "</script>"
    )

    assert jd_enricher._parse_icims_jsonld(html) == "Build cool things."


def test_parse_icims_jsonld_skips_malformed_blocks() -> None:
    """A malformed JSON-LD block must not break extraction of later valid ones."""

    html = (
        '<script type="application/ld+json">{not json,}</script>'
        '<script type="application/ld+json">'
        + json.dumps({"@type": "JobPosting", "description": "Valid body text."})
        + "</script>"
    )

    assert jd_enricher._parse_icims_jsonld(html) == "Valid body text."


def test_parse_icims_jsonld_returns_empty_when_no_jobposting() -> None:
    """Pages without a JobPosting node yield empty string, not garbage."""

    html = (
        '<script type="application/ld+json">'
        + json.dumps({"@type": "Organization", "name": "Acme"})
        + "</script>"
    )

    assert jd_enricher._parse_icims_jsonld(html) == ""


def test_parse_icims_dom_fallback_requires_minimum_length() -> None:
    """Near-empty wrapper divs must not be promoted to a real description."""

    html = '<div class="iCIMS_JobContent">Loading...</div>'

    assert jd_enricher._parse_icims_dom_fallback(html) == ""


def test_parse_icims_dom_fallback_extracts_when_substantial() -> None:
    """A populated wrapper above the floor returns clean text."""

    body = " ".join(["Responsibilities include reviewing X."] * 10)
    html = (
        f'<div class="iCIMS_JobContent"><div>{body}</div></div>'
        '<div class="iCIMS_Footer">©</div>'
    )

    result = jd_enricher._parse_icims_dom_fallback(html)

    assert "Responsibilities include reviewing X." in result
    assert len(result) >= jd_enricher.MIN_ICIMS_DOM_FALLBACK_CHARS


# ---------- Boundary mocks ----------


class _FakeResponse:
    """Minimal stand-in for both ``httpx.Response`` and curl_cffi responses."""

    def __init__(self, *, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


class _FakeAsyncSession:
    """Async-context-manager that returns a fixed response or raises."""

    def __init__(
        self,
        *,
        response: _FakeResponse | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._response = response
        self._raise_exc = raise_exc
        self.last_url: str | None = None

    async def __aenter__(self) -> "_FakeAsyncSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, url: str) -> _FakeResponse:
        self.last_url = url
        if self._raise_exc is not None:
            raise self._raise_exc
        assert self._response is not None
        return self._response


def _make_session_factory(
    *,
    response: _FakeResponse | None = None,
    raise_exc: Exception | None = None,
) -> tuple[Any, list[_FakeAsyncSession]]:
    """Build a constructor that records every session it produces."""

    instances: list[_FakeAsyncSession] = []

    def factory(*_: object, **__: object) -> _FakeAsyncSession:
        session = _FakeAsyncSession(response=response, raise_exc=raise_exc)
        instances.append(session)
        return session

    return factory, instances


# ---------- _fetch_linkedin_jd ----------


@pytest.mark.asyncio
async def test_fetch_linkedin_returns_empty_when_no_job_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No id → skip network entirely (no AsyncSession constructed)."""

    factory, instances = _make_session_factory(
        response=_FakeResponse(status_code=200, text="<p>x</p>")
    )
    monkeypatch.setattr(jd_enricher, "AsyncSession", factory)

    result = await jd_enricher._fetch_linkedin_jd("https://example.com/no-digits")

    assert result == ""
    assert instances == []


@pytest.mark.asyncio
async def test_fetch_linkedin_returns_stripped_text_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """200 + HTML → tags stripped, entities decoded."""

    html = "<section><h2>About</h2><p>Real LinkedIn body text.</p></section>"
    factory, instances = _make_session_factory(
        response=_FakeResponse(status_code=200, text=html)
    )
    monkeypatch.setattr(jd_enricher, "AsyncSession", factory)

    result = await jd_enricher._fetch_linkedin_jd(
        "https://www.linkedin.com/jobs/view/role-at-plusai-4414358640"
    )

    assert "Real LinkedIn body text" in result
    assert "<" not in result
    assert instances[0].last_url == (
        "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/4414358640"
    )


@pytest.mark.asyncio
async def test_fetch_linkedin_returns_empty_on_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any non-200 response is treated as failure."""

    factory, _ = _make_session_factory(
        response=_FakeResponse(status_code=429, text="rate limited")
    )
    monkeypatch.setattr(jd_enricher, "AsyncSession", factory)

    result = await jd_enricher._fetch_linkedin_jd(
        "https://www.linkedin.com/jobs/view/role-at-plusai-4414358640"
    )

    assert result == ""


@pytest.mark.asyncio
async def test_fetch_linkedin_swallows_request_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A curl_cffi RequestsError must not propagate."""

    from curl_cffi.requests import errors as curl_errors

    factory, _ = _make_session_factory(
        raise_exc=curl_errors.RequestsError("connection reset")
    )
    monkeypatch.setattr(jd_enricher, "AsyncSession", factory)

    result = await jd_enricher._fetch_linkedin_jd(
        "https://www.linkedin.com/jobs/view/role-at-plusai-4414358640"
    )

    assert result == ""


# ---------- _fetch_icims_jd ----------


class _FakeHttpxClient:
    """Async-context-manager mimicking ``httpx.AsyncClient``."""

    def __init__(
        self,
        *,
        response: _FakeResponse | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._response = response
        self._raise_exc = raise_exc
        self.last_url: str | None = None

    async def __aenter__(self) -> "_FakeHttpxClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, url: str) -> _FakeResponse:
        self.last_url = url
        if self._raise_exc is not None:
            raise self._raise_exc
        assert self._response is not None
        return self._response


def _patch_httpx_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    response: _FakeResponse | None = None,
    raise_exc: Exception | None = None,
) -> list[_FakeHttpxClient]:
    """Swap ``httpx.AsyncClient`` for a recording fake."""

    instances: list[_FakeHttpxClient] = []

    def factory(*_: object, **__: object) -> _FakeHttpxClient:
        client = _FakeHttpxClient(response=response, raise_exc=raise_exc)
        instances.append(client)
        return client

    # Patch at the real httpx module: ``jd_enricher`` looks up
    # ``httpx.AsyncClient`` through its imported ``httpx`` reference,
    # so attribute-replacing on the module object covers it without
    # tripping mypy strict on a non-exported attribute access.
    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return instances


@pytest.mark.asyncio
async def test_fetch_icims_returns_empty_for_blank_url() -> None:
    """No URL → no network — guards against malformed rows."""

    assert await jd_enricher._fetch_icims_jd(None) == ""
    assert await jd_enricher._fetch_icims_jd("") == ""


@pytest.mark.asyncio
async def test_fetch_icims_extracts_jsonld_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real iCIMS-shaped HTML → JSON-LD description returned."""

    instances = _patch_httpx_client(
        monkeypatch,
        response=_FakeResponse(status_code=200, text=_ICIMS_JSONLD_HTML),
    )

    result = await jd_enricher._fetch_icims_jd(
        "https://careers.icims.com/jobs/1/job"
    )

    assert result == "Care for patients. Real responsibilities here."
    assert instances[0].last_url == (
        "https://careers.icims.com/jobs/1/job?in_iframe=1"
    )


@pytest.mark.asyncio
async def test_fetch_icims_swallows_httpx_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``httpx.HTTPError`` must not propagate to the caller."""

    _patch_httpx_client(monkeypatch, raise_exc=httpx.ConnectTimeout("boom"))

    assert (
        await jd_enricher._fetch_icims_jd(
            "https://careers.icims.com/jobs/1/job"
        )
        == ""
    )


@pytest.mark.asyncio
async def test_fetch_icims_returns_empty_on_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-200 responses are treated as failure even if the body is HTML."""

    _patch_httpx_client(
        monkeypatch,
        response=_FakeResponse(status_code=403, text=_ICIMS_JSONLD_HTML),
    )

    assert (
        await jd_enricher._fetch_icims_jd(
            "https://careers.icims.com/jobs/1/job"
        )
        == ""
    )


# ---------- _maybe_enrich_job_description (DB-backed) ----------


@pytest.mark.asyncio
async def test_enrich_skips_usable_descriptions(db: DatabaseManager) -> None:
    """A real description is passed through untouched (no network, no write)."""

    real = "x" * (jd_enricher.WEAK_DESCRIPTION_THRESHOLD_CHARS + 50)
    job_hash = "a" * 40
    await db.insert_job(
        _insert_payload(
            job_hash=job_hash,
            source="greenhouse_acme",
            source_url="https://boards.greenhouse.io/acme/jobs/1",
            description=real,
        )
    )
    row = await db.get_resume_tailor_job_context(job_hash=job_hash)
    assert row is not None

    result = await jd_enricher._maybe_enrich_job_description(
        db=db, job_row=row, job_hash=job_hash
    )

    assert result["description"] == real


@pytest.mark.asyncio
async def test_enrich_skips_unknown_sources(db: DatabaseManager) -> None:
    """Sources without a fetcher route fall through unchanged."""

    job_hash = "b" * 40
    await db.insert_job(
        _insert_payload(
            job_hash=job_hash,
            source="github_simplifyjobs_summer2026",
            source_url="https://example.com/foo",
            description="",
        )
    )
    row = await db.get_resume_tailor_job_context(job_hash=job_hash)
    assert row is not None

    result = await jd_enricher._maybe_enrich_job_description(
        db=db, job_row=row, job_hash=job_hash
    )

    assert result is row


@pytest.mark.asyncio
async def test_enrich_swallows_fetcher_exception(
    db: DatabaseManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Load-bearing requirement: a fetcher that raises must not fail the run."""

    async def boom(_url: str | None) -> str:
        raise RuntimeError("network gone")

    monkeypatch.setattr(jd_enricher, "_fetch_linkedin_jd", boom)

    job_hash = "c" * 40
    await db.insert_job(
        _insert_payload(
            job_hash=job_hash,
            source="linkedin_software_engineer_intern",
            source_url="https://www.linkedin.com/jobs/view/role-1234567890",
            description="LinkedIn job posting: SWE at Acme",
        )
    )
    row = await db.get_resume_tailor_job_context(job_hash=job_hash)
    assert row is not None

    result = await jd_enricher._maybe_enrich_job_description(
        db=db, job_row=row, job_hash=job_hash
    )

    assert result["description"] == "LinkedIn job posting: SWE at Acme"
    persisted = await db.get_job_by_hash(job_hash)
    assert persisted is not None
    assert persisted["description"] == "LinkedIn job posting: SWE at Acme"


@pytest.mark.asyncio
async def test_enrich_discards_too_short_fetch(
    db: DatabaseManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fetcher that returns under the floor is treated as failure."""

    async def tiny(_url: str | None) -> str:
        return "not enough"

    monkeypatch.setattr(jd_enricher, "_fetch_linkedin_jd", tiny)

    job_hash = "d" * 40
    await db.insert_job(
        _insert_payload(
            job_hash=job_hash,
            source="linkedin_research_engineer_intern",
            source_url="https://www.linkedin.com/jobs/view/role-1234567890",
            description="",
        )
    )
    row = await db.get_resume_tailor_job_context(job_hash=job_hash)
    assert row is not None

    result = await jd_enricher._maybe_enrich_job_description(
        db=db, job_row=row, job_hash=job_hash
    )

    assert result is row
    persisted = await db.get_job_by_hash(job_hash)
    assert persisted is not None
    assert persisted["description"] == ""


@pytest.mark.asyncio
async def test_enrich_writes_back_and_returns_updated_row(
    db: DatabaseManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful fetch caches the body to the DB and surfaces it in-memory."""

    body = "Real LinkedIn description body. " * 30
    assert len(body) >= jd_enricher.MIN_ACCEPTABLE_FETCH_CHARS

    async def good(_url: str | None) -> str:
        return body

    monkeypatch.setattr(jd_enricher, "_fetch_linkedin_jd", good)

    job_hash = "e" * 40
    await db.insert_job(
        _insert_payload(
            job_hash=job_hash,
            source="linkedin_data_engineer_intern",
            source_url="https://www.linkedin.com/jobs/view/role-1234567890",
            description="LinkedIn job posting: DE at PlusAI",
        )
    )
    row = await db.get_resume_tailor_job_context(job_hash=job_hash)
    assert row is not None

    result = await jd_enricher._maybe_enrich_job_description(
        db=db, job_row=row, job_hash=job_hash
    )

    assert result["description"] == body
    persisted = await db.get_job_by_hash(job_hash)
    assert persisted is not None
    assert persisted["description"] == body


@pytest.mark.asyncio
async def test_enrich_works_for_icims_path(
    db: DatabaseManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """iCIMS source routes through ``_fetch_icims_jd`` and caches the body."""

    body = "Comprehensive iCIMS-sourced description body. " * 20
    assert len(body) >= jd_enricher.MIN_ACCEPTABLE_FETCH_CHARS

    captured_urls: list[str | None] = []

    async def fake_icims(url: str | None) -> str:
        captured_urls.append(url)
        return body

    monkeypatch.setattr(jd_enricher, "_fetch_icims_jd", fake_icims)

    job_hash = "f" * 40
    icims_url = "https://careers-phc.icims.com/jobs/53912/role/job?in_iframe=1"
    await db.insert_job(
        _insert_payload(
            job_hash=job_hash,
            source="icims_providence_health",
            source_url=icims_url,
            description="",
        )
    )
    row = await db.get_resume_tailor_job_context(job_hash=job_hash)
    assert row is not None

    result = await jd_enricher._maybe_enrich_job_description(
        db=db, job_row=row, job_hash=job_hash
    )

    assert result["description"] == body
    assert captured_urls == [icims_url]
