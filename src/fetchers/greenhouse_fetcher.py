"""Fetch and normalize jobs from Greenhouse public job boards."""

import re
from collections.abc import Mapping
from types import TracebackType
from typing import Optional

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting
from src.utils.json_types import get_dict, get_str, get_str_opt


class GreenhouseFetcher(BaseFetcher):
    """Fetch job postings from Greenhouse's public boards API."""

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self, company_name: str, greenhouse_id: str):
        """Store the Greenhouse board identity for one company.

        Purpose:
            Capture the board token and company label needed to fetch and label
            jobs from a single Greenhouse board.
        Args:
            self: The Greenhouse fetcher instance being initialized.
            company_name: Human-readable company name used in logs and jobs.
            greenhouse_id: Greenhouse board token used in the API URL.
        Output:
            Returns `None` after saving the board metadata and base config.
        """

        self.company_name = company_name
        self.greenhouse_id = greenhouse_id
        self._client: Optional[httpx.AsyncClient] = None
        super().__init__(config={"company": company_name, "id": greenhouse_id})

    def get_source_name(self) -> str:
        """Return the source name recorded on Greenhouse jobs.

        Purpose:
            Provide a stable identifier for crawl history and persisted job rows
            originating from this Greenhouse board.
        Args:
            self: The Greenhouse fetcher reporting its source name.
        Output:
            Returns a machine-friendly source identifier string.
        """

        return f"greenhouse_{self.company_name.lower().replace(' ', '_')}"

    async def __aenter__(self) -> "GreenhouseFetcher":
        """Create the shared HTTP client for the Greenhouse crawl.

        Purpose:
            Reuse one async HTTP client across all requests made during the
            lifetime of the fetcher context.
        Args:
            self: The Greenhouse fetcher entering the async context.
        Output:
            Returns the fetcher instance after creating the HTTP client.
        """

        self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the HTTP client when the Greenhouse context ends.

        Purpose:
            Release network resources created for the crawl once the caller is
            finished using the fetcher.
        Args:
            self: The Greenhouse fetcher exiting the async context.
            exc_type: Exception type raised inside the context, if any.
            exc_val: Exception instance raised inside the context, if any.
            exc_tb: Traceback for the exception raised inside the context.
        Output:
            Returns `None` after closing and clearing the HTTP client.
        """

        if self._client:
            await self._client.aclose()
            self._client = None

    async def fetch_jobs(self) -> list[JobPosting]:
        """Fetch and normalize all jobs for the configured Greenhouse board.

        Purpose:
            Call the Greenhouse API, handle common HTTP failure modes, and turn
            the returned job payloads into normalized `JobPosting` objects.
        Args:
            self: The Greenhouse fetcher performing the API call.
        Output:
            Returns a list of normalized `JobPosting` objects for the board, or
            an empty list when the board is missing or rate-limited.
        """

        # The fetcher can be used with or without `async with`, so it lazily
        # creates the client when the caller skips the context manager.
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

        url = f"{self.BASE_URL}/{self.greenhouse_id}/jobs"
        params = {"content": "true"}

        try:
            client = self._client
            if client is None:
                raise RuntimeError("Greenhouse HTTP client was not initialized")
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            # Missing boards and rate limits are common enough to downshift to
            # warnings rather than crash the entire discovery cycle.
            if e.response.status_code == 404:
                logger.warning(f"Greenhouse board not found: {self.greenhouse_id}")
                return []
            if e.response.status_code == 429:
                logger.warning(f"Rate limited by Greenhouse for {self.company_name}")
                return []

            logger.error(f"HTTP error fetching {self.company_name}: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error fetching {self.company_name}: {e}")
            raise

        jobs = data.get("jobs", [])
        logger.debug(f"Fetched {len(jobs)} jobs from {self.company_name}")

        # Parsing is delegated to `_parse_job` so the API call path stays short
        # and the normalization logic can be documented independently.
        return [self._parse_job(job) for job in jobs]

    def _parse_job(self, job_data: Mapping[str, object]) -> JobPosting:
        """Convert one Greenhouse payload into a normalized `JobPosting`.

        Purpose:
            Translate Greenhouse-specific field names and HTML content into the
            shared model used elsewhere in the repository.
        Args:
            self: The Greenhouse fetcher performing the normalization.
            job_data: Raw Greenhouse job payload from the API response.
        Output:
            Returns a normalized `JobPosting` instance.
        """

        # Greenhouse sometimes wraps location information in a nested object, so
        # this branch flattens it into the plain string used by the shared model.
        location_dict = get_dict(job_data, "location")
        if location_dict is not None:
            location_str = get_str(location_dict, "name")
        else:
            raw_loc = job_data.get("location")
            location_str = str(raw_loc) if raw_loc and not isinstance(raw_loc, dict) else ""

        # The public API returns HTML in the `content` field, which needs to be
        # cleaned before it is suitable for hashing, storage, and prompts.
        content = get_str(job_data, "content")
        description = self._clean_html(content)

        # Salary data is not consistently structured, so this fetcher extracts
        # a best-effort range from the cleaned description text.
        salary_min, salary_max = self._extract_salary(description)
        job_url = get_str(job_data, "absolute_url")

        return JobPosting(
            source=self.get_source_name(),
            source_url=job_url,
            company=self.company_name,
            company_url=f"https://boards.greenhouse.io/{self.greenhouse_id}",
            title=get_str(job_data, "title", "Unknown Title"),
            location=location_str,
            description=description,
            posted_date=get_str_opt(job_data, "updated_at"),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_source="parsed" if salary_min else "not_listed",
            raw_data=dict(job_data),
        )

    def _clean_html(self, html: str) -> str:
        """Strip HTML tags and collapse whitespace from Greenhouse content.

        Purpose:
            Turn Greenhouse's rich-text job descriptions into clean plain text
            suitable for storage, hashing, and downstream prompt building.
        Args:
            self: The Greenhouse fetcher cleaning the description text.
            html: Raw HTML string returned by the Greenhouse API.
        Output:
            Returns a plain-text description string.
        """

        if not html:
            return ""

        # Regex stripping is intentionally simple here because the source HTML
        # is predictable enough for readability-focused cleanup.
        clean = re.sub(r"<[^>]+>", " ", html)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def _extract_salary(self, text: str) -> tuple[Optional[int], Optional[int]]:
        """Extract a salary range from free-form description text.

        Purpose:
            Recover salary information when Greenhouse exposes it only inside the
            human-readable job description rather than a dedicated field.
        Args:
            self: The Greenhouse fetcher scanning description text.
            text: Cleaned plain-text job description.
        Output:
            Returns a `(min_cents, max_cents)` tuple, or `(None, None)` when no
            supported salary range pattern is found.
        """

        if not text:
            return None, None

        # The patterns cover the two salary formats that show up most often in
        # Greenhouse descriptions: comma-separated full values and `k` shorthand.
        patterns = [
            r"\$(\d{1,3}(?:,\d{3})*)\s*[-–—to]\s*\$(\d{1,3}(?:,\d{3})*)",
            r"\$(\d{2,3})k\s*[-–—to]\s*\$(\d{2,3})k",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue

            try:
                min_val = match.group(1).replace(",", "")
                max_val = match.group(2).replace(",", "")

                # The pattern itself tells us whether the values are already
                # annual dollar amounts or shorthand that needs expansion.
                if "k" in pattern.lower():
                    min_cents = int(min_val) * 1000 * 100
                    max_cents = int(max_val) * 1000 * 100
                else:
                    min_cents = int(min_val) * 100
                    max_cents = int(max_val) * 100

                return min_cents, max_cents
            except ValueError:
                # Bad numeric formatting should not abort parsing of the whole
                # job posting, so the scan simply continues.
                continue

        return None, None
