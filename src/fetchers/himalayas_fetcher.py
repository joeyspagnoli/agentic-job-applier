"""Fetch and normalize remote jobs from the Himalayas public API.

Himalayas provides a free, unauthenticated JSON API for remote jobs.
Docs: https://himalayas.app/api
"""

from __future__ import annotations

from types import TracebackType
from typing import Optional

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting

API_URL = "https://himalayas.app/jobs/api"


class HimalayasFetcher(BaseFetcher):
    """Fetch remote job postings from the Himalayas API.

    Attributes:
        _search_term: Optional keyword to search in job titles.
    """

    def __init__(self, *, search_term: str | None = None) -> None:
        """Initialize the Himalayas fetcher.

        Args:
            search_term: Optional keyword filter for job titles.
        """
        self._search_term = search_term
        self._client: Optional[httpx.AsyncClient] = None
        super().__init__(config={"search": search_term})

    def get_source_name(self) -> str:
        """Return the stable source identifier."""
        return "himalayas"

    async def __aenter__(self) -> HimalayasFetcher:
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
        """Fetch remote jobs from the Himalayas API.

        Returns:
            A list of normalized JobPosting objects.
        """
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

        params: dict[str, str] = {}
        if self._search_term:
            params["q"] = self._search_term

        try:
            response = await self._client.get(API_URL, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.error("HTTP error from Himalayas: {}", exc)
            return []
        except httpx.RequestError as exc:
            logger.error("Network error fetching Himalayas: {}", exc)
            raise

        jobs = data.get("jobs", [])
        if not isinstance(jobs, list):
            logger.warning("Unexpected Himalayas response shape")
            return []

        logger.debug("Fetched {} remote jobs from Himalayas", len(jobs))

        postings: list[JobPosting] = []
        for item in jobs:
            if not isinstance(item, dict):
                continue
            posting = self._parse_job(item)
            if posting:
                postings.append(posting)
        return postings

    def _parse_job(self, item: dict[str, object]) -> JobPosting | None:
        """Convert one Himalayas job into a normalized JobPosting.

        Args:
            item: Raw Himalayas job object.

        Returns:
            A JobPosting, or None if required fields are missing.
        """
        title = str(item.get("title", "")).strip()
        if not title:
            return None

        slug = str(item.get("slug", "")).strip()
        company_slug = str(item.get("companySlug", "")).strip()
        url = f"https://himalayas.app/companies/{company_slug}/jobs/{slug}" if slug else ""
        if not url:
            url = str(item.get("applicationUrl", "")).strip()
        if not url:
            return None

        company = str(item.get("companyName", "Unknown")).strip()
        location = str(item.get("location", "")).strip() or "Remote"
        description = str(item.get("description", "")).strip()
        posted_date = str(item.get("pubDate", "")).strip() or None

        # Salary fields.
        salary_min = None
        salary_max = None
        raw_min = item.get("minSalary")
        raw_max = item.get("maxSalary")
        if raw_min is not None:
            try:
                salary_min = int(float(str(raw_min)) * 100)
            except (ValueError, TypeError):
                pass
        if raw_max is not None:
            try:
                salary_max = int(float(str(raw_max)) * 100)
            except (ValueError, TypeError):
                pass

        return JobPosting(
            source=self.get_source_name(),
            source_url=url,
            company=company,
            title=title,
            location=location,
            is_remote=True,
            description=description,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_source="direct" if salary_min else "not_listed",
            posted_date=posted_date,
            raw_data=dict(item),
        )
