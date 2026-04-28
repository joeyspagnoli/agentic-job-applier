"""Fetch and normalize remote jobs from the Remotive public API.

Remotive provides a free, unauthenticated JSON endpoint for remote
job listings. Rate limit: 2 requests/minute.
Docs: https://github.com/remotive-com/remote-jobs-api
"""

from __future__ import annotations

from types import TracebackType
from typing import Optional

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting, map_job_type

API_URL = "https://remotive.com/api/remote-jobs"


class RemotiveFetcher(BaseFetcher):
    """Fetch remote job postings from the Remotive public API.

    Attributes:
        _category: Optional job category filter (e.g. "software-dev").
        _search_term: Optional keyword search filter.
    """

    def __init__(
        self,
        *,
        category: str | None = None,
        search_term: str | None = None,
    ) -> None:
        """Initialize the Remotive fetcher.

        Args:
            category: Optional Remotive category slug to filter by.
            search_term: Optional keyword to search in job titles.
        """
        self._category = category
        self._search_term = search_term
        self._client: Optional[httpx.AsyncClient] = None
        super().__init__(config={"category": category, "search": search_term})

    def get_source_name(self) -> str:
        """Return the stable source identifier for Remotive jobs."""
        return "remotive"

    async def __aenter__(self) -> RemotiveFetcher:
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
        """Fetch remote jobs from the Remotive API.

        Returns:
            A list of normalized JobPosting objects.
        """
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=30.0)
            self._client = client

        params: dict[str, str] = {}
        if self._category:
            params["category"] = self._category
        if self._search_term:
            params["search"] = self._search_term

        try:
            response = await client.get(API_URL, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                logger.warning("Rate limited by Remotive API")
                return []
            logger.error("HTTP error from Remotive: {}", exc)
            raise
        except httpx.RequestError as exc:
            logger.error("Network error fetching Remotive: {}", exc)
            raise

        jobs = data.get("jobs", [])
        logger.debug("Fetched {} remote jobs from Remotive", len(jobs))

        postings: list[JobPosting] = []
        for item in jobs:
            posting = self._parse_job(item)
            if posting:
                postings.append(posting)
        return postings

    def _parse_job(self, item: dict[str, object]) -> JobPosting | None:
        """Convert one Remotive job into a normalized JobPosting.

        Args:
            item: Raw Remotive job object.

        Returns:
            A JobPosting, or None if required fields are missing.
        """
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        if not title or not url:
            return None

        company = str(item.get("company_name", "Unknown")).strip()
        location = str(item.get("candidate_required_location", "")).strip() or "Remote"
        description = str(item.get("description", "")).strip()
        job_type_raw = str(item.get("job_type", "")).strip() or None
        job_type = map_job_type(job_type_raw)
        posted_date = str(item.get("publication_date", "")).strip() or None

        # Remotive provides salary as a string range like "$50,000 - $70,000".
        salary_text = str(item.get("salary", "")).strip()
        salary_min, salary_max = self._parse_salary(salary_text)

        return JobPosting(
            source=self.get_source_name(),
            source_url=url,
            company=company,
            title=title,
            location=location,
            is_remote=True,
            job_type=job_type,
            description=description,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_source="direct" if salary_min else "not_listed",
            posted_date=posted_date,
            raw_data=dict(item),
        )

    @staticmethod
    def _parse_salary(salary_text: str) -> tuple[int | None, int | None]:
        """Extract min/max salary in cents from Remotive salary string.

        Args:
            salary_text: Raw salary string like "$50,000 - $70,000".

        Returns:
            A (min_cents, max_cents) tuple.
        """
        if not salary_text:
            return None, None

        import re

        # Match dollar amounts with optional commas and K suffix.
        amounts = re.findall(r"\$?([\d,]+)k?", salary_text, re.IGNORECASE)
        if len(amounts) < 1:
            return None, None

        try:
            values = [int(a.replace(",", "")) for a in amounts[:2]]
            # Detect K shorthand.
            if "k" in salary_text.lower():
                values = [v * 1000 for v in values]
            min_cents = values[0] * 100
            max_cents = values[1] * 100 if len(values) > 1 else min_cents
            return min_cents, max_cents
        except (ValueError, IndexError):
            return None, None
