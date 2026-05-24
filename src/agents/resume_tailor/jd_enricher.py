"""Lazy job-description enrichment for the resume-tailor pipeline.

Several discovery adapters write only an empty string or a synthetic
placeholder into ``job_postings.description`` at insert time
(LinkedIn's guest card scraper, iCIMS pre-`_fetch_detail`, Workday
pre-A-flip).  Tailoring against a stub description produces weak
output, so this module is called just before the tailor LLM and tries
to backfill the body by hitting the source URL once.

Two load-bearing invariants:

* **The tailor pipeline must never fail because enrichment failed.**
  Every per-source helper swallows its own exceptions and returns
  ``""``; the outer wrapper has its own backstop ``except Exception``.
* **The cache is best-effort.**  A successful fetch is written back to
  ``job_postings.description`` so future runs and debug queries see
  the real body, but a write failure does not block the in-progress
  tailor run from using the fetched text in-memory.
"""

from __future__ import annotations

import html as html_module
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, Optional

import httpx
from curl_cffi.requests import AsyncSession
from curl_cffi.requests import errors as curl_errors
from loguru import logger

from src.database.db_manager import DatabaseManager

# Minimum chars below which we suspect the description is a stub.
# Real Greenhouse/JobSpy descriptions land at 1.5k-15k chars; LinkedIn
# synthetic placeholders are 50-200; Workday rows pre-flip are 0.
# 200 sits comfortably between the two distributions.
WEAK_DESCRIPTION_THRESHOLD_CHARS = 200

# Minimum chars a freshly-fetched body must have before we trust it
# enough to cache and use.  A 500-char floor rejects "job no longer
# available" stubs and HTML-stripped error pages while still accepting
# the smallest plausible real JD.
MIN_ACCEPTABLE_FETCH_CHARS = 500

# Synthetic placeholder prefix written by
# ``linkedin_fetcher._parse_card`` when per-card description fetching
# is disabled.  Pattern match is load-bearing: every short LinkedIn
# row in the DB starts with this exact string.
LINKEDIN_PLACEHOLDER_PREFIX = "LinkedIn job posting:"

# LinkedIn guest job-detail endpoint — same URL pattern the discovery
# fetcher uses (see ``src/fetchers/linkedin_fetcher.py:32``).
LINKEDIN_JOB_DETAIL_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
)

# LinkedIn job IDs are 8+ consecutive digits; canonical URLs end with
# ``-<job_id>`` but some include earlier numeric tokens like ``2026``
# in the slug, so we take the *last* matching run rather than the first.
_LINKEDIN_JOB_ID_RE = re.compile(r"(\d{8,})")

# iCIMS embeds a Schema.org ``JobPosting`` JSON-LD blob whose
# ``description`` field is the full HTML body.  Only present when the
# iframe-rendered variant of the page is fetched.
_JSONLD_SCRIPT_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_ICIMS_JOBCONTENT_RE = re.compile(
    r'<div[^>]*class="[^"]*iCIMS_JobContent[^"]*"[^>]*>'
    r"(.*?)"
    r'(?=<div[^>]*class="[^"]*iCIMS_Footer|</body>)',
    re.DOTALL | re.IGNORECASE,
)

# Browser-like headers — bare httpx UAs occasionally get 403s from
# Akamai-fronted iCIMS tenants; this Chrome 120 set was confirmed to
# work against three live iCIMS tenants and LinkedIn guest endpoints.
_BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Per-fetch timeout in seconds — generous enough for slow tenants but
# short enough that a hung connection cannot stall the tailor run.
FETCH_TIMEOUT_SECONDS = 15.0

# Minimum length of a usable iCIMS DOM-fallback extract.  The wrapper
# div is often present but near-empty on tenants that render the body
# entirely via JavaScript, so we require a substantive payload.
MIN_ICIMS_DOM_FALLBACK_CHARS = 200


# Type alias for the per-source fetch coroutines so the router signature
# stays readable.
JdFetcher = Callable[[Optional[str]], Awaitable[str]]


