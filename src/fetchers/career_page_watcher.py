"""Monitor arbitrary company career pages for new job postings.

Periodically fetches a career page URL, extracts job links using a
configurable CSS-selector-like pattern or regex, and diffs against the
previously seen link set to detect new postings.

Requires ``beautifulsoup4`` for HTML parsing.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional
from urllib.parse import urljoin

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting

try:
    from bs4 import BeautifulSoup

    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False
    if TYPE_CHECKING:
        from bs4 import BeautifulSoup  # type: ignore[assignment]


class CareerPageWatcher(BaseFetcher):
    """Watch a company career page for new job listing links.

    Extracts job links from the page using either a CSS selector or a
    regex pattern, then creates minimal :class:`JobPosting` entries for
    each new link discovered since the last check.

    Attributes:
        company_name: Human-readable company label.
        page_url: The career page URL to monitor.
        link_selector: CSS selector for extracting job links.
        link_pattern: Regex pattern alternative to CSS selector.
        previous_urls: Set of URLs seen on the previous check.
    """

    def __init__(
        self,
        company_name: str,
        page_url: str,
        *,
        link_selector: str = "a[href*='/jobs/']",
        link_pattern: str | None = None,
    ) -> None:
        """Configure the career page watcher.

        Args:
            company_name: Human-readable company name.
            page_url: The URL of the company's career page.
            link_selector: CSS selector to find job links (default:
                ``a[href*='/jobs/']``).  Requires ``beautifulsoup4``.
            link_pattern: Regex pattern to extract job URLs from the
                page HTML.  Used as a fallback when ``beautifulsoup4``
                is not installed, or as the primary method when specified.
        """
        self.company_name = company_name
        self.page_url = page_url
        self.link_selector = link_selector
        self.link_pattern = link_pattern
        self.previous_urls: set[str] = set()
        self._client: Optional[httpx.AsyncClient] = None
        super().__init__(
            config={
                "company": company_name,
                "url": page_url,
            },
        )

    def get_source_name(self) -> str:
        """Return the stable source identifier for this career page.

        Returns:
            A machine-friendly source string.
        """
        slug = re.sub(r"[^a-z0-9]+", "_", self.company_name.lower())
        return f"career_page_{slug}"

    async def __aenter__(self) -> CareerPageWatcher:
        """Create the shared HTTP client with browser-like headers.

        Returns:
            The fetcher instance with an active HTTP client.
        """
        self._client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html",
            },
        )
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: object,
    ) -> None:
        """Close the HTTP client when the context ends."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def set_previous_urls(self, urls: set[str]) -> None:
        """Load previously seen URLs for diffing against the next fetch.

        Args:
            urls: Set of absolute URLs from the previous check.
        """
        self.previous_urls = urls

    async def fetch_jobs(self) -> list[JobPosting]:
        """Fetch the career page and detect new job links.

        Extracts all job links from the page, diffs against
        :attr:`previous_urls`, and creates :class:`JobPosting` entries
        for each new link.

        Returns:
            A list of :class:`JobPosting` objects for newly discovered
            job links.  Returns an empty list when no new links are found.

        Raises:
            httpx.HTTPStatusError: On unexpected HTTP errors.
            httpx.RequestError: On network-level failures.
        """
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
            self._client = client

        try:
            response = await client.get(self.page_url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTP error watching {}: {}",
                self.company_name,
                exc,
            )
            raise
        except httpx.RequestError as exc:
            logger.error(
                "Network error watching {}: {}",
                self.company_name,
                exc,
            )
            raise

        current_urls = self._extract_links(response.text)
        new_urls = current_urls - self.previous_urls

        # Update the stored set for next time (caller should persist this).
        self.previous_urls = current_urls

        if not new_urls:
            logger.debug(
                "No new job links on {} ({} total links)",
                self.company_name,
                len(current_urls),
            )
            return []

        logger.info(
            "Found {} new job links on {} ({} total)",
            len(new_urls),
            self.company_name,
            len(current_urls),
        )

        jobs: list[JobPosting] = []
        for url in sorted(new_urls):
            title = self._extract_title_from_url(url)
            jobs.append(
                JobPosting(
                    source=self.get_source_name(),
                    source_url=url,
                    company=self.company_name,
                    company_url=self.page_url,
                    title=title,
                    description=f"New job posting discovered on {self.company_name} career page",
                    raw_data={"discovered_url": url, "page_url": self.page_url},
                ),
            )

        return jobs

    def _extract_links(self, html: str) -> set[str]:
        """Extract job links from career page HTML.

        Uses BeautifulSoup with the CSS selector when available, falling
        back to regex extraction.

        Args:
            html: Raw HTML content of the career page.

        Returns:
            A set of absolute job URLs found on the page.
        """
        # Prefer CSS selector when beautifulsoup4 is available.
        if _BS4_AVAILABLE and not self.link_pattern:
            return self._extract_with_css(html)

        # Fall back to regex.
        if self.link_pattern:
            return self._extract_with_regex(html, self.link_pattern)

        # Last resort: find all href attributes.
        return self._extract_with_regex(
            html,
            r'href="(https?://[^"]*(?:job|career|position|opening)[^"]*)"',
        )

    def _extract_with_css(self, html: str) -> set[str]:
        """Extract links using BeautifulSoup and a CSS selector.

        Args:
            html: Raw HTML content.

        Returns:
            A set of absolute URLs matching the selector.
        """
        if not _BS4_AVAILABLE:
            logger.warning("BeautifulSoup not available; returning empty set")
            return set()
        soup = BeautifulSoup(html, "html.parser")
        links: set[str] = set()
        for tag in soup.select(self.link_selector):
            href = tag.get("href")
            if href and isinstance(href, str):
                absolute = urljoin(self.page_url, href.strip())
                links.add(absolute)
        return links

    def _extract_with_regex(self, html: str, pattern: str) -> set[str]:
        """Extract links using a regex pattern.

        Args:
            html: Raw HTML content.
            pattern: Regex with a capture group for the URL.

        Returns:
            A set of absolute URLs matching the pattern.
        """
        links: set[str] = set()
        for match in re.finditer(pattern, html, re.IGNORECASE):
            url = match.group(1) if match.lastindex else match.group(0)
            absolute = urljoin(self.page_url, url.strip())
            links.add(absolute)
        return links

    @staticmethod
    def _extract_title_from_url(url: str) -> str:
        """Derive a human-readable title from a job posting URL.

        Args:
            url: The absolute URL of the job posting.

        Returns:
            A title derived from the URL path, or a generic fallback.
        """
        from urllib.parse import urlparse

        path = urlparse(url).path.rstrip("/")
        if not path:
            return "New Job Posting"

        # Take the last path segment and clean it up.
        last_segment = path.split("/")[-1]
        # Replace common separators with spaces.
        title = re.sub(r"[-_]+", " ", last_segment)
        # Remove file extensions.
        title = re.sub(r"\.\w+$", "", title)
        # Title-case the result.
        title = title.strip().title()

        return title if title else "New Job Posting"
