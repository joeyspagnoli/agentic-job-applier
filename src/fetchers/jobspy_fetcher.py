"""Fetch and normalize jobs from JobSpy-supported job boards."""

import asyncio
import math
from collections.abc import Mapping
from datetime import date
from typing import Any, Literal, Optional

from jobspy import scrape_jobs  # type: ignore[import-untyped]
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.fetchers.errors import FetchError
from src.models.job_posting import JobPosting, map_job_type


def clean_value(val: object, default: object | None = None) -> object | None:
    """Normalize JobSpy values that may contain NaNs or date objects.

    Purpose:
        Clean JobSpy and pandas-style values before they are serialized into the
        shared model or raw JSON payload.
    Args:
        val: Raw value returned by JobSpy.
        default: Fallback value used when the raw value is missing or NaN.
    Output:
        Returns a cleaned scalar, ISO date string, or the provided default.
    """

    if val is None:
        return default

    # JobSpy often returns pandas NaN floats, which would otherwise leak into
    # JSON serialization and downstream normalization logic.
    try:
        if isinstance(val, float) and math.isnan(val):
            return default
    except (TypeError, ValueError):
        pass

    # Dates are converted here so every caller gets consistent string output
    # without needing to know which fields may contain date objects.
    if isinstance(val, date):
        return val.isoformat()
    return val


def clean_str(val: object, default: str = "") -> str:
    """Normalize a JobSpy value into a safe string.

    Purpose:
        Ensure string fields are always represented as plain text, even when the
        source contains nulls, NaNs, or non-string scalar values.
    Args:
        val: Raw value returned by JobSpy.
        default: Fallback string used when the raw value is missing.
    Output:
        Returns a cleaned string value.
    """

    cleaned = clean_value(val, default)
    if cleaned is None:
        return default
    return str(cleaned)


def _coerce_float(value: object | None) -> float | None:
    """Convert a cleaned scalar value to float when possible.

    Purpose:
        Normalize numeric salary inputs into a concrete float type before
        annual-cents conversion logic runs.
    Args:
        value: Cleaned scalar value from JobSpy payload.
    Output:
        Returns parsed float value or `None` when conversion fails.
    """

    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


