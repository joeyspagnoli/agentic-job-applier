"""Scrape job listings from LinkedIn's guest jobs API.

Uses LinkedIn's unauthenticated guest API to search for jobs with
configurable time filtering (``f_TPR``), experience level (``f_E``),
and work type (``f_WT``) parameters.  Includes built-in rate-limit
mitigation via random delays between page requests.

.. warning::
    LinkedIn actively rate-limits scrapers.  Use proxy support and
    conservative polling intervals to avoid IP blocks.
"""

from __future__ import annotations

import random
import re
from typing import Optional

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting

# LinkedIn guest jobs API endpoint (no auth required).
GUEST_JOBS_URL = "https://www.linkedin.com/jobs-guest/jobs/api/sJobsMore"

# LinkedIn job detail page (guest-accessible).
JOB_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

# Delay range between page requests to avoid detection (seconds).
MIN_DELAY_SECONDS = 3.0
MAX_DELAY_SECONDS = 7.0

# Maximum pages to fetch before stopping (each page has ~25 results).
DEFAULT_MAX_PAGES = 4
AGGRESSIVE_MAX_PAGES = 10

# LinkedIn experience level filter values.
EXPERIENCE_LEVELS: dict[str, int] = {
    "internship": 1,
    "entry": 2,
    "associate": 3,
    "mid-senior": 4,
    "director": 5,
    "executive": 6,
}

# LinkedIn work type filter values.
WORK_TYPES: dict[str, int] = {
    "on-site": 1,
    "remote": 2,
    "hybrid": 3,
}

RESULTS_PER_PAGE = 25


