"""Fetch and normalize jobs from the Adzuna public API.

Adzuna provides a free API with 12+ country coverage. Requires a free
app_id and app_key from https://developer.adzuna.com/overview.
"""

from __future__ import annotations

from types import TracebackType
from typing import Literal, Optional

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting

BASE_URL = "https://api.adzuna.com/v1/api/jobs"
DEFAULT_RESULTS_PER_PAGE = 50
DEFAULT_COUNTRY = "us"


class AdzunaFetcher(BaseFetcher):
    """Fetch job postings from the Adzuna search API.

    Attributes:
        _app_id: Adzuna application ID from developer portal.
        _app_key: Adzuna application key from developer portal.
        _search_term: Job title or keyword to search for.
        _country: Two-letter country code (us, gb, de, etc.).
        _results_per_page: Number of results per API page.
    """

    def __init__(
        self,
        *,
        app_id: str,
        app_key: str,
        search_term: str = "software engineer",
        country: str = DEFAULT_COUNTRY,
        results_per_page: int = DEFAULT_RESULTS_PER_PAGE,
    ) -> None:
        """Initialize the Adzuna fetcher with API credentials.

        Args:
            app_id: Adzuna application ID.
            app_key: Adzuna application key.
            search_term: Job title or keyword to search.
            country: Two-letter country code for regional results.
            results_per_page: Number of results per API page.
        """
        self._app_id = app_id
        self._app_key = app_key
        self._search_term = search_term
        self._country = country
        self._results_per_page = results_per_page
        self._client: Optional[httpx.AsyncClient] = None
        super().__init__(config={"search_term": search_term, "country": country})

    def get_source_name(self) -> str:
        """Return the stable source identifier for Adzuna jobs."""
        return f"adzuna_{self._country}"

    async def __aenter__(self) -> AdzunaFetcher:
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
        """Fetch jobs matching the search term from Adzuna.

        Returns:
            A list of normalized JobPosting objects.
        """
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

        url = f"{BASE_URL}/{self._country}/search/1"
        params = {
            "app_id": self._app_id,
            "app_key": self._app_key,
            "what": self._search_term,
            "results_per_page": str(self._results_per_page),
            "content-type": "application/json",
        }

        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                logger.warning("Adzuna API auth failed — check app_id/app_key")
                return []
            if exc.response.status_code == 429:
                logger.warning("Rate limited by Adzuna API")
                return []
            logger.error("HTTP error from Adzuna: {}", exc)
            raise
        except httpx.RequestError as exc:
            logger.error("Network error fetching Adzuna: {}", exc)
            raise

        results = data.get("results", [])
        logger.debug("Fetched {} jobs from Adzuna ({})", len(results), self._country)

        postings: list[JobPosting] = []
        for item in results:
            posting = self._parse_result(item)
            if posting:
                postings.append(posting)
        return postings

    def _parse_result(self, item: dict[str, object]) -> JobPosting | None:
        """Convert one Adzuna result into a normalized JobPosting.

        Args:
            item: Raw Adzuna search result object.

        Returns:
            A JobPosting, or None if required fields are missing.
        """
        title = str(item.get("title", "")).strip()
        redirect_url = str(item.get("redirect_url", "")).strip()
        if not title or not redirect_url:
            return None

        company_dict = item.get("company", {})
        company = ""
        if isinstance(company_dict, dict):
            company = str(company_dict.get("display_name", "")).strip()
        if not company:
            company = "Unknown"

        location_dict = item.get("location", {})
        location_parts: list[str] = []
        if isinstance(location_dict, dict):
            for area_key in ("area", "display_name"):
                area_val = location_dict.get(area_key)
                if isinstance(area_val, list):
                    location_parts.extend(str(a) for a in area_val if a)
                elif area_val:
                    location_parts.append(str(area_val))
        location = ", ".join(location_parts) if location_parts else None

        description = str(item.get("description", "")).strip()

        # Adzuna provides salary_min and salary_max as annual amounts.
        salary_min = None
        salary_max = None
        salary_source: Literal["direct", "parsed", "not_listed"] = "not_listed"
        raw_min = item.get("salary_min")
        raw_max = item.get("salary_max")
        if raw_min is not None:
            try:
                salary_min = int(float(str(raw_min)) * 100)
                salary_source = "direct"
            except (ValueError, TypeError):
                pass
        if raw_max is not None:
            try:
                salary_max = int(float(str(raw_max)) * 100)
                salary_source = "direct"
            except (ValueError, TypeError):
                pass

        created = item.get("created")
        posted_date = str(created) if created else None

        return JobPosting(
            source=self.get_source_name(),
            source_url=redirect_url,
            company=company,
            title=title,
            location=location,
            description=description,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_source=salary_source,
            posted_date=posted_date,
            raw_data=dict(item),
        )