class JobSpyFetcher(BaseFetcher):
    """Fetch job postings from JobSpy-supported job boards."""

    def __init__(
        self,
        site_name: Literal["indeed", "glassdoor", "linkedin"],
        search_term: str,
        location: str = "Remote",
        results_wanted: int = 25,
        country: str = "USA",
    ) -> None:
        """Store the JobSpy search settings for one crawl variant.

        Purpose:
            Capture the board, search term, location, and result count that
            define a single JobSpy scrape request.
        Args:
            self: The JobSpy fetcher instance being initialized.
            site_name: Job board name supported by JobSpy.
            search_term: Search phrase to send to the target board.
            location: Geographic location or `Remote` filter for the search.
            results_wanted: Approximate number of rows to request.
            country: Country code passed through to Indeed scraping.
        Output:
            Returns `None` after saving the fetcher configuration.
        """

        self.site_name = site_name
        self.search_term = search_term
        self.location = location
        self.results_wanted = results_wanted
        self.country = country
        super().__init__(
            config={
                "site": site_name,
                "term": search_term,
                "location": location,
            }
        )

    def get_source_name(self) -> str:
        """Return the source name recorded on JobSpy jobs.

        Purpose:
            Include both the site and search term in the source identifier so
            logs and persisted rows retain useful crawl provenance.
        Args:
            self: The JobSpy fetcher reporting its source name.
        Output:
            Returns a machine-friendly source identifier string.
        """

        term_slug = self.search_term.lower().replace(" ", "_")[:30]
        return f"jobspy_{self.site_name}_{term_slug}"

    async def fetch_jobs(self) -> list[JobPosting]:
        """Run the JobSpy scrape and normalize each returned row.

        Purpose:
            Bridge JobSpy's synchronous scraping API into the async discovery
            flow and convert the resulting rows into `JobPosting` objects.
        Args:
            self: The JobSpy fetcher performing the scrape.
        Output:
            Returns a list of normalized `JobPosting` objects, or an empty list
            when the scrape fails or yields no rows.
        """

        logger.info(
            f"Scraping {self.site_name} for '{self.search_term}' in {self.location}"
        )

        # JobSpy is synchronous, so the scrape runs in an executor to keep the
        # orchestrator event loop responsive while scraping happens.
        loop = asyncio.get_event_loop()

        try:
            jobs_df = await loop.run_in_executor(None, self._scrape_sync)
        except Exception as e:
            raise FetchError(f"JobSpy scrape failed for {self.site_name}: {e}") from e

        if jobs_df is None or jobs_df.empty:
            logger.warning(f"No jobs found on {self.site_name} for '{self.search_term}'")
            return []

        logger.info(f"Scraped {len(jobs_df)} jobs from {self.site_name}")
        jobs = []

        # Each row is parsed independently so one malformed posting does not
        # discard the rest of the scrape results.
        for _, row in jobs_df.iterrows():
            try:
                jobs.append(self._parse_job(row.to_dict()))
            except Exception as e:
                logger.warning(f"Failed to parse job from {self.site_name}: {e}")
                continue

        return jobs

    def _scrape_sync(self) -> Any:
        """Run JobSpy's blocking scrape function.

        Purpose:
            Isolate the synchronous scrape call so the async fetch method can
            execute it via an executor without cluttering its control flow.
        Args:
            self: The JobSpy fetcher running the scrape.
        Output:
            Returns the JobSpy DataFrame result.
        """
        return scrape_jobs(
            site_name=[self.site_name],
            search_term=self.search_term,
            location=self.location,
            results_wanted=self.results_wanted,
            country_indeed=self.country,
            hours_old=72,
        )

    def _parse_job(self, job_data: Mapping[str, object]) -> JobPosting:
        """Convert one JobSpy row dictionary into a normalized `JobPosting`.

        Purpose:
            Translate JobSpy's DataFrame-like output into the shared model while
            cleaning NaNs, dates, strings, and salary fields.
        Args:
            self: The JobSpy fetcher performing the normalization.
            job_data: Dictionary created from a JobSpy DataFrame row.
        Output:
            Returns a normalized `JobPosting` instance.
        """

        # JobSpy rows often contain pandas values, so each field is cleaned
        # before the normalized model or raw payload is constructed.
        title = clean_str(job_data.get("title"), "Unknown Title")
        company = clean_str(job_data.get("company"), "Unknown Company")
        location = clean_str(job_data.get("location"), "")
        description = clean_str(job_data.get("description"), "")
        job_url = clean_str(job_data.get("job_url"), "")

        company_url_raw = clean_value(job_data.get("company_url"))
        company_url: str | None = str(company_url_raw) if company_url_raw is not None else None

        # Map job_type using the canonical mapping so we get a proper Literal type.
        job_type_raw = clean_value(job_data.get("job_type"))
        job_type_str: str | None = str(job_type_raw) if job_type_raw is not None else None
        job_type = map_job_type(job_type_str)

        # Dates and salary intervals are normalized to strings before they are
        # handed to the shared model and JSON serializer.
        date_posted_raw = clean_value(job_data.get("date_posted"))
        date_posted: str | None = str(date_posted_raw) if date_posted_raw is not None else None

        min_amount = _coerce_float(clean_value(job_data.get("min_amount")))
        max_amount = _coerce_float(clean_value(job_data.get("max_amount")))
        currency = clean_str(job_data.get("currency"), "USD")
        interval_raw = clean_value(job_data.get("interval"))
        interval: str | None = str(interval_raw) if interval_raw is not None else None

        salary_min, salary_max = self._normalize_salary(
            min_amount,
            max_amount,
            interval,
        )

        # The raw payload is cleaned field-by-field so JSON serialization never
        # has to deal with NaNs or other pandas-specific sentinel values.
        cleaned_raw_data: dict[str, object] = {}
        for key, value in job_data.items():
            cleaned_raw_data[key] = clean_value(value)

        return JobPosting(
            source=self.get_source_name(),
            source_url=job_url,
            company=company,
            company_url=company_url,
            title=title,
            location=location,
            job_type=job_type,
            description=description,
            posted_date=date_posted,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=currency,
            salary_source="direct" if salary_min else "not_listed",
            raw_data=cleaned_raw_data,
        )

    def _normalize_salary(
        self,
        min_val: Optional[float],
        max_val: Optional[float],
        interval: Optional[str],
    ) -> tuple[Optional[int], Optional[int]]:
        """Convert JobSpy salary values into annual cents.

        Purpose:
            Normalize salary amounts that may be expressed hourly, daily,
            weekly, monthly, or yearly into one comparable annual-cents scale.
        Args:
            self: The JobSpy fetcher normalizing the salary values.
            min_val: Lower bound salary value returned by JobSpy.
            max_val: Upper bound salary value returned by JobSpy.
            interval: Frequency label describing the salary cadence.
        Output:
            Returns a `(min_cents, max_cents)` tuple in annual cents, or
            `(None, None)` when no salary data is available.
        """

        if min_val is None and max_val is None:
            return None, None

        # The multipliers convert common salary cadences into an annualized
        # representation that downstream ranking logic can compare directly.
        multipliers = {
            "yearly": 1,
            "monthly": 12,
            "weekly": 52,
            "daily": 260,
            "hourly": 2080,
        }

        normalized_interval = ""
        if interval:
            normalized_interval = str(interval).strip().lower()
            normalized_interval = normalized_interval.removeprefix("per ").strip()

        normalized_interval = {
            "year": "yearly",
            "annual": "yearly",
            "annually": "yearly",
            "month": "monthly",
            "week": "weekly",
            "day": "daily",
            "hour": "hourly",
        }.get(normalized_interval, normalized_interval)

        multiplier = multipliers.get(normalized_interval, 1)
        min_annual = int(min_val * multiplier * 100) if min_val else None
        max_annual = int(max_val * multiplier * 100) if max_val else None
        return min_annual, max_annual
