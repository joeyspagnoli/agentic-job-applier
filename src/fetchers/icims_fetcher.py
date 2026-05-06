"""Fetch and normalize jobs from iCIMS ATS career portals.

iCIMS is a proprietary ATS used by healthcare systems, retail chains,
universities, and financial services companies. Career portals live on
subdomains such as ``jobs-dollargeneral.icims.com`` or
``careers-phc.icims.com``.

The free scraping path hits the paginated HTML listing endpoint directly:

    GET https://{subdomain}.icims.com/jobs/search?ss=1&pr={page}&in_iframe=1

``?in_iframe=1`` strips the page navigation wrapper, yielding cleaner HTML.
``&pr=N`` is the 0-indexed page number. Pagination stops when a page yields
no new job IDs or the ``PAGE_CAP`` is reached.

Job titles and apply URLs are extracted via three module-level regex patterns
adapted from the stapply-ai/ats-scrapers open-source reference implementation
(⭐34, verified against 83k real iCIMS job postings).
"""

from __future__ import annotations

import asyncio
import html
import re
from types import TracebackType

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.fetchers.errors import FetchError
from src.models.job_posting import JobPosting


PAGE_CAP = 200
"""Hard limit on paginated requests per company (≈ 5 000 jobs at 25/page)."""

MAX_RETRIES = 3
"""Attempts before a rate-limited or server-error page is treated as fail-soft."""

RETRY_BASE_DELAY = 1.5
"""Base delay (seconds) for exponential back-off on 429 / 5xx responses."""

INTER_PAGE_SLEEP = 0.5
"""Polite delay (seconds) between paginated requests to avoid hammering tenants."""

REQUEST_TIMEOUT = 30.0

USER_AGENT = (
    "Mozilla/5.0 (compatible; agentic-job-applier/1.0;"
    " +https://github.com/joeyspagnoli/agentic-job-applier)"
)

