"""Fetch and normalize jobs from The Muse public API.

The Muse provides a public API with optional API key.
500 req/hr without key, 3600 req/hr with key.
Docs: https://www.themuse.com/developers/api/v2
"""

from __future__ import annotations

from types import TracebackType
from typing import Optional

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting

API_URL = "https://www.themuse.com/api/public/jobs"
DEFAULT_PAGE_SIZE = 50


class TheMuseFetcher(BaseFetcher):
    """Fetch job postings from The Muse API.

    Attributes:
        _api_key: Optional API key for higher rate limits.
        _category: Job category filter (e.g. "Software Engineering").
        _level: Experience level filter (e.g. "Entry Level").
        _location: Location filter (e.g. "New York, NY").
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        category: str | None = None,
        level: str | None = None,
        location: str | None = None,
    ) -> None:
        """Initialize The Muse fetcher.

        Args:
            api_key: Optional API key for higher rate limits.
            category: Job category to filter by.
            level: Experience level to filter by.
            location: Location to filter by.
        """
        self._api_key = api_key
        self._category = category
        self._level = level
        self._location = location
        self._client: Optional[httpx.AsyncClient] = None
        super().__init__(config={"category": category, "level": level})

    def get_source_name(self) -> str:
        """Return the stable source identifier for The Muse jobs."""
        return "themuse"

    async def __aenter__(self) -> TheMuseFetcher:
        """Create the shared HTTP client."""
        self._client = httpx.AsyncClient(timeout=30.0)
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
        """Fetch jobs from The Muse API.

        Returns:
            A list of normalized JobPosting objects.
        """
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

        params: dict[str, str] = {"page": "0"}
        if self._api_key:
            params["api_key"] = self._api_key
        if self._category:
            params["category"] = self._category
        if self._level:
            params["level"] = self._level
        if self._location:
            params["location"] = self._location

        try:
            response = await self._client.get(API_URL, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                logger.warning("Rate limited by The Muse API")
                return []
            logger.error("HTTP error from The Muse: {}", exc)
            raise
        except httpx.RequestError as exc:
            logger.error("Network error fetching The Muse: {}", exc)
            raise

        results = data.get("results", [])
        logger.debug("Fetched {} jobs from The Muse", len(results))

        postings: list[JobPosting] = []
        for item in results:
            posting = self._parse_job(item)
            if posting:
                postings.append(posting)
        return postings

    def _parse_job(self, item: dict[str, object]) -> JobPosting | None:
        """Convert one Muse job into a normalized JobPosting.

        Args:
            item: Raw Muse API result object.

        Returns:
            A JobPosting, or None if required fields are missing.
        """
        name = str(item.get("name", "")).strip()
        if not name:
            return None

        # Build the job URL from the refs object.
        refs = item.get("refs", {})
        landing_page = ""
        if isinstance(refs, dict):
            landing_page = str(refs.get("landing_page", "")).strip()
        if not landing_page:
            return None

        # Extract company info.
        company_data = item.get("company", {})
        company_name = "Unknown"
        if isinstance(company_data, dict):
            company_name = str(company_data.get("name", "Unknown")).strip()

        # Extract locations.
        locations = item.get("locations", [])
        location_parts: list[str] = []
        if isinstance(locations, list):
            for loc in locations:
                if isinstance(loc, dict):
                    loc_name = str(loc.get("name", "")).strip()
                    if loc_name:
                        location_parts.append(loc_name)
        location = "; ".join(location_parts) if location_parts else None

        # Extract content sections.
        contents = str(item.get("contents", "")).strip()
        # The Muse returns HTML content.
        import re
        description = re.sub(r"<[^>]+>", " ", contents)
        description = re.sub(r"\s+", " ", description).strip()

        # Extract levels.
        levels = item.get("levels", [])
        job_type = None
        if isinstance(levels, list) and levels:
            first_level = levels[0]
            if isinstance(first_level, dict):
                level_name = str(first_level.get("name", "")).strip()
                if "intern" in level_name.lower():
                    job_type = "Internship"

        posted_date = str(item.get("publication_date", "")).strip() or None

        return JobPosting(
            source=self.get_source_name(),
            source_url=landing_page,
            company=company_name,
            title=name,
            location=location,
            job_type=job_type,
            description=description,
            posted_date=posted_date,
            raw_data=dict(item),
        )
