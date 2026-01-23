"""Greenhouse API fetcher for job postings."""

import re
from typing import List, Optional

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting


class GreenhouseFetcher(BaseFetcher):
    """Fetches job postings from Greenhouse's public API.

    Greenhouse API is free and doesn't require authentication.
    Endpoint: https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs
    """

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self, company_name: str, greenhouse_id: str):
        self.company_name = company_name
        self.greenhouse_id = greenhouse_id
        self._client: Optional[httpx.AsyncClient] = None
        super().__init__(config={"company": company_name, "id": greenhouse_id})

    def get_source_name(self) -> str:
        return f"greenhouse_{self.company_name.lower().replace(' ', '_')}"

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_jobs(self) -> List[JobPosting]:
        """Fetch all jobs from Greenhouse API for this company."""
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

        url = f"{self.BASE_URL}/{self.greenhouse_id}/jobs"
        params = {"content": "true"}  # Include job descriptions

        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Greenhouse board not found: {self.greenhouse_id}")
                return []
            elif e.response.status_code == 429:
                logger.warning(f"Rate limited by Greenhouse for {self.company_name}")
                return []
            else:
                logger.error(f"HTTP error fetching {self.company_name}: {e}")
                raise
        except httpx.RequestError as e:
            logger.error(f"Network error fetching {self.company_name}: {e}")
            raise

        jobs = data.get("jobs", [])
        logger.debug(f"Fetched {len(jobs)} jobs from {self.company_name}")

        return [self._parse_job(job) for job in jobs]

    def _parse_job(self, job_data: dict) -> JobPosting:
        """Convert Greenhouse job data to JobPosting model."""
        # Extract location
        location = job_data.get("location", {})
        if isinstance(location, dict):
            location_str = location.get("name", "")
        else:
            location_str = str(location) if location else ""

        # Extract description (HTML content)
        content = job_data.get("content", "")
        description = self._clean_html(content)

        # Try to parse salary from description
        salary_min, salary_max = self._extract_salary(description)

        # Build job URL
        job_url = job_data.get("absolute_url", "")

        return JobPosting(
            source=self.get_source_name(),
            source_url=job_url,
            company=self.company_name,
            company_url=f"https://boards.greenhouse.io/{self.greenhouse_id}",
            title=job_data.get("title", "Unknown Title"),
            location=location_str,
            description=description,
            posted_date=job_data.get("updated_at"),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_source="parsed" if salary_min else "not_listed",
            raw_data=job_data,
        )

    def _clean_html(self, html: str) -> str:
        """Strip HTML tags from content."""
        if not html:
            return ""
        # Simple HTML tag removal
        clean = re.sub(r"<[^>]+>", " ", html)
        # Normalize whitespace
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def _extract_salary(self, text: str) -> tuple[Optional[int], Optional[int]]:
        """Extract salary range from text.

        Returns (min_cents, max_cents) or (None, None) if not found.
        """
        if not text:
            return None, None

        # Common patterns:
        # $150,000 - $200,000
        # $150k - $200k
        # $150,000-$200,000
        patterns = [
            # Full format: $150,000 - $200,000
            r"\$(\d{1,3}(?:,\d{3})*)\s*[-–—to]\s*\$(\d{1,3}(?:,\d{3})*)",
            # K format: $150k - $200k
            r"\$(\d{2,3})k\s*[-–—to]\s*\$(\d{2,3})k",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    min_val = match.group(1).replace(",", "")
                    max_val = match.group(2).replace(",", "")

                    # Handle "k" format
                    if "k" in pattern.lower():
                        min_cents = int(min_val) * 1000 * 100
                        max_cents = int(max_val) * 1000 * 100
                    else:
                        min_cents = int(min_val) * 100
                        max_cents = int(max_val) * 100

                    return min_cents, max_cents
                except ValueError:
                    continue

        return None, None
