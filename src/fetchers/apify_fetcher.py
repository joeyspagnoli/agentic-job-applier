"""Apify-based fetcher for Workday job boards."""

import asyncio
import os
from typing import List, Optional

from apify_client import ApifyClient
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.models.job_posting import JobPosting


class ApifyWorkdayFetcher(BaseFetcher):
    """Fetches job postings from Workday using Apify actors.

    Uses the Workday scraper actor from Apify marketplace.
    Requires APIFY_API_TOKEN environment variable.
    """

    # Apify actor for Workday scraping
    ACTOR_ID = "gooyer.co/myworkdayjobs"

    def __init__(self, company_name: str, workday_url: str, max_items: int = 100):
        self.company_name = company_name
        self.workday_url = workday_url
        self.max_items = max_items
        self._client: Optional[ApifyClient] = None
        super().__init__(
            config={"company": company_name, "url": workday_url, "max_items": max_items}
        )

    def get_source_name(self) -> str:
        return f"apify_workday_{self.company_name.lower().replace(' ', '_')}"

    async def __aenter__(self):
        api_token = os.getenv("APIFY_API_TOKEN")
        if not api_token:
            raise ValueError("APIFY_API_TOKEN environment variable not set")
        self._client = ApifyClient(api_token)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._client = None

    async def fetch_jobs(self) -> List[JobPosting]:
        """Fetch jobs from Workday via Apify actor."""
        if not self._client:
            api_token = os.getenv("APIFY_API_TOKEN")
            if not api_token:
                logger.error("APIFY_API_TOKEN not set, skipping Workday fetch")
                return []
            self._client = ApifyClient(api_token)

        logger.info(f"Starting Apify actor for {self.company_name}")

        # Run the actor (this is synchronous in the apify-client library)
        # We'll run it in an executor to not block the event loop
        loop = asyncio.get_event_loop()

        try:
            run_result = await loop.run_in_executor(
                None, self._run_actor_sync
            )
        except Exception as e:
            logger.error(f"Apify actor failed for {self.company_name}: {e}")
            return []

        if not run_result:
            return []

        # Fetch results from the dataset
        try:
            dataset_id = run_result.get("defaultDatasetId")
            if not dataset_id:
                logger.warning(f"No dataset returned for {self.company_name}")
                return []

            items = await loop.run_in_executor(
                None,
                lambda: list(self._client.dataset(dataset_id).iterate_items()),
            )
        except Exception as e:
            logger.error(f"Failed to fetch Apify results for {self.company_name}: {e}")
            return []

        logger.info(f"Fetched {len(items)} jobs from {self.company_name} via Apify")

        return [self._parse_job(item) for item in items]

    def _run_actor_sync(self) -> Optional[dict]:
        """Run the Apify actor synchronously."""
        try:
            run = self._client.actor(self.ACTOR_ID).call(
                run_input={
                    "startUrls": [{"url": self.workday_url}],
                    "maxItems": self.max_items,
                },
                timeout_secs=300,  # 5 minute timeout
            )
            return run
        except Exception as e:
            logger.error(f"Actor call failed: {e}")
            return None

    def _parse_job(self, job_data: dict) -> JobPosting:
        """Convert Apify Workday job data to JobPosting model."""
        # Workday scraper typically returns fields like:
        # title, company, location, description, url, postedDate

        title = job_data.get("title") or job_data.get("jobTitle") or "Unknown Title"
        location = job_data.get("location") or job_data.get("jobLocation") or ""
        description = job_data.get("description") or job_data.get("jobDescription") or ""
        url = job_data.get("url") or job_data.get("jobUrl") or self.workday_url
        posted_date = job_data.get("postedDate") or job_data.get("datePosted")

        return JobPosting(
            source=self.get_source_name(),
            source_url=url,
            company=self.company_name,
            company_url=self.workday_url,
            title=title,
            location=location,
            description=description,
            posted_date=posted_date,
            raw_data=job_data,
        )