def _strip_html(raw: str) -> str:
    """Reduce HTML to whitespace-collapsed plain text.

    Purpose:
        Mirror ``greenhouse_fetcher._clean_html`` so the description
        format the tailor sees is consistent regardless of source.
    Args:
        raw: HTML or plain-text string; empty input returns empty.
    Output:
        Plain-text string with HTML entities decoded and whitespace
        collapsed to single spaces.
    """

    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html_module.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _description_is_usable(description: Optional[str]) -> bool:
    """Decide whether an existing description is good enough to keep.

    Purpose:
        Single source of truth for the "should we enrich" decision so
        the rule stays consistent across sources and is easy to tune.
    Args:
        description: The current ``description`` field on the job row.
    Output:
        ``True`` when the row already has a real, non-stub JD body.
    """

    if description is None:
        return False
    stripped = description.strip()
    if not stripped:
        return False
    if stripped.startswith(LINKEDIN_PLACEHOLDER_PREFIX):
        return False
    return len(stripped) >= WEAK_DESCRIPTION_THRESHOLD_CHARS


def _extract_linkedin_job_id(source_url: Optional[str]) -> Optional[str]:
    """Pull the numeric job id out of a canonical LinkedIn job URL.

    Purpose:
        The tailor context row does not preserve ``raw_data['job_id']``,
        so we recover the id from the URL the same way the discovery
        fetcher formats it.
    Args:
        source_url: The ``source_url`` field from ``job_postings``.
    Output:
        Trailing digit run as a string, or ``None`` when no plausible
        id is present.
    """

    if not source_url:
        return None
    matches = _LINKEDIN_JOB_ID_RE.findall(source_url)
    return matches[-1] if matches else None


def _force_in_iframe(source_url: str) -> str:
    """Normalize an iCIMS URL to the JSON-LD-bearing iframe variant.

    Purpose:
        iCIMS only ships the ``application/ld+json`` JobPosting block
        on the iframe-rendered page; the SEO marketing wrapper omits
        it entirely.  Without this, JSON-LD parsing silently fails.
    Args:
        source_url: iCIMS career page URL, with or without the param.
    Output:
        Same URL with ``in_iframe=1`` set (any prior value is replaced).
    """

    if "in_iframe=" in source_url:
        return re.sub(r"in_iframe=\d+", "in_iframe=1", source_url)
    separator = "&" if "?" in source_url else "?"
    return f"{source_url}{separator}in_iframe=1"


async def _fetch_linkedin_jd(source_url: Optional[str]) -> str:
    """Fetch a LinkedIn JD via the guest jobPosting endpoint.

    Purpose:
        Backfill the body for LinkedIn rows that only carry the
        synthetic placeholder string.  Uses ``curl_cffi`` so the TLS
        fingerprint mimics Chrome (LinkedIn aggressively fingerprints
        bare httpx clients).
    Args:
        source_url: Public LinkedIn job URL stored on the row.
    Output:
        Plain-text JD body, or empty string on any failure.
    """

    job_id = _extract_linkedin_job_id(source_url)
    if job_id is None:
        return ""
    endpoint = LINKEDIN_JOB_DETAIL_URL.format(job_id=job_id)
    try:
        async with AsyncSession(
            impersonate="chrome120",
            timeout=FETCH_TIMEOUT_SECONDS,
            headers=_BROWSER_HEADERS,
        ) as session:
            response = await session.get(endpoint)
        if response.status_code != 200:
            return ""
        return _strip_html(response.text or "")
    except curl_errors.RequestsError:
        return ""


