"""Zero-token ATS direct scanner for company career pages.

Inspired by career-ops' scan.mjs. Hits Greenhouse, Ashby, Lever, and
BambooHR JSON APIs directly — zero AI cost. Auto-detects the ATS
provider from the careers page URL or explicit configuration.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from types import TracebackType

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting

SCAN_CONCURRENCY = 10
REQUEST_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class PortalConfig:
    """Configuration for a single company's career portal.

    Attributes:
        company_name: Human-readable company name.
        careers_url: URL to the company's careers page or ATS board.
        api_provider: Optional explicit ATS provider hint.
        title_filter_positive: Keywords that must appear in the title.
        title_filter_negative: Keywords that must not appear in the title.
    """

    company_name: str
    careers_url: str
    api_provider: str | None = None
    title_filter_positive: list[str] | None = None
    title_filter_negative: list[str] | None = None


def detect_ats_provider(url: str) -> str | None:
    """Auto-detect the ATS provider from a URL pattern.

    Args:
        url: The careers page or job board URL.

    Returns:
        The detected ATS provider name, or None if unknown.
    """
    lower = url.lower()

    if "boards-api.greenhouse.io" in lower or "boards.greenhouse.io" in lower:
        return "greenhouse"
    if "greenhouse.io" in lower:
        return "greenhouse"
    if "ashbyhq.com" in lower or "jobs.ashbyhq.com" in lower:
        return "ashby"
    if "lever.co" in lower or "jobs.lever.co" in lower:
        return "lever"
    if "bamboohr.com" in lower:
        return "bamboohr"
    if "teamtailor.com" in lower:
        return "teamtailor"
    return None


def _extract_board_id(url: str, provider: str) -> str:
    """Extract the board/company identifier from an ATS URL.

    Args:
        url: The ATS board URL.
        provider: The detected ATS provider.

    Returns:
        The board identifier string.
    """
    # Greenhouse: boards.greenhouse.io/{id} or boards-api.greenhouse.io/v1/boards/{id}
    if provider == "greenhouse":
        match = re.search(r"greenhouse\.io/(?:v1/boards/)?([^/?#]+)", url)
        return match.group(1) if match else url.rstrip("/").rsplit("/", maxsplit=1)[-1]

    # Ashby: jobs.ashbyhq.com/{id}
    if provider == "ashby":
        match = re.search(r"ashbyhq\.com/([^/?#]+)", url)
        return match.group(1) if match else url.rstrip("/").rsplit("/", maxsplit=1)[-1]

    # Lever: jobs.lever.co/{id}
    if provider == "lever":
        match = re.search(r"lever\.co/([^/?#]+)", url)
        return match.group(1) if match else url.rstrip("/").rsplit("/", maxsplit=1)[-1]

    # BambooHR: {company}.bamboohr.com
    if provider == "bamboohr":
        match = re.search(r"([^.]+)\.bamboohr\.com", url)
        return match.group(1) if match else ""

    return url.rstrip("/").rsplit("/", maxsplit=1)[-1]


def _matches_title_filter(
    title: str,
    positive: list[str] | None,
    negative: list[str] | None,
) -> bool:
    """Check if a job title passes the positive/negative keyword filters.

    Args:
        title: Job title to check.
        positive: At least one must match (case-insensitive). None = no filter.
        negative: None must match. None = no filter.

    Returns:
        True if the title passes all filters.
    """
    lower = title.lower()

    if negative:
        for neg in negative:
            if neg.lower() in lower:
                return False

    if positive:
        return any(pos.lower() in lower for pos in positive)

    return True


async def _fetch_greenhouse_jobs(
    client: httpx.AsyncClient,
    board_id: str,
    company_name: str,
) -> list[dict[str, object]]:
    """Fetch jobs from Greenhouse boards API.

    Args:
        client: Shared HTTP client.
        board_id: Greenhouse board identifier.
        company_name: Company name for logging.

    Returns:
        List of raw job dicts with title, url, location.
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_id}/jobs"
    try:
        response = await client.get(url, params={"content": "true"})
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.warning("Greenhouse fetch failed for {}: {}", company_name, exc)
        return []

    raw_jobs = data.get("jobs", [])
    results: list[dict[str, object]] = []
    for job in raw_jobs:
        if not isinstance(job, dict):
            continue
        location_obj = job.get("location", {})
        location = ""
        if isinstance(location_obj, dict):
            location = str(location_obj.get("name", ""))
        elif location_obj:
            location = str(location_obj)

        # Strip HTML from content.
        content = str(job.get("content", ""))
        description = re.sub(r"<[^>]+>", " ", content)
        description = re.sub(r"\s+", " ", description).strip()

        results.append({
            "title": str(job.get("title", "")),
            "url": str(job.get("absolute_url", "")),
            "location": location,
            "description": description,
            "posted_date": str(job.get("updated_at", "")),
        })
    return results


async def _fetch_ashby_jobs(
    client: httpx.AsyncClient,
    board_id: str,
    company_name: str,
) -> list[dict[str, object]]:
    """Fetch jobs from Ashby job board API.

    Args:
        client: Shared HTTP client.
        board_id: Ashby board identifier.
        company_name: Company name for logging.

    Returns:
        List of raw job dicts.
    """
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board_id}"
    try:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.warning("Ashby fetch failed for {}: {}", company_name, exc)
        return []

    raw_jobs = data.get("jobs", [])
    results: list[dict[str, object]] = []
    for job in raw_jobs:
        if not isinstance(job, dict):
            continue
        location_obj = job.get("location")
        location = ""
        if isinstance(location_obj, dict):
            location = str(location_obj.get("name", ""))
        elif location_obj:
            location = str(location_obj)

        desc_html = str(job.get("descriptionHtml", ""))
        description = re.sub(r"<[^>]+>", " ", desc_html)
        description = re.sub(r"\s+", " ", description).strip()
        if not description:
            description = str(job.get("descriptionPlain", ""))

        job_url = str(job.get("jobUrl", "") or job.get("applyUrl", ""))
        if not job_url:
            job_id = str(job.get("id", ""))
            if job_id:
                job_url = f"https://jobs.ashbyhq.com/{board_id}/{job_id}"

        results.append({
            "title": str(job.get("title", "")),
            "url": job_url,
            "location": location,
            "description": description,
        })
    return results


