"""Fetch and normalize jobs from startup.jobs.

startup.jobs provides a public JSON feed of startup job listings.
"""

from __future__ import annotations

import re
from types import TracebackType
from typing import Optional

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting, map_job_type

API_URL = "https://startup.jobs/api/jobs"


class StartupJobsFetcher(BaseFetcher):
    """Fetch job postings from startup.jobs.

    Attributes:
        _search_term: Optional keyword search filter.
    """

    def __init__(self, *, search_term: str | None = None) -> None:
        """Initialize the startup.jobs fetcher.

        Args:
            search_term: Optional keyword to search in job titles.
        """
        self._search_term = search_term
        self._client: Optional[httpx.AsyncClient] = None
        super().__init__(config={"search": search_term})

    def get_source_name(self) -> str:
        """Return the stable source identifier."""
        return "startup_jobs"

    async def __aenter__(self) -> StartupJobsFetcher:
        """Create the shared HTTP client."""
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_jobs(self) -> list[JobPosting]:
        """Fetch jobs from startup.jobs.

        Returns:
            A list of normalized JobPosting objects.
        """
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=30.0)
            self._client = client

        params: dict[str, str] = {}
        if self._search_term:
            params["q"] = self._search_term

        try:
            response = await client.get(API_URL, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.error("HTTP error from startup.jobs: {}", exc)
            return []
        except httpx.RequestError as exc:
            logger.error("Network error fetching startup.jobs: {}", exc)
            raise

        jobs = data if isinstance(data, list) else data.get("jobs", [])
        if not isinstance(jobs, list):
            logger.warning("Unexpected startup.jobs response shape")
            return []

        logger.debug("Fetched {} jobs from startup.jobs", len(jobs))

        postings: list[JobPosting] = []
        for item in jobs:
            if not isinstance(item, dict):
                continue
            posting = self._parse_job(item)
            if posting:
                postings.append(posting)
        return postings

    def _parse_job(self, item: dict[str, object]) -> JobPosting | None:
        """Convert one startup.jobs listing into a normalized JobPosting.

        Args:
            item: Raw startup.jobs job object.

        Returns:
            A JobPosting, or None if required fields are missing.
        """
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "") or item.get("apply_url", "")).strip()
        if not title or not url:
            return None

        company = str(item.get("company_name", "Unknown")).strip()
        location = str(item.get("location", "")).strip() or None
        description_raw = str(item.get("description", "")).strip()
        description = re.sub(r"<[^>]+>", " ", description_raw)
        description = re.sub(r"\s+", " ", description).strip()

        is_remote = bool(item.get("remote"))
        job_type_raw = str(item.get("type", "")).strip() or None
        job_type = map_job_type(job_type_raw)
        posted_date = str(item.get("published_at", "")).strip() or None

        return JobPosting(
            source=self.get_source_name(),
            source_url=url,
            company=company,
            title=title,
            location=location,
            is_remote=is_remote,
            job_type=job_type,
            description=description,
            posted_date=posted_date,
            raw_data=dict(item),
        )
