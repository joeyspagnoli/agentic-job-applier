"""Fetch and normalize jobs from Ashby public job board API.

Ashby exposes a free, unauthenticated endpoint at
``GET /posting-api/job-board/{boardId}`` that returns all published
postings for a given company.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal, Optional

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting
from src.utils.json_types import get_dict, get_float_opt, get_str

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board"


class AshbyFetcher(BaseFetcher):
    """Fetch job postings from Ashby's public job board API.

    Attributes:
        company_name: Human-readable label used in logs and job records.
        board_id: Ashby board identifier (URL slug, e.g. ``"anthropic"``).
    """

    def __init__(self, company_name: str, board_id: str) -> None:
        """Store the Ashby board identity for one company.

        Args:
            company_name: Human-readable company name.
            board_id: Ashby board slug used in the API URL path.
        """
        self.company_name = company_name
        self.board_id = board_id
        self._client: Optional[httpx.AsyncClient] = None
        super().__init__(config={"company": company_name, "id": board_id})

    def get_source_name(self) -> str:
        """Return the stable source identifier for Ashby jobs.

        Returns:
            A machine-friendly source string like ``ashby_notion``.
        """
        return f"ashby_{self.company_name.lower().replace(' ', '_')}"

    async def __aenter__(self) -> AshbyFetcher:
        """Create the shared HTTP client for the Ashby crawl.

        Returns:
            The fetcher instance with an active HTTP client.
        """
        self._client = httpx.AsyncClient(timeout=30.0)
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
        """Fetch all published postings for the configured Ashby board.

        Returns:
            A list of normalized :class:`JobPosting` objects, or an empty
            list when the board is missing or rate-limited.

        Raises:
            httpx.HTTPStatusError: On unexpected HTTP errors.
            httpx.RequestError: On network-level failures.
        """
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

        url = f"{BASE_URL}/{self.board_id}"

        try:
            response = await self._client.get(url)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning("Ashby board not found: {}", self.board_id)
                return []
            if exc.response.status_code == 429:
                logger.warning("Rate limited by Ashby for {}", self.company_name)
                return []
            logger.error("HTTP error fetching Ashby {}: {}", self.company_name, exc)
            raise
        except httpx.RequestError as exc:
            logger.error("Network error fetching Ashby {}: {}", self.company_name, exc)
            raise

        # Ashby wraps postings under a "jobs" key.
        jobs = data.get("jobs", [])
        if not isinstance(jobs, list):
            logger.warning("Unexpected Ashby response for {}", self.company_name)
            return []

        logger.debug("Fetched {} jobs from Ashby {}", len(jobs), self.company_name)
        return [self._parse_job(posting) for posting in jobs]

    def _parse_job(self, posting: Mapping[str, object]) -> JobPosting:
        """Convert one Ashby posting payload into a normalized :class:`JobPosting`.

        Args:
            posting: Raw JSON object from the Ashby API response.

        Returns:
            A normalized :class:`JobPosting` instance.
        """
        # Ashby nests location under different possible keys.
        location_dict = get_dict(posting, "location")
        if location_dict is not None:
            location = get_str(location_dict, "name")
        else:
            location = get_str(posting, "location")

        # Description may be HTML.
        description_html = get_str(posting, "descriptionHtml")
        description = self._clean_html(description_html)
        if not description:
            description = get_str(posting, "descriptionPlain")

        # Employment type mapping.
        employment_type = get_str(posting, "employmentType")

        # Compensation info.
        salary_min, salary_max, salary_source = self._extract_salary(posting)

        # Build the posting URL.
        job_url = get_str(posting, "jobUrl") or get_str(posting, "applyUrl")
        if not job_url:
            posting_id = get_str(posting, "id")
            if posting_id:
                job_url = f"https://jobs.ashbyhq.com/{self.board_id}/{posting_id}"

        return JobPosting(
            source=self.get_source_name(),
            source_url=job_url,
            company=self.company_name,
            company_url=f"https://jobs.ashbyhq.com/{self.board_id}",
            title=get_str(posting, "title", "Unknown Title"),
            location=location,
            job_type=self._map_employment_type(employment_type),
            description=description,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_source=salary_source,
            raw_data=dict(posting),
        )

    @staticmethod
    def _extract_salary(
        posting: Mapping[str, object],
    ) -> tuple[int | None, int | None, Literal["direct", "not_listed"]]:
        """Extract salary info from Ashby's compensation field.

        Args:
            posting: Raw Ashby posting payload.

        Returns:
            A ``(min_cents, max_cents, salary_source)`` tuple.
        """
        comp = get_dict(posting, "compensation")
        if not comp:
            return None, None, "not_listed"

        raw_min = get_float_opt(comp, "min")
        if raw_min is None:
            raw_min = get_float_opt(comp, "salaryMin")
        raw_max = get_float_opt(comp, "max")
        if raw_max is None:
            raw_max = get_float_opt(comp, "salaryMax")

        if raw_min is None and raw_max is None:
            return None, None, "not_listed"

        # Ashby usually reports annual amounts.
        min_cents = int(raw_min * 100) if raw_min is not None else None
        max_cents = int(raw_max * 100) if raw_max is not None else None
        return min_cents, max_cents, "direct"

    @staticmethod
    def _map_employment_type(
        employment_type: str,
    ) -> Literal["Full-time", "Part-time", "Contract", "Internship"] | None:
        """Map Ashby's employment type to the normalized job_type enum.

        Args:
            employment_type: Raw employment type from the Ashby API.

        Returns:
            A normalized job-type string, or ``None`` when unmapped.
        """
        if not employment_type:
            return None
        lower = employment_type.lower()
        if "intern" in lower:
            return "Internship"
        if "full" in lower:
            return "Full-time"
        if "part" in lower:
            return "Part-time"
        if "contract" in lower or "freelance" in lower:
            return "Contract"
        return None

    @staticmethod
    def _clean_html(html: str) -> str:
        """Strip HTML tags and collapse whitespace.

        Args:
            html: Raw HTML string from an Ashby posting.

        Returns:
            Plain-text content with collapsed whitespace.
        """
        if not html:
            return ""
        clean = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", clean).strip()