class LinkedInFetcher(BaseFetcher):
    """Scrape job listings from LinkedIn's guest jobs API.

    Attributes:
        search_term: The search query string.
        location: Geographic filter or ``"Remote"``.
        time_range_seconds: Value for the ``f_TPR`` parameter.
        experience_level: Filter for experience level (e.g. ``"internship"``).
        work_type: Filter for work type (e.g. ``"remote"``).
        max_pages: Maximum number of result pages to fetch.
        proxy_url: Optional HTTP proxy URL for request routing.
        fetch_descriptions: Whether to fetch full descriptions per job.
    """

    def __init__(
        self,
        search_term: str,
        *,
        location: str = "United States",
        time_range_seconds: int = 86400,
        experience_level: str | None = None,
        work_type: str | None = None,
        max_pages: int = DEFAULT_MAX_PAGES,
        proxy_url: str | None = None,
        fetch_descriptions: bool = False,
    ) -> None:
        """Configure the LinkedIn search parameters.

        Args:
            search_term: Job search query (e.g. ``"software intern"``).
            location: Geographic location filter.
            time_range_seconds: Time filter in seconds (e.g. 3600 for last
                hour, 86400 for last day).  Maps to LinkedIn's ``f_TPR``
                parameter.
            experience_level: One of ``"internship"``, ``"entry"``,
                ``"associate"``, ``"mid-senior"``, ``"director"``,
                ``"executive"``.
            work_type: One of ``"on-site"``, ``"remote"``, ``"hybrid"``.
            max_pages: Maximum pages to scrape (each ~25 results).
            proxy_url: Optional proxy URL (e.g. ``"http://proxy:8080"``).
            fetch_descriptions: Fetch full job descriptions (slower, more
                requests).
        """
        self.search_term = search_term
        self.location = location
        self.time_range_seconds = time_range_seconds
        self.experience_level = experience_level
        self.work_type = work_type
        self.max_pages = max_pages
        self.proxy_url = proxy_url
        self.fetch_descriptions = fetch_descriptions
        self._client: Optional[httpx.AsyncClient] = None
        super().__init__(
            config={
                "search_term": search_term,
                "location": location,
            },
        )

    def get_source_name(self) -> str:
        """Return the stable source identifier for this LinkedIn search.

        Returns:
            A machine-friendly source string.
        """
        slug = re.sub(r"[^a-z0-9]+", "_", self.search_term.lower())[:30]
        return f"linkedin_{slug}"

    async def __aenter__(self) -> LinkedInFetcher:
        """Create the shared HTTP client with browser-like headers.

        Returns:
            The fetcher instance with an active HTTP client.
        """
        transport = None
        if self.proxy_url:
            transport = httpx.AsyncHTTPTransport(proxy=self.proxy_url)

        self._client = httpx.AsyncClient(
            timeout=30.0,
            transport=transport,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Close the HTTP client when the context ends."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_jobs(self) -> list[JobPosting]:
        """Scrape job listings from LinkedIn's guest API.

        Paginates through results with random delays between pages.
        Stops early when rate-limited (HTTP 429) or when a page returns
        no results.

        Returns:
            A list of normalized :class:`JobPosting` objects.
        """
        if not self._client:
            # Fallback when used without `async with`.
            await self.__aenter__()

        all_jobs: list[JobPosting] = []

        for page in range(self.max_pages):
            start = page * RESULTS_PER_PAGE
            params = self._build_params(start)

            try:
                client = self._client
                if client is None:
                    raise RuntimeError("LinkedIn HTTP client was not initialized")
                response = await client.get(GUEST_JOBS_URL, params=params)
            except httpx.RequestError as exc:
                logger.error("LinkedIn network error on page {}: {}", page, exc)
                break

            if response.status_code == 429:
                logger.warning(
                    "LinkedIn rate limited on page {} — returning {} jobs collected so far",
                    page,
                    len(all_jobs),
                )
                break

            if response.status_code != 200:
                logger.warning(
                    "LinkedIn returned {} on page {}",
                    response.status_code,
                    page,
                )
                break

            page_jobs = self._parse_job_cards(response.text)
            if not page_jobs:
                logger.debug("No more LinkedIn results after page {}", page)
                break

            all_jobs.extend(page_jobs)
            logger.debug(
                "LinkedIn page {}: {} jobs (total: {})",
                page,
                len(page_jobs),
                len(all_jobs),
            )

            # Random delay between pages to avoid detection.
            if page < self.max_pages - 1:
                import asyncio

                delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
                await asyncio.sleep(delay)

        logger.info(
            "LinkedIn search '{}': {} jobs across {} pages",
            self.search_term,
            len(all_jobs),
            min(self.max_pages, len(all_jobs) // RESULTS_PER_PAGE + 1),
        )
        return all_jobs

    def _build_params(self, start: int) -> dict[str, str]:
        """Build the query parameters for a LinkedIn guest API request.

        Args:
            start: The result offset for pagination.

        Returns:
            A mapping of query parameter names to values.
        """
        params: dict[str, str] = {
            "keywords": self.search_term,
            "location": self.location,
            "start": str(start),
            "f_TPR": f"r{self.time_range_seconds}",
        }

        if self.experience_level:
            level_code = EXPERIENCE_LEVELS.get(self.experience_level.lower())
            if level_code is not None:
                params["f_E"] = str(level_code)

        if self.work_type:
            wt_code = WORK_TYPES.get(self.work_type.lower())
            if wt_code is not None:
                params["f_WT"] = str(wt_code)

        return params

    def _parse_job_cards(self, html: str) -> list[JobPosting]:
        """Parse job card elements from LinkedIn's guest API HTML response.

        LinkedIn's guest API returns HTML fragments containing ``<li>``
        elements with job card data.  This parser extracts structured
        data from the HTML using regex patterns (avoiding a BeautifulSoup
        dependency for lightweight operation).

        Args:
            html: Raw HTML response from the LinkedIn guest API.

        Returns:
            A list of :class:`JobPosting` instances parsed from the HTML.
        """
        jobs: list[JobPosting] = []

        # Each job card is wrapped in a base-card element.
        card_pattern = re.compile(
            r'<div[^>]*class="[^"]*base-card[^"]*"[^>]*>(.+?)</div>\s*</li>',
            re.DOTALL,
        )

        for card_match in card_pattern.finditer(html):
            card_html = card_match.group(0)
            try:
                job = self._parse_single_card(card_html)
                if job is not None:
                    jobs.append(job)
            except Exception as exc:
                logger.debug("Failed to parse LinkedIn card: {}", exc)

        return jobs

    def _parse_single_card(self, card_html: str) -> JobPosting | None:
        """Parse a single job card HTML fragment into a :class:`JobPosting`.

        Args:
            card_html: HTML fragment for one job card.

        Returns:
            A :class:`JobPosting` if the card contains enough data, or
            ``None`` if essential fields are missing.
        """
        # Extract job URL and ID.
        url_match = re.search(
            r'href="(https://www\.linkedin\.com/jobs/view/[^"?]+)',
            card_html,
        )
        job_url = url_match.group(1) if url_match else ""

        job_id_match = re.search(r"/jobs/view/(\d+)", job_url)
        job_id = job_id_match.group(1) if job_id_match else ""

        # Extract title.
        title_match = re.search(
            r'class="[^"]*base-search-card__title[^"]*"[^>]*>([^<]+)',
            card_html,
        )
        title = title_match.group(1).strip() if title_match else ""

        if not title:
            return None

        # Extract company name.
        company_match = re.search(
            r'class="[^"]*base-search-card__subtitle[^"]*"[^>]*>'
            r'\s*<a[^>]*>([^<]+)',
            card_html,
            re.DOTALL,
        )
        if not company_match:
            company_match = re.search(
                r'class="[^"]*base-search-card__subtitle[^"]*"[^>]*>([^<]+)',
                card_html,
            )
        company = company_match.group(1).strip() if company_match else "Unknown"

        # Extract location.
        location_match = re.search(
            r'class="[^"]*job-search-card__location[^"]*"[^>]*>([^<]+)',
            card_html,
        )
        location = location_match.group(1).strip() if location_match else ""

        # Extract posted date.
        date_match = re.search(
            r'<time[^>]*datetime="([^"]+)"',
            card_html,
        )
        posted_date = date_match.group(1) if date_match else None

        return JobPosting(
            source=self.get_source_name(),
            source_url=job_url,
            company=company,
            title=title,
            location=location,
            posted_date=posted_date,
            description=f"LinkedIn job posting: {title} at {company}",
            raw_data={"job_id": job_id, "card_html_length": len(card_html)},
        )