# Regex patterns adapted from stapply-ai/ats-scrapers (MIT, ⭐34).
# Matched against raw HTML from iCIMS listing pages; verified against 83k real postings.
_JOB_ANCHOR_RE = re.compile(
    r'<a[^>]+href="(?P<href>https?://[^"]*?/jobs/(?P<id>\d+)/[^"]*?/job[^"]*)"[^>]*'
    r'class="iCIMS_Anchor"[^>]*>'
    r"(?P<inner>.*?)</a>",
    re.DOTALL | re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<h3[^>]*>(?P<title>.*?)</h3>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


class ICIMSFetcher(BaseFetcher):
    """Fetch job postings from a public iCIMS career portal via HTML scraping.

    iCIMS has no free public JSON API; the only credential-free path is the
    paginated HTML listing endpoint with ``?in_iframe=1``. Titles and apply
    URLs are extracted via regex, matching the stapply-ai/ats-scrapers reference
    implementation. One instance is created per company.

    Attributes:
        company_name: Human-readable company label used in logs and job records.
        base_url: Resolved HTTPS base URL for the iCIMS subdomain.

    Example:
        async with ICIMSFetcher("Dollar General", "jobs-dollargeneral.icims.com") as f:
            jobs = await f.fetch_jobs()
    """

    def __init__(
        self,
        company_name: str,
        icims_subdomain: str,
        *,
        timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        """Store the company label and resolve the base URL from its subdomain.

        Args:
            company_name: Human-readable company name used in logs and job records.
            icims_subdomain: Bare subdomain such as ``jobs-dollargeneral.icims.com``
                or a full HTTPS URL. The fetcher prepends ``https://`` when bare.
            timeout: HTTP request timeout in seconds. Defaults to ``REQUEST_TIMEOUT``.
        """
        self.company_name = company_name
        self.base_url = _resolve_base_url(icims_subdomain)
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

        super().__init__(
            config={
                "company": company_name,
                "icims_subdomain": icims_subdomain,
                "base_url": self.base_url,
            }
        )

    def get_source_name(self) -> str:
        """Return the stable source identifier recorded on iCIMS job postings.

        Returns:
            A machine-friendly source identifier, e.g. ``"icims_dollar_general"``.
        """
        return f"icims_{self.company_name.lower().replace(' ', '_')}"

    async def __aenter__(self) -> "ICIMSFetcher":
        """Create the shared HTTP client used during the crawl.

        Returns:
            The fetcher instance after creating the HTTP client.
        """
        self._client = _build_client(self._timeout)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the shared HTTP client when the crawl context ends.

        Args:
            exc_type: Exception type raised inside the context, if any.
            exc_val: Exception instance raised inside the context, if any.
            exc_tb: Traceback for the exception raised inside the context.
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_jobs(self) -> list[JobPosting]:
        """Paginate the iCIMS listing endpoint and return normalized postings.

        Iterates pages until a page yields no new job IDs or ``PAGE_CAP`` is
        reached. 404 and rate-limit responses are treated as fail-soft: a
        warning is logged and an empty list is returned. Transport errors
        raise ``FetchError``.

        Returns:
            A list of normalized ``JobPosting`` records. Returns an empty list
            when the subdomain returns 404 (misconfigured entry) or is
            rate-limited past retries.

        Raises:
            FetchError: When a transport error prevents any listing page from
                being retrieved.
        """
        if self._client is None:
            self._client = _build_client(self._timeout)

        seen: set[str] = set()
        all_jobs: list[JobPosting] = []

        for page_num in range(PAGE_CAP):
            html_text = await self._fetch_page(page=page_num)
            if html_text is None:
                break

            page_jobs = self._parse_page(html_text)
            new = [j for j in page_jobs if _ats_id(j) not in seen]
            if not new:
                break

            for job in new:
                seen.add(_ats_id(job))
            all_jobs.extend(new)

            if page_num < PAGE_CAP - 1:
                await asyncio.sleep(INTER_PAGE_SLEEP)
        else:
            if all_jobs:
                logger.warning(
                    "iCIMS page cap ({}) reached for {}; stopping pagination",
                    PAGE_CAP,
                    self.company_name,
                )

        logger.debug(
            "Fetched {} jobs from iCIMS {} ({})",
            len(all_jobs),
            self.base_url,
            self.company_name,
        )
        return all_jobs

    async def _fetch_page(self, *, page: int) -> str | None:
        """Fetch a single iCIMS listing page with retry on 429 / 5xx.

        Args:
            page: 0-indexed page number passed as the ``pr`` query parameter.

        Returns:
            The response HTML on success, or ``None`` when the page should be
            treated as fail-soft (404, exhausted 429 / 5xx retries).

        Raises:
            FetchError: When a transport error prevents the request.
        """
        client = self._client
        if client is None:
            raise FetchError("iCIMS HTTP client was not initialized")

        url = f"{self.base_url}/jobs/search"
        params = {"ss": "1", "pr": str(page), "in_iframe": "1"}

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.get(
                    url,
                    params=params,
                    headers={"User-Agent": USER_AGENT},
                )
            except httpx.RequestError as exc:
                raise FetchError(
                    f"Network error fetching iCIMS {self.company_name} page={page}: {exc}"
                ) from exc

            status = response.status_code

            if status == 404:
                logger.warning(
                    "iCIMS subdomain not found for {} ({}); skipping",
                    self.company_name,
                    self.base_url,
                )
                return None

            if status == 200:
                return response.text

            if status == 429 or 500 <= status < 600:
                if attempt == MAX_RETRIES:
                    logger.warning(
                        "iCIMS returned {} for {} at page={} after {} retries; skipping",
                        status,
                        self.company_name,
                        page,
                        MAX_RETRIES,
                    )
                    return None
                retry_after = response.headers.get("Retry-After", "")
                delay = (
                    float(retry_after)
                    if retry_after.isdigit()
                    else RETRY_BASE_DELAY * (2**attempt)
                )
                await asyncio.sleep(delay)
                continue

            raise FetchError(
                f"Unexpected HTTP {status} from iCIMS {self.company_name} at page={page}"
            )

        return None  # exhausted retries

    def _parse_page(self, html_text: str) -> list[JobPosting]:
        """Extract job postings from a single iCIMS listing page.

        Deduplicates within the page because iCIMS sometimes renders multiple
        anchors per job (title link + icon link) sharing the same job ID.

        Args:
            html_text: Raw HTML from the ``/jobs/search?in_iframe=1`` endpoint.

        Returns:
            A list of ``JobPosting`` objects parsed from the page.
        """
        jobs: list[JobPosting] = []
        seen_in_page: set[str] = set()

        for match in _JOB_ANCHOR_RE.finditer(html_text):
            ats_id = match.group("id")
            if ats_id in seen_in_page:
                continue
            seen_in_page.add(ats_id)

            href = html.unescape(match.group("href"))
            inner = match.group("inner")

            title_match = _TITLE_RE.search(inner)
            if not title_match:
                continue

            title = _strip(title_match.group("title"))
            if not title:
                continue

            jobs.append(
                JobPosting(
                    source=self.get_source_name(),
                    source_url=href,
                    company=self.company_name,
                    company_url=self.base_url,
                    title=title,
                    location=None,
                    description="",
                    posted_date=None,
                    raw_data={"ats_id": ats_id, "base_url": self.base_url},
                )
            )

        return jobs


def _resolve_base_url(subdomain: str) -> str:
    """Prepend ``https://`` to a bare subdomain or pass through a full HTTPS URL.

    Args:
        subdomain: Bare subdomain such as ``jobs-dollargeneral.icims.com`` or a
            full URL such as ``https://uscareers-nyu.icims.com``.

    Returns:
        A full HTTPS URL with no trailing slash.
    """
    if subdomain.startswith(("http://", "https://")):
        return subdomain.rstrip("/")
    return f"https://{subdomain.rstrip('/')}"


def _build_client(timeout: float) -> httpx.AsyncClient:
    """Create the configured HTTP client for iCIMS listing requests.

    Args:
        timeout: Request timeout in seconds.

    Returns:
        A configured ``httpx.AsyncClient`` with redirect following enabled.
    """
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
    )


def _ats_id(posting: JobPosting) -> str:
    """Extract the iCIMS ATS job ID from ``raw_data`` for cross-page deduplication.

    Args:
        posting: A job posting produced by ``ICIMSFetcher._parse_page``.

    Returns:
        The ATS job ID string from ``raw_data``, or the ``source_url`` as fallback.
    """
    return str(posting.raw_data.get("ats_id", posting.source_url))


def _strip(text: str) -> str:
    """Strip HTML tags, unescape entities, and collapse whitespace.

    Args:
        text: Raw inner HTML string from inside a title element.

    Returns:
        Clean plain-text string suitable for storage.
    """
    cleaned = _TAG_RE.sub(" ", text)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()
