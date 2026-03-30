"""Fetch and normalize job listings from GitHub internship repositories.

Parses the SimplifyJobs ``listings.json`` format used by repos like
``SimplifyJobs/Summer2026-Internships``.  The JSON file is fetched via
``raw.githubusercontent.com`` to avoid GitHub API rate limits.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting

# Template for fetching raw files from GitHub without hitting the REST API.
RAW_GITHUB_URL = "https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"

# Default path where SimplifyJobs stores its listing data.
DEFAULT_JSON_PATH = ".github/scripts/listings.json"
DEFAULT_BRANCH = "dev"


class GitHubRepoFetcher(BaseFetcher):
    """Fetch job listings from a GitHub repo's JSON listing file.

    Attributes:
        repo_owner: GitHub repo owner (e.g. ``"SimplifyJobs"``).
        repo_name: GitHub repo name (e.g. ``"Summer2026-Internships"``).
        branch: Git branch to fetch from (default: ``"dev"``).
        json_path: Path to the JSON listing file within the repo.
        categories: Optional category filter (e.g. ``["Software"]``).
    """

    def __init__(
        self,
        repo_owner: str,
        repo_name: str,
        *,
        branch: str = DEFAULT_BRANCH,
        json_path: str = DEFAULT_JSON_PATH,
        categories: list[str] | None = None,
    ) -> None:
        """Configure which GitHub repo and branch to fetch listings from.

        Args:
            repo_owner: GitHub user or org that owns the repository.
            repo_name: Repository name.
            branch: Branch to fetch from.
            json_path: File path within the repo to the JSON listing.
            categories: If provided, only include entries matching these
                category values (case-insensitive).
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.branch = branch
        self.json_path = json_path
        self.categories = (
            {c.lower() for c in categories} if categories else None
        )
        self._client: Optional[httpx.AsyncClient] = None
        super().__init__(
            config={
                "owner": repo_owner,
                "repo": repo_name,
                "branch": branch,
            },
        )

    def get_source_name(self) -> str:
        """Return the stable source identifier for this GitHub repo.

        Returns:
            A machine-friendly source string like
            ``github_simplifyjobs_summer2026-internships``.
        """
        owner_slug = self.repo_owner.lower().replace(" ", "_")
        repo_slug = self.repo_name.lower().replace(" ", "_")
        return f"github_{owner_slug}_{repo_slug}"

    async def __aenter__(self) -> GitHubRepoFetcher:
        """Create the shared HTTP client.

        Returns:
            The fetcher instance with an active HTTP client.
        """
        headers: dict[str, str] = {}
        import os

        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"token {token}"

        self._client = httpx.AsyncClient(timeout=30.0, headers=headers)
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
        """Fetch and parse job listings from the configured GitHub repo.

        Returns:
            A list of normalized :class:`JobPosting` objects for active,
            visible listings.

        Raises:
            httpx.HTTPStatusError: On unexpected HTTP errors.
            httpx.RequestError: On network-level failures.
        """
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

        url = RAW_GITHUB_URL.format(
            owner=self.repo_owner,
            repo=self.repo_name,
            branch=self.branch,
            path=self.json_path,
        )

        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning(
                    "GitHub listings not found: {}/{}/{}",
                    self.repo_owner,
                    self.repo_name,
                    self.json_path,
                )
                return []
            logger.error(
                "HTTP error fetching GitHub {}/{}: {}",
                self.repo_owner,
                self.repo_name,
                exc,
            )
            raise
        except httpx.RequestError as exc:
            logger.error(
                "Network error fetching GitHub {}/{}: {}",
                self.repo_owner,
                self.repo_name,
                exc,
            )
            raise

        try:
            listings = response.json()
        except json.JSONDecodeError:
            logger.error(
                "Invalid JSON from GitHub {}/{}",
                self.repo_owner,
                self.repo_name,
            )
            return []

        if not isinstance(listings, list):
            logger.warning(
                "Expected list from GitHub {}/{}, got {}",
                self.repo_owner,
                self.repo_name,
                type(listings).__name__,
            )
            return []

        jobs: list[JobPosting] = []
        for entry in listings:
            if not self._should_include(entry):
                continue
            try:
                jobs.append(self._parse_entry(entry))
            except Exception as exc:
                logger.warning(
                    "Failed to parse GitHub listing {}: {}",
                    entry.get("id", "unknown"),
                    exc,
                )

        logger.debug(
            "Fetched {} jobs from GitHub {}/{} ({} total listings)",
            len(jobs),
            self.repo_owner,
            self.repo_name,
            len(listings),
        )
        return jobs

    def _should_include(self, entry: dict[str, Any]) -> bool:
        """Check whether a listing passes visibility and category filters.

        Args:
            entry: Raw listing dict from the JSON file.

        Returns:
            ``True`` if the entry should be included, ``False`` otherwise.
        """
        if not entry.get("active", True):
            return False
        if not entry.get("is_visible", True):
            return False

        if self.categories is not None:
            category = (entry.get("category") or "").lower()
            if category not in self.categories:
                return False

        return True

    def _parse_entry(self, entry: dict[str, Any]) -> JobPosting:
        """Convert one SimplifyJobs listing into a :class:`JobPosting`.

        Args:
            entry: Raw listing dict from the JSON file.

        Returns:
            A normalized :class:`JobPosting` instance.
        """
        locations = entry.get("locations", [])
        location_str = ", ".join(locations) if locations else ""

        posted_date = self._parse_epoch(entry.get("date_posted"))

        return JobPosting(
            source=self.get_source_name(),
            source_url=entry.get("url", ""),
            company=entry.get("company_name", "Unknown"),
            company_url=entry.get("company_url") or None,
            title=entry.get("title", "Unknown Title"),
            location=location_str,
            job_type="Internship",
            description=self._build_description(entry),
            posted_date=posted_date,
            raw_data=entry,
        )

    @staticmethod
    def _build_description(entry: dict[str, Any]) -> str:
        """Build a description string from available listing metadata.

        Args:
            entry: Raw listing dict from the JSON file.

        Returns:
            A short description assembled from available fields.
        """
        parts: list[str] = []

        title = entry.get("title", "")
        company = entry.get("company_name", "")
        if title and company:
            parts.append(f"{title} at {company}")

        category = entry.get("category", "")
        if category:
            parts.append(f"Category: {category}")

        sponsorship = entry.get("sponsorship", "")
        if sponsorship:
            parts.append(f"Sponsorship: {sponsorship}")

        terms = entry.get("terms", [])
        if terms:
            parts.append(f"Terms: {', '.join(terms)}")

        degrees = entry.get("degrees", [])
        if degrees:
            parts.append(f"Degrees: {', '.join(degrees)}")

        locations = entry.get("locations", [])
        if locations:
            parts.append(f"Locations: {', '.join(locations)}")

        return " | ".join(parts) if parts else "GitHub listing"

    @staticmethod
    def _parse_epoch(timestamp: int | float | None) -> str | None:
        """Convert a Unix epoch timestamp to an ISO 8601 date string.

        Args:
            timestamp: Unix epoch seconds, or ``None``.

        Returns:
            An ISO 8601 date string, or ``None`` when the input is invalid.
        """
        if timestamp is None:
            return None
        try:
            dt = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
            return dt.isoformat()
        except (ValueError, OverflowError, OSError):
            return None