async def _fetch_icims_jd(source_url: Optional[str]) -> str:
    """Fetch an iCIMS JD by parsing the page's JSON-LD JobPosting blob.

    Purpose:
        iCIMS exposes no public REST/GraphQL API for job detail, but
        every tenant ships a Schema.org ``JobPosting`` script for
        Google for Jobs.  The ``description`` field there holds the
        full HTML body and is more stable across tenants than any
        DOM selector.
    Args:
        source_url: Public iCIMS career page URL.
    Output:
        Plain-text JD body, or empty string on any failure.
    """

    if not source_url:
        return ""
    url = _force_in_iframe(source_url)
    try:
        async with httpx.AsyncClient(
            headers=_BROWSER_HEADERS,
            timeout=FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
    except httpx.HTTPError:
        return ""
    if response.status_code != 200 or not response.text:
        return ""
    html = response.text

    description = _parse_icims_jsonld(html)
    if description:
        return description
    return _parse_icims_dom_fallback(html)


def _parse_icims_jsonld(html: str) -> str:
    """Extract a description from any iCIMS JobPosting JSON-LD block.

    Purpose:
        Isolate the parse so a malformed block on one tenant cannot
        break the whole fetch — each candidate is decoded independently
        and skipped on ``JSONDecodeError``.
    Args:
        html: Full iCIMS page HTML.
    Output:
        Plain-text JD body, or empty string when no ``JobPosting`` node
        carries a non-empty description.
    """

    for match in _JSONLD_SCRIPT_RE.finditer(html):
        try:
            payload = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            continue
        candidates: list[Any]
        if isinstance(payload, list):
            candidates = payload
        elif isinstance(payload, dict) and "@graph" in payload:
            graph = payload["@graph"]
            candidates = graph if isinstance(graph, list) else [graph]
        else:
            candidates = [payload]
        for node in candidates:
            if not isinstance(node, dict):
                continue
            if node.get("@type") != "JobPosting":
                continue
            description = node.get("description")
            if isinstance(description, str) and description.strip():
                return _strip_html(description)
    return ""


def _parse_icims_dom_fallback(html: str) -> str:
    """Fallback iCIMS extraction using the ``iCIMS_JobContent`` div.

    Purpose:
        Cover the rare tenant that omits JSON-LD or ships malformed
        JSON.  Enforces a length floor so a near-empty skeleton div
        isn't promoted to a "real" description.
    Args:
        html: Full iCIMS page HTML.
    Output:
        Plain-text JD body, or empty string when nothing usable is found.
    """

    match = _ICIMS_JOBCONTENT_RE.search(html)
    if not match:
        return ""
    text = _strip_html(match.group(1))
    return text if len(text) >= MIN_ICIMS_DOM_FALLBACK_CHARS else ""


def _route_fetcher(source: str) -> Optional[JdFetcher]:
    """Pick the right per-source fetch coroutine.

    Purpose:
        Keep the source→fetcher mapping in one place so adding a new
        adapter is a one-line change and the outer wrapper stays small.
    Args:
        source: The lower-cased ``source`` column from ``job_postings``.
    Output:
        Matching fetcher, or ``None`` for sources we don't enrich
        (Greenhouse, JobSpy, Workday — already populated by their
        discovery paths).
    """

    if source.startswith("linkedin"):
        return _fetch_linkedin_jd
    if source.startswith("icims"):
        return _fetch_icims_jd
    return None


async def _maybe_enrich_job_description(
    *,
    db: DatabaseManager,
    job_row: dict[str, Any],
    job_hash: str,
) -> dict[str, Any]:
    """Opportunistically backfill a missing JD body before the tailor run.

    Purpose:
        Replace empty/placeholder descriptions with a freshly-fetched
        body so the tailor LLM has real text to work from.  The fetch
        result is also cached to ``job_postings.description`` for
        future runs.
    Args:
        db: Connected database manager used to write the cache update.
        job_row: The dict returned by ``get_resume_tailor_job_context``.
        job_hash: Stable job identifier used for the UPDATE statement.
    Output:
        Either the original ``job_row`` (when the existing description
        is usable, when no fetcher matches the source, or when the
        fetch failed or returned too little text) or a shallow copy
        with an updated ``description`` field.  Never raises.
    """

    if _description_is_usable(job_row.get("description")):
        return job_row

    source = (job_row.get("source") or "").lower()
    fetcher = _route_fetcher(source)
    if fetcher is None:
        return job_row

    source_url = job_row.get("source_url")
    try:
        fetched = await fetcher(source_url)
    except Exception as exc:
        # Backstop: the tailor pipeline must never fail because of an
        # enrichment error.  Per-source helpers already swallow their
        # own failures; this catch covers anything they re-raise.
        logger.warning(
            "JD enrichment raised for {} ({}): {}",
            job_hash,
            source,
            exc,
        )
        return job_row

    if not fetched or len(fetched) < MIN_ACCEPTABLE_FETCH_CHARS:
        logger.info(
            "JD enrichment skipped for {} ({}): fetched {} chars",
            job_hash,
            source,
            len(fetched) if fetched else 0,
        )
        return job_row

    try:
        await db.update_job_description(
            job_hash=job_hash,
            description=fetched,
        )
    except Exception as exc:
        # A cache-write failure should not block the in-progress tailor
        # run from using the body we already have in hand.
        logger.warning(
            "JD enrichment cache-write failed for {}: {}",
            job_hash,
            exc,
        )

    logger.info(
        "JD enrichment applied for {} ({}): {} chars",
        job_hash,
        source,
        len(fetched),
    )
    return {**job_row, "description": fetched}
