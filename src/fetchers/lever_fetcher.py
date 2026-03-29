"""Fetch and normalize jobs from Lever public job boards.

Lever exposes a free, unauthenticated JSON API at
``GET /v0/postings/{site}?mode=json`` that returns all published postings
for a given company.  This fetcher follows the same async-context-manager
pattern as :class:`GreenhouseFetcher`.
"""

from __future__ import annotations

import re
from typing import Optional

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting

# Lever's public postings API requires no authentication.
BASE_URL = "https://api.lever.co/v0/postings"


class LeverFetcher(BaseFetcher):
    """Fetch job postings from Lever's public postings API.

    Attributes:
        company_name: Human-readable label used in logs and job records.
        lever_id: Lever site identifier (the URL slug, e.g. ``"lever"``).
    """

    def __init__(self, company_name: str, lever_id: str) -> None:
        """Store the Lever site identity for one company.

        Args:
            company_name: Human-readable company name.
            lever_id: Lever board slug used in the API URL path.
        """
        self.company_name = company_name
        self.lever_id = lever_id
        self._client: Optional[httpx.AsyncClient] = None
        super().__init__(config={"company": company_name, "id": lever_id})

    def get_source_name(self) -> str:
        """Return the stable source identifier for Lever jobs.

        Returns:
            A machine-friendly source string like ``lever_stripe``.
        """
        return f"lever_{self.company_name.lower().replace(' ', '_')}"

    async def __aenter__(self) -> LeverFetcher:
        """Create the shared HTTP client for the Lever crawl.

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
        """Fetch all published postings for the configured Lever board.

        Returns:
            A list of normalized :class:`JobPosting` objects, or an empty
            list when the board is missing or rate-limited.

        Raises:
            httpx.HTTPStatusError: On unexpected HTTP errors.
            httpx.RequestError: On network-level failures.
        """
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

        url = f"{BASE_URL}/{self.lever_id}"
        params = {"mode": "json"}

        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning("Lever board not found: {}", self.lever_id)
                return []
            if exc.response.status_code == 429:
                logger.warning("Rate limited by Lever for {}", self.company_name)
                return []
            logger.error("HTTP error fetching Lever {}: {}", self.company_name, exc)
            raise
        except httpx.RequestError as exc:
            logger.error("Network error fetching Lever {}: {}", self.company_name, exc)
            raise

        if not isinstance(data, list):
            logger.warning("Unexpected Lever response for {}", self.company_name)
            return []

        logger.debug("Fetched {} jobs from Lever {}", len(data), self.company_name)
        return [self._parse_job(posting) for posting in data]

    def _parse_job(self, posting: dict) -> JobPosting:
        """Convert one Lever posting payload into a normalized :class:`JobPosting`.

        Args:
            posting: Raw JSON object from the Lever API response.

        Returns:
            A normalized :class:`JobPosting` instance.
        """
        categories = posting.get("categories", {}) or {}
        location = categories.get("location", "")
        commitment = categories.get("commitment", "")

        # Lever provides both HTML and plaintext description variants.
        description = posting.get("descriptionPlain", "") or ""

        # Requirements and other list sections come as structured blocks.
        requirements_parts: list[str] = []
        for section in posting.get("lists", []) or []:
            section_text = section.get("text", "")
            section_content = section.get("content", "")
            if section_content:
                cleaned = self._clean_html(section_content)
                if section_text:
                    requirements_parts.append(f"{section_text}: {cleaned}")
                else:
                    requirements_parts.append(cleaned)
        requirements = "\n".join(requirements_parts)

        # Salary data is structured when present.
        salary_min, salary_max, salary_source = self._extract_salary(posting)

        hosted_url = posting.get("hostedUrl", "")

        return JobPosting(
            source=self.get_source_name(),
            source_url=hosted_url,
            company=self.company_name,
            company_url=f"https://jobs.lever.co/{self.lever_id}",
            title=posting.get("text", "Unknown Title"),
            location=location,
            job_type=self._map_commitment(commitment),
            description=description,
            requirements=requirements,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_source=salary_source,
            is_remote=self._detect_remote(posting),
            raw_data=posting,
        )

    @staticmethod
    def _extract_salary(
        posting: dict,
    ) -> tuple[int | None, int | None, str]:
        """Extract salary range from the Lever posting's structured field.

        Args:
            posting: Raw Lever posting payload.

        Returns:
            A ``(min_cents, max_cents, salary_source)`` tuple.
        """
        salary_range = posting.get("salaryRange")
        if not salary_range:
            return None, None, "not_listed"

        raw_min = salary_range.get("min")
        raw_max = salary_range.get("max")
        interval = salary_range.get("interval", "annually")

        if raw_min is None and raw_max is None:
            return None, None, "not_listed"

        multiplier = _interval_to_annual_multiplier(interval)
        min_cents = int(raw_min * multiplier * 100) if raw_min is not None else None
        max_cents = int(raw_max * multiplier * 100) if raw_max is not None else None
        return min_cents, max_cents, "direct"

    @staticmethod
    def _map_commitment(commitment: str) -> str | None:
        """Map Lever's commitment category to the normalized job_type enum.

        Args:
            commitment: Raw commitment string from the Lever API.

        Returns:
            A normalized job-type string, or ``None`` when unmapped.
        """
        if not commitment:
            return None
        lower = commitment.lower()
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
    def _detect_remote(posting: dict) -> bool | None:
        """Detect remote status from Lever's workplaceType field.

        Args:
            posting: Raw Lever posting payload.

        Returns:
            ``True`` for remote, ``False`` for on-site, or ``None`` when
            unspecified.
        """
        workplace = posting.get("workplaceType", "")
        if not workplace or workplace == "unspecified":
            return None
        return workplace.lower() == "remote"

    @staticmethod
    def _clean_html(html: str) -> str:
        """Strip HTML tags and collapse whitespace.

        Args:
            html: Raw HTML string from a Lever list section.

        Returns:
            Plain-text content with collapsed whitespace.
        """
        if not html:
            return ""
        clean = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", clean).strip()


def _interval_to_annual_multiplier(interval: str) -> float:
    """Convert a salary interval label to an annual multiplier.

    Args:
        interval: Lever's salary interval (e.g. ``"annually"``, ``"monthly"``).

    Returns:
        A multiplier that converts the interval value to annual dollars.
    """
    mapping: dict[str, float] = {
        "annually": 1.0,
        "yearly": 1.0,
        "monthly": 12.0,
        "weekly": 52.0,
        "daily": 260.0,
        "hourly": 2080.0,
    }
    return mapping.get(interval.lower(), 1.0)
