"""JobSpy-based fetcher for job boards (Indeed, Glassdoor, LinkedIn)."""

import asyncio
import math
from datetime import date
from typing import Any, List, Literal, Optional

from jobspy import scrape_jobs
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting


def clean_value(val: Any, default: Any = None) -> Any:
    """Clean a value that might be NaN or other pandas special values."""
    if val is None:
        return default
    # Handle pandas NaN
    try:
        if isinstance(val, float) and math.isnan(val):
            return default
    except (TypeError, ValueError):
        pass
    # Handle date objects
    if isinstance(val, date):
        return val.isoformat()
    return val


def clean_str(val: Any, default: str = "") -> str:
    """Clean a value to ensure it's a string."""
    cleaned = clean_value(val, default)
    if cleaned is None:
        return default
    return str(cleaned)


class JobSpyFetcher(BaseFetcher):
    """Fetches job postings from job boards using JobSpy.

    Supports: Indeed, Glassdoor, LinkedIn (LinkedIn requires proxies).
    """

    def __init__(
        self,
        site_name: Literal["indeed", "glassdoor", "linkedin"],
        search_term: str,
        location: str = "Remote",
        results_wanted: int = 25,
        country: str = "USA",
    ):
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
        # Normalize search term for source name
        term_slug = self.search_term.lower().replace(" ", "_")[:30]
        return f"jobspy_{self.site_name}_{term_slug}"

    async def fetch_jobs(self) -> List[JobPosting]:
        """Fetch jobs from job board using JobSpy."""
        logger.info(
            f"Scraping {self.site_name} for '{self.search_term}' in {self.location}"
        )

        # JobSpy is synchronous, run in executor
        loop = asyncio.get_event_loop()

        try:
            jobs_df = await loop.run_in_executor(None, self._scrape_sync)
        except Exception as e:
            logger.error(f"JobSpy scrape failed for {self.site_name}: {e}")
            return []

        if jobs_df is None or jobs_df.empty:
            logger.warning(f"No jobs found on {self.site_name} for '{self.search_term}'")
            return []

        logger.info(f"Scraped {len(jobs_df)} jobs from {self.site_name}")

        # Convert DataFrame rows to JobPosting objects
        jobs = []
        for _, row in jobs_df.iterrows():
            try:
                job = self._parse_job(row.to_dict())
                jobs.append(job)
            except Exception as e:
                logger.warning(f"Failed to parse job from {self.site_name}: {e}")
                continue

        return jobs

    def _scrape_sync(self):
        """Run the synchronous scrape_jobs function."""
        try:
            return scrape_jobs(
                site_name=[self.site_name],
                search_term=self.search_term,
                location=self.location,
                results_wanted=self.results_wanted,
                country_indeed=self.country,
                hours_old=72,  # Jobs posted in last 72 hours
            )
        except Exception as e:
            logger.error(f"scrape_jobs raised: {e}")
            return None

    def _parse_job(self, job_data: dict) -> JobPosting:
        """Convert JobSpy DataFrame row to JobPosting model."""
        # JobSpy returns columns like:
        # site, job_url, title, company, location, job_type, date_posted,
        # description, min_amount, max_amount, currency, etc.

        # Clean all string fields to handle NaN values
        title = clean_str(job_data.get("title"), "Unknown Title")
        company = clean_str(job_data.get("company"), "Unknown Company")
        location = clean_str(job_data.get("location"), "")
        description = clean_str(job_data.get("description"), "")
        job_url = clean_str(job_data.get("job_url"), "")
        company_url = clean_value(job_data.get("company_url"))
        if company_url is not None:
            company_url = str(company_url)
        job_type = clean_value(job_data.get("job_type"))
        if job_type is not None:
            job_type = str(job_type)

        # Date handling
        date_posted = clean_value(job_data.get("date_posted"))
        if date_posted is not None:
            date_posted = str(date_posted)

        # Salary handling
        min_amount = clean_value(job_data.get("min_amount"))
        max_amount = clean_value(job_data.get("max_amount"))
        currency = clean_str(job_data.get("currency"), "USD")
        interval = clean_value(job_data.get("interval"))
        if interval is not None:
            interval = str(interval)

        # Convert to annual cents
        salary_min, salary_max = self._normalize_salary(
            min_amount, max_amount, interval
        )

        # Clean raw_data to remove NaN values for JSON serialization
        cleaned_raw_data = {}
        for k, v in job_data.items():
            cleaned_raw_data[k] = clean_value(v)

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
        """Normalize salary to annual cents."""
        if min_val is None and max_val is None:
            return None, None

        # Multipliers to convert to annual
        multipliers = {
            "yearly": 1,
            "monthly": 12,
            "weekly": 52,
            "daily": 260,  # ~5 days/week, 52 weeks
            "hourly": 2080,  # 40 hours/week, 52 weeks
        }

        multiplier = multipliers.get(interval if interval else "", 1)

        min_annual = int(min_val * multiplier * 100) if min_val else None
        max_annual = int(max_val * multiplier * 100) if max_val else None

        return min_annual, max_annual
