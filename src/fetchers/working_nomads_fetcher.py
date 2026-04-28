"""Fetch and normalize remote jobs from Working Nomads.

Working Nomads provides a public JSON feed of remote job listings
at https://www.workingnomads.com/api/exposed_jobs/.
"""

from __future__ import annotations

import re
from types import TracebackType
from typing import Optional

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting

API_URL = "https://www.workingnomads.com/api/exposed_jobs/"


class WorkingNomadsFetcher(BaseFetcher):
    """Fetch remote job postings from the Working Nomads API.

    Attributes:
        _category: Optional category slug filter (e.g. "development").
    """

    def __init__(self, *, category: str | None = None) -> None:
        """Initialize the Working Nomads fetcher.

        Args:
            category: Optional category slug to filter by.
        """
        self._category = category
        self._client: Optional[httpx.AsyncClient] = None
        super().__init__(config={"category": category})

    def get_source_name(self) -> str:
        """Return the stable source identifier."""
        return "working_nomads"

    async def __aenter__(self) -> WorkingNomadsFetcher:
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
        """Fetch remote jobs from Working Nomads.

        Returns:
            A list of normalized JobPosting objects.
        """
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

        try:
            response = await self._client.get(API_URL)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.error("HTTP error from Working Nomads: {}", exc)
            return []
        except httpx.RequestError as exc:
            logger.error("Network error fetching Working Nomads: {}", exc)
            raise

        if not isinstance(data, list):
            logger.warning("Unexpected Working Nomads response shape")
            return []

        logger.debug("Fetched {} jobs from Working Nomads", len(data))

        postings: list[JobPosting] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            if self._category:
                cat = str(item.get("category_name", "")).lower()
                if self._category.lower() not in cat:
                    continue
            posting = self._parse_job(item)
            if posting:
                postings.append(posting)
        return postings

    def _parse_job(self, item: dict[str, object]) -> JobPosting | None:
        """Convert one Working Nomads job into a normalized JobPosting.

        Args:
            item: Raw Working Nomads job object.

        Returns:
            A JobPosting, or None if required fields are missing.
        """
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        if not title or not url:
            return None

        company = str(item.get("company_name", "Unknown")).strip()
        location = str(item.get("location", "")).strip() or "Remote"
        description_html = str(item.get("description", "")).strip()
        description = re.sub(r"<[^>]+>", " ", description_html)
        description = re.sub(r"\s+", " ", description).strip()
        posted_date = str(item.get("pub_date", "")).strip() or None

        return JobPosting(
            source=self.get_source_name(),
            source_url=url,
            company=company,
            title=title,
            location=location,
            is_remote=True,
            description=description,
            posted_date=posted_date,
            raw_data=dict(item),
        )
