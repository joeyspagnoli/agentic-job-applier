"""Fetch and normalize jobs from Taleo Enterprise career portals.

Taleo Enterprise exposes an undocumented AJAX endpoint at
``/careersection/rest/jobboard/searchjobs`` that returns JSON.  Three headers
are mandatory — omitting any causes an HTTP 500 or an HTML fallback instead of
JSON: ``X-Requested-With``, ``tz``, and ``tzname``.

Most tenants also require a ``?portal={portal_id}`` query parameter discovered
by scraping the career section landing page HTML.
"""

from __future__ import annotations

import asyncio
import json
import re
from types import TracebackType
from typing import Optional
from urllib.parse import quote

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.fetchers.errors import FetchError
from src.models.job_posting import JobPosting

_PORTAL_ID_RE = re.compile(
    r'["\']?portalId["\']?\s*[=:]\s*["\']?(\d+)',
)


def _normalize_company_name(name: str) -> str:
    """Normalize a company name into a snake_case source identifier segment.

    Purpose:
        Produce a stable, human-readable fragment for the ``source`` field so
        all Taleo jobs from one company share a consistent identifier prefix.
    Args:
        name: Raw company name string.
    Output:
        Returns a lowercase snake_case string with ``&`` expanded to ``and``
        and punctuation characters stripped.
    """
    name = name.lower()
    name = name.replace("&", "and")
    name = re.sub(r"[,.()\-]+", "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return re.sub(r"_+", "_", name)


def _clean_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace from a raw HTML string.

    Purpose:
        Produce a plain-text description suitable for hashing, storage, and
        downstream prompt construction.
    Args:
        html: Raw HTML string to clean.
    Output:
        Returns the cleaned plain-text string.
    """
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("<", " ").replace(">", " ")
    return re.sub(r"\s+", " ", text).strip()


def _extract_div_content(html_text: str, div_id: str) -> str:
    """Extract the inner HTML of the first div with the given id attribute.

    Purpose:
        Isolate a named div's content from a full HTML page without requiring
        an external HTML parser.  Uses a depth counter so nested divs are
        handled correctly.
    Args:
        html_text: Full HTML page source.
        div_id: Value of the ``id`` attribute to search for.
    Output:
        Returns the raw inner HTML of the matching div, or an empty string
        when the div is not found or the document is malformed.
    """
    pattern = re.compile(
        r"<div\b[^>]*\bid=[\"']?" + re.escape(div_id) + r"[\"']?[^>]*>",
        re.IGNORECASE,
    )
    m = pattern.search(html_text)
    if not m:
        return ""

    content_start = m.end()
    pos = content_start
    depth = 1

    while depth > 0:
        next_open = html_text.find("<div", pos)
        next_close = html_text.find("</div", pos)

        if next_close == -1:
            # Unclosed div — return all remaining content.
            return html_text[content_start:]

        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + 4
        else:
            depth -= 1
            if depth == 0:
                return html_text[content_start:next_close]
            pos = next_close + 6

    return ""


class TaleoFetcher(BaseFetcher):
    """Fetch job postings from a Taleo Enterprise career portal.

    Purpose:
        Paginate the undocumented Taleo JSON search endpoint, enrich each job
        with a plain-text description fetched from the detail HTML page, and
        return normalized ``JobPosting`` records for the pipeline.
    """

    PAGE_SIZE = 25
    """Taleo's default and typical max page size."""

    PAGE_CAP = 150
    """Hard limit on paginated requests per company (≈ 3 750 jobs)."""

    INTER_PAGE_SLEEP = 0.5
    """Polite delay (seconds) between consecutive page POSTs."""

    DETAIL_CONCURRENCY = 5
    """Maximum concurrent detail-page GETs per listing page."""

    REQUEST_TIMEOUT = 30.0

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        company_name: str,
        tenant_id: str,
        career_section: str,
        *,
        portal_id: str | None = None,
    ) -> None:
        """Store Taleo portal metadata needed to construct API calls.

        Purpose:
            Capture the company label, tenant slug, and career section so every
            request method has the context it needs without accepting extra args.
        Args:
            self: The fetcher instance being initialized.
            company_name: Human-readable company name for logging and job records.
            tenant_id: Taleo tenant subdomain (e.g. ``"boeing"``).
            career_section: Taleo career section ID (e.g. ``"exm"`` or ``"10161"``).
            portal_id: Pre-discovered portal ID for the ``?portal=`` query param.
                When ``None``, the fetcher discovers it at runtime via HTML scrape.
        Output:
            Returns ``None`` after caching metadata.
        """
        self.company_name = company_name
        self.tenant_id = tenant_id
        self.career_section = career_section
        self._portal_id = portal_id
        self._client: Optional[httpx.AsyncClient] = None

        super().__init__(
            config={
                "company": company_name,
                "tenant_id": tenant_id,
                "career_section": career_section,
            }
        )

    def get_source_name(self) -> str:
        """Return the source identifier for Taleo jobs.

        Purpose:
            Provide a stable, human-readable source label for crawl history and
            persisted job rows originating from this Taleo portal.
        Args:
            self: The fetcher reporting its source name.
        Output:
            Returns a machine-friendly source identifier string such as
            ``"taleo_morgan_stanley"``.
        """
        return f"taleo_{_normalize_company_name(self.company_name)}"

    async def __aenter__(self) -> "TaleoFetcher":
        """Create the shared HTTP client used during the crawl.

        Purpose:
            Reuse a single async client across every listing and detail request
            so connection pooling stays consistent.
        Args:
            self: The fetcher entering the async context.
        Output:
            Returns the fetcher instance after creating the HTTP client.
        """
        self._client = httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the shared HTTP client when the crawl context ends.

        Purpose:
            Release network resources once the caller exits the async context.
        Args:
            self: The fetcher exiting the async context.
            exc_type: Exception type raised inside the context, if any.
            exc_val: Exception instance raised inside the context, if any.
            exc_tb: Traceback for the exception raised inside the context.
        Output:
            Returns ``None`` after closing and clearing the HTTP client.
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _discover_portal_id(self) -> str | None:
        """Discover the portal ID by scraping the career section landing page.

        Purpose:
            Extract the tenant-specific ``portalId`` embedded in the career
            section HTML.  This value is required as a ``?portal=`` query param
            on the job search endpoint for most Taleo tenants.
        Args:
            self: The fetcher issuing the discovery request.
        Output:
            Returns the discovered portal ID string, or ``None`` when not found
            or the request fails.
        """
        client = self._client
        if client is None:
            return None

        section_encoded = quote(self.career_section, safe="")
        url = (
            f"https://{self.tenant_id}.taleo.net"
            f"/careersection/{section_encoded}/jobsearch.ftl?lang=en"
        )
        try:
            resp = await client.get(url)
        except httpx.RequestError:
            return None

        if resp.status_code != 200:
            return None

        match = _PORTAL_ID_RE.search(resp.text)
        if match:
            portal_id = match.group(1)
            logger.warning(
                'Taleo: discovered portalId={} for {} — add portal_id: "{}" to companies.yaml',
                portal_id,
                self.company_name,
                portal_id,
            )
            return portal_id
        return None

    def _build_url(self, portal_id: str | None) -> str:
        """Build the Taleo job search REST endpoint URL.

        Purpose:
            Produce the full endpoint URL, appending the portal query param
            when a portal ID is available.
        Args:
            self: The fetcher constructing the URL.
            portal_id: Portal ID for the ``?portal=`` param, or ``None``.
        Output:
            Returns the constructed endpoint URL string.
        """
        base = (
            f"https://{self.tenant_id}.taleo.net"
            "/careersection/rest/jobboard/searchjobs?lang=en"
        )
        if portal_id:
            return f"{base}&portal={portal_id}"
        return base

    def _build_headers(self) -> dict[str, str]:
        """Build the required headers for Taleo AJAX requests.

        Purpose:
            Assemble the full header set that Taleo's REST endpoint requires.
            Omitting ``X-Requested-With``, ``tz``, or ``tzname`` causes HTTP 500
            or an HTML response instead of JSON.
        Args:
            self: The fetcher building request headers.
        Output:
            Returns a dict of required HTTP headers.
        """
        section_encoded = quote(self.career_section, safe="")
        return {
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "tz": "GMT-04:00",
            "tzname": "America/New_York",
            "Referer": (
                f"https://{self.tenant_id}.taleo.net"
                f"/careersection/{section_encoded}/jobsearch.ftl?lang=en"
            ),
            "Origin": f"https://{self.tenant_id}.taleo.net",
            "User-Agent": self.USER_AGENT,
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }

    def _build_payload(self, page_no: int) -> dict[str, object]:
        """Build the Taleo job search POST payload for a given page.

        Purpose:
            Produce the JSON body required by the search endpoint, using empty
            keyword fields so the fetcher retrieves all available jobs.  The
            filter pipeline — not the ATS — is responsible for filtering.
        Args:
            self: The fetcher building the payload.
            page_no: 1-indexed page number for the current request.
        Output:
            Returns the JSON-serializable payload dict.
        """
        return {
            "pageNo": page_no,
            "multilineEnabled": True,
            "sortingSelection": {
                "sortBySelectionParam": "1",
                "ascendingSortingOrder": "false",
            },
            "fieldData": {
                "fields": {"KEYWORD": "", "LOCATION": "", "JOB_TITLE": ""},
                "valid": True,
            },
            "filterSelectionParam": {"searchFilterSelections": []},
            "advancedSearchFiltersSelectionParam": {"searchFilterSelections": []},
        }

    async def _fetch_description(self, contest_no: str) -> str:
        """Fetch the plain-text description for a single job posting.

        Purpose:
            Pull the full job description from the detail HTML page so the
            filter pipeline and gate agent can score it.  Failures are
            swallowed individually so one bad listing does not abort the crawl.
        Args:
            self: The fetcher issuing the detail request.
            contest_no: Taleo requisition contest number.
        Output:
            Returns the cleaned plain-text description, or an empty string on
            any fetch or parse error.
        """
        client = self._client
        if client is None:
            return ""

        section_encoded = quote(self.career_section, safe="")
        url = (
            f"https://{self.tenant_id}.taleo.net"
            f"/careersection/{section_encoded}/jobdetail.ftl"
            f"?job={contest_no}&lang=en"
        )
        try:
            resp = await client.get(url)
        except httpx.RequestError as exc:
            logger.debug(
                "Taleo detail network error for {} (job={}): {}",
                self.company_name,
                contest_no,
                exc,
            )
            return ""

        if resp.status_code != 200:
            logger.debug(
                "Taleo detail returned HTTP {} for {} (job={})",
                resp.status_code,
                self.company_name,
                contest_no,
            )
            return ""

        try:
            inner_html = _extract_div_content(resp.text, "jobDescription")
            return _clean_html(inner_html)
        except Exception:
            return ""

    def _parse_location(self, raw: str) -> str | None:
        """Parse a JSON-encoded Taleo location string into a readable label.

        Purpose:
            Decode the ``column[3]`` value from a listing entry, which Taleo
            encodes as a JSON object ``{"city": ..., "state": ..., "country":
            ...}``.
        Args:
            self: The fetcher performing the parse.
            raw: Raw column value from a Taleo listing entry.
        Output:
            Returns a human-readable ``"City, State, Country"`` string, the raw
            input string when JSON decoding fails, or ``None`` when raw is empty.
        """
        if not raw:
            return None
        try:
            loc = json.loads(raw)
            parts = [
                str(loc.get("city", "") or ""),
                str(loc.get("state", "") or ""),
                str(loc.get("country", "") or ""),
            ]
            label = ", ".join(p for p in parts if p)
            return label if label else raw
        except (json.JSONDecodeError, AttributeError, TypeError):
            return raw

    def _parse_job(
        self,
        raw: dict[str, object],
        *,
        contest_no: str,
        description: str = "",
    ) -> JobPosting:
        """Convert a Taleo requisition entry into a normalized JobPosting.

        Purpose:
            Map the positional ``column`` array to semantic fields, falling back
            gracefully when individual entries are missing or the array is shorter
            than expected.
        Args:
            self: The fetcher performing the normalization.
            raw: Raw entry from ``requisitionList`` in the search response.
            contest_no: Taleo requisition contest number.
            description: Pre-fetched plain-text job description.
        Output:
            Returns a normalized ``JobPosting``.
        """
        col = raw.get("column")
        if not isinstance(col, list):
            col = []

        def _col(idx: int) -> str:
            return str(col[idx]) if len(col) > idx and col[idx] else ""

        title = _col(0) or "Unknown Title"
        location_raw = _col(3)
        posted_date = _col(5) or None

        section_encoded = quote(self.career_section, safe="")
        source_url = (
            f"https://{self.tenant_id}.taleo.net"
            f"/careersection/{section_encoded}/jobdetail.ftl"
            f"?job={contest_no}&lang=en"
        )

        return JobPosting(
            source=self.get_source_name(),
            source_url=source_url,
            company=self.company_name,
            company_url=f"https://{self.tenant_id}.taleo.net",
            title=title,
            location=self._parse_location(location_raw),
            description=description,
            posted_date=posted_date,
            raw_data=dict(raw),
        )

    async def _fetch_page(
        self,
        url: str,
        headers: dict[str, str],
        page_no: int,
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        """Fetch a single listing page from the Taleo search endpoint.

        Purpose:
            Issue one POST to the search endpoint and return the raw job list
            alongside the paging metadata object.
        Args:
            self: The fetcher issuing the request.
            url: Full search endpoint URL including any portal query param.
            headers: Required AJAX headers for the request.
            page_no: 1-indexed page number.
        Output:
            Returns a tuple of ``(raw_jobs, paging_data)`` where ``raw_jobs``
            is the ``requisitionList`` array and ``paging_data`` is the
            ``pagingData`` object from the response.
        Raises:
            FetchError: When a network error, non-200 status, or non-JSON body
                makes the crawl unrecoverable.
        """
        assert self._client is not None
        payload = self._build_payload(page_no)

        try:
            resp = await self._client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise FetchError(
                f"Network error fetching Taleo {self.company_name}: {exc}"
            ) from exc

        if resp.status_code != 200:
            raise FetchError(
                f"Taleo returned HTTP {resp.status_code} for {self.company_name}"
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise FetchError(
                f"Non-JSON response from Taleo {self.company_name}: {exc}"
            ) from exc

        raw_jobs = data.get("requisitionList") or []
        paging = data.get("pagingData") or {}
        return raw_jobs, paging

    async def _process_page(
        self,
        raw_jobs: list[dict[str, object]],
        semaphore: asyncio.Semaphore,
    ) -> list[JobPosting]:
        """Fetch descriptions for a page's jobs concurrently and normalize them.

        Purpose:
            Parallelize detail fetches for all jobs on one listing page while
            respecting the per-page concurrency limit, then convert each raw
            entry into a normalized ``JobPosting``.
        Args:
            self: The fetcher processing the page.
            raw_jobs: List of raw requisition entries from ``requisitionList``.
            semaphore: Semaphore limiting concurrent detail-page GETs.
        Output:
            Returns a list of normalized ``JobPosting`` objects, one per valid
            raw entry.
        """
        contest_nos = [str(j.get("contestNo", "")) for j in raw_jobs if isinstance(j, dict)]

        async def _fetch_with_limit(cn: str) -> str:
            """Fetch one description slot-limited by the shared semaphore."""
            async with semaphore:
                return await self._fetch_description(cn)

        descriptions = list(
            await asyncio.gather(*[_fetch_with_limit(cn) for cn in contest_nos])
        )

        postings: list[JobPosting] = []
        for raw_job, contest_no, description in zip(raw_jobs, contest_nos, descriptions):
            if not isinstance(raw_job, dict):
                continue
            postings.append(
                self._parse_job(raw_job, contest_no=contest_no, description=description)
            )
        return postings

    async def fetch_jobs(self) -> list[JobPosting]:
        """Paginate the Taleo Enterprise search endpoint and normalize results.

        Purpose:
            Drive the full crawl flow: discover portal ID when absent, paginate
            all listing pages, fetch descriptions concurrently per page, and
            return all normalized postings.
        Args:
            self: The fetcher performing the crawl.
        Output:
            Returns a list of normalized ``JobPosting`` records.
        Raises:
            FetchError: When the search endpoint returns an unexpected HTTP
                status, a non-JSON body, or a network error that prevents the
                crawl from completing.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT)

        portal_id = self._portal_id or await self._discover_portal_id()
        url = self._build_url(portal_id)
        headers = self._build_headers()
        semaphore = asyncio.Semaphore(self.DETAIL_CONCURRENCY)

        all_jobs: list[JobPosting] = []
        page_no = 1
        page_size = self.PAGE_SIZE
        total_count: int | None = None

        while page_no <= self.PAGE_CAP:
            raw_jobs, paging = await self._fetch_page(url, headers, page_no)

            if total_count is None:
                raw_total = paging.get("totalCount")
                total_count = raw_total if isinstance(raw_total, int) else 0
                raw_size = paging.get("pageSize")
                page_size = raw_size if isinstance(raw_size, int) else self.PAGE_SIZE

            if not raw_jobs:
                break

            all_jobs.extend(await self._process_page(raw_jobs, semaphore))

            fetched_so_far = (page_no - 1) * page_size + len(raw_jobs)
            if total_count is not None and fetched_so_far >= total_count:
                break

            page_no += 1
            await asyncio.sleep(self.INTER_PAGE_SLEEP)

        if page_no > self.PAGE_CAP:
            logger.warning(
                "Taleo page cap ({}) reached for {}; stopping pagination",
                self.PAGE_CAP,
                self.company_name,
            )

        logger.debug(
            "Fetched {} jobs from Taleo tenant {} ({})",
            len(all_jobs),
            self.tenant_id,
            self.company_name,
        )
        return all_jobs