async def _fetch_lever_jobs(
    client: httpx.AsyncClient,
    board_id: str,
    company_name: str,
) -> list[dict[str, object]]:
    """Fetch jobs from Lever postings API.

    Args:
        client: Shared HTTP client.
        board_id: Lever company identifier.
        company_name: Company name for logging.

    Returns:
        List of raw job dicts.
    """
    url = f"https://api.lever.co/v0/postings/{board_id}"
    try:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.warning("Lever fetch failed for {}: {}", company_name, exc)
        return []

    if not isinstance(data, list):
        return []

    results: list[dict[str, object]] = []
    for posting in data:
        if not isinstance(posting, dict):
            continue

        # Lever nests location under categories.
        categories = posting.get("categories", {})
        location = ""
        if isinstance(categories, dict):
            location = str(categories.get("location", ""))

        description = str(posting.get("descriptionPlain", ""))

        results.append({
            "title": str(posting.get("text", "")),
            "url": str(posting.get("hostedUrl", "")),
            "location": location,
            "description": description,
        })
    return results


class ATSScanner(BaseFetcher):
    """Zero-token scanner that fetches jobs from ATS APIs directly.

    Takes a list of PortalConfig entries and hits the appropriate ATS
    JSON API for each company. No AI cost — pure HTTP.

    Attributes:
        _portals: List of company portal configurations.
    """

    def __init__(self, portals: list[PortalConfig]) -> None:
        """Initialize the ATS scanner with portal configs.

        Args:
            portals: List of company portal configurations.
        """
        self._portals = portals
        self._client: httpx.AsyncClient | None = None
        super().__init__(config={"portal_count": len(portals)})

    def get_source_name(self) -> str:
        """Return the stable source identifier."""
        return "ats_scanner"

    async def __aenter__(self) -> ATSScanner:
        """Create the shared HTTP client."""
        self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_jobs(self) -> list[JobPosting]:
        """Scan all configured portals and return normalized job postings.

        Runs up to SCAN_CONCURRENCY portal fetches in parallel.

        Returns:
            Combined list of JobPosting objects from all portals.
        """
        if not self._client:
            self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)

        semaphore = asyncio.Semaphore(SCAN_CONCURRENCY)
        tasks = [
            self._scan_portal(portal, semaphore)
            for portal in self._portals
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_postings: list[JobPosting] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Portal scan failed: {}", result)
                continue
            if isinstance(result, list):
                all_postings.extend(result)

        logger.info(
            "ATS scanner found {} jobs across {} portals",
            len(all_postings),
            len(self._portals),
        )
        return all_postings

    async def _scan_portal(
        self,
        portal: PortalConfig,
        semaphore: asyncio.Semaphore,
    ) -> list[JobPosting]:
        """Scan a single portal and return filtered job postings.

        Args:
            portal: Company portal configuration.
            semaphore: Concurrency limiter.

        Returns:
            List of JobPosting objects from this portal.
        """
        async with semaphore:
            provider = portal.api_provider or detect_ats_provider(portal.careers_url)
            if not provider:
                logger.debug(
                    "No ATS provider detected for {} ({})",
                    portal.company_name,
                    portal.careers_url,
                )
                return []

            board_id = _extract_board_id(portal.careers_url, provider)
            if not board_id:
                logger.warning(
                    "Could not extract board ID for {} from {}",
                    portal.company_name,
                    portal.careers_url,
                )
                return []

            if not self._client:
                return []

            raw_jobs: list[dict[str, object]] = []
            if provider == "greenhouse":
                raw_jobs = await _fetch_greenhouse_jobs(
                    self._client, board_id, portal.company_name
                )
            elif provider == "ashby":
                raw_jobs = await _fetch_ashby_jobs(
                    self._client, board_id, portal.company_name
                )
            elif provider == "lever":
                raw_jobs = await _fetch_lever_jobs(
                    self._client, board_id, portal.company_name
                )
            else:
                logger.debug(
                    "Unsupported ATS provider '{}' for {}",
                    provider,
                    portal.company_name,
                )
                return []

            # Filter by title keywords.
            postings: list[JobPosting] = []
            for raw_job in raw_jobs:
                title = str(raw_job.get("title", "")).strip()
                if not title:
                    continue

                if not _matches_title_filter(
                    title,
                    portal.title_filter_positive,
                    portal.title_filter_negative,
                ):
                    continue

                url = str(raw_job.get("url", "")).strip()
                if not url:
                    continue

                postings.append(
                    JobPosting(
                        source=f"ats_{provider}_{portal.company_name.lower().replace(' ', '_')}",
                        source_url=url,
                        company=portal.company_name,
                        title=title,
                        location=str(raw_job.get("location", "")).strip() or None,
                        description=str(raw_job.get("description", "")).strip(),
                        posted_date=str(raw_job.get("posted_date", "")).strip() or None,
                        raw_data=dict(raw_job),
                    )
                )

            logger.debug(
                "Scanned {} ({}): {} jobs, {} after filters",
                portal.company_name,
                provider,
                len(raw_jobs),
                len(postings),
            )
            return postings
