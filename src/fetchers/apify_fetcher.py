"""Fetch and normalize Workday jobs through an Apify actor."""

import asyncio
import os
from collections.abc import Mapping
from types import TracebackType
from typing import Optional

from apify_client import ApifyClient
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.fetchers.errors import FetchError
from src.models.job_posting import JobPosting
from src.utils.json_types import get_str, get_str_opt


class ApifyWorkdayFetcher(BaseFetcher):
    """Fetch job postings from Workday boards using Apify."""

    ACTOR_ID = "gooyer.co/myworkdayjobs"

    def __init__(self, company_name: str, workday_url: str, max_items: int = 100):
        """Store the Workday board information and result limits.

        Purpose:
            Capture the source-specific settings needed to run the Apify actor
            and label the resulting normalized jobs.
        Args:
            self: The Workday fetcher instance being initialized.
            company_name: Human-readable company name used in logs and jobs.
            workday_url: Workday careers URL passed to the Apify actor.
            max_items: Maximum number of rows the actor should return.
        Output:
            Returns `None` after saving the fetcher configuration.
        """

        self.company_name = company_name
        self.workday_url = workday_url
        self.max_items = max_items
        self._client: Optional[ApifyClient] = None
        super().__init__(
            config={"company": company_name, "url": workday_url, "max_items": max_items}
        )

    def get_source_name(self) -> str:
        """Return the source name recorded on Apify Workday jobs.

        Purpose:
            Provide a stable identifier for crawl history and persisted job rows
            that originate from this Workday board.
        Args:
            self: The Workday fetcher reporting its source name.
        Output:
            Returns a machine-friendly source identifier string.
        """

        return f"apify_workday_{self.company_name.lower().replace(' ', '_')}"

    async def __aenter__(self) -> "ApifyWorkdayFetcher":
        """Create the Apify client for the fetcher context.

        Purpose:
            Validate required credentials and prepare the client used to launch
            the Workday scraping actor.
        Args:
            self: The Workday fetcher entering the async context.
        Output:
            Returns the fetcher instance after creating the Apify client.
        """

        api_token = os.getenv("APIFY_API_TOKEN")
        if not api_token:
            raise ValueError("APIFY_API_TOKEN environment variable not set")

        self._client = ApifyClient(api_token)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Clear the Apify client reference when the context ends.

        Purpose:
            Mirror the async context-manager contract even though the Apify
            client itself does not require explicit asynchronous cleanup.
        Args:
            self: The Workday fetcher exiting the async context.
            exc_type: Exception type raised inside the context, if any.
            exc_val: Exception instance raised inside the context, if any.
            exc_tb: Traceback for the exception raised inside the context.
        Output:
            Returns `None` after clearing the stored client reference.
        """

        self._client = None

    async def fetch_jobs(self) -> list[JobPosting]:
        """Run the Apify actor and normalize the returned jobs.

        Purpose:
            Bridge the synchronous Apify client into the async discovery flow,
            then map the resulting dataset items into `JobPosting` objects.
        Args:
            self: The Workday fetcher performing the actor run.
        Output:
            Returns a list of normalized `JobPosting` objects, or an empty list
            when credentials are missing or the actor returns no usable data.
        """

        if not self._client:
            api_token = os.getenv("APIFY_API_TOKEN")
            if not api_token:
                raise FetchError("APIFY_API_TOKEN not set")
            self._client = ApifyClient(api_token)

        logger.info(f"Starting Apify actor for {self.company_name}")
        loop = asyncio.get_event_loop()

        try:
            # The Apify client is synchronous, so the actor call runs in an
            # executor to avoid blocking the orchestrator event loop.
            run_result = await loop.run_in_executor(None, self._run_actor_sync)
        except Exception as e:
            raise FetchError(f"Apify actor failed for {self.company_name}: {e}") from e

        if not run_result:
            raise FetchError(f"Apify actor returned no run result for {self.company_name}")

        try:
            dataset_id = run_result.get("defaultDatasetId")
            if not dataset_id:
                raise FetchError(f"No dataset returned for {self.company_name}")
            if not isinstance(dataset_id, str):
                raise FetchError(f"Unexpected dataset ID type for {self.company_name}")

            # Dataset iteration is also synchronous, so it follows the same
            # executor pattern as the actor launch.
            client = self._client
            if client is None:
                raise FetchError("Apify client was not initialized")
            items = await loop.run_in_executor(
                None,
                lambda: list(client.dataset(dataset_id).iterate_items()),
            )
        except Exception as e:
            raise FetchError(
                f"Failed to fetch Apify results for {self.company_name}: {e}"
            ) from e

        logger.info(f"Fetched {len(items)} jobs from {self.company_name} via Apify")
        return [self._parse_job(item) for item in items]

    def _run_actor_sync(self) -> Optional[dict[str, object]]:
        """Run the Apify actor using the synchronous client API.

        Purpose:
            Isolate the blocking actor invocation so the async fetch path can
            hand it to an executor without mixing sync and async logic.
        Args:
            self: The Workday fetcher running the actor.
        Output:
            Returns the actor run metadata dictionary.
        """
        client = self._client
        if client is None:
            raise FetchError("Apify client was not initialized")
        return client.actor(self.ACTOR_ID).call(
            run_input={
                "startUrls": [{"url": self.workday_url}],
                "maxItems": self.max_items,
            },
            timeout_secs=300,
        )

    def _parse_job(self, job_data: Mapping[str, object]) -> JobPosting:
        """Convert one Apify dataset item into a normalized `JobPosting`.

        Purpose:
            Translate the Workday actor's field names into the shared model used
            by persistence, deduplication, and agent-processing code.
        Args:
            self: The Workday fetcher performing the normalization.
            job_data: Raw dataset item returned by the Apify actor.
        Output:
            Returns a normalized `JobPosting` instance.
        """

        # The actor's field names vary slightly across boards, so each field is
        # pulled from the common alternatives before falling back to defaults.
        title = get_str(job_data, "title") or get_str(job_data, "jobTitle") or "Unknown Title"
        location = get_str(job_data, "location") or get_str(job_data, "jobLocation")
        description = get_str(job_data, "description") or get_str(job_data, "jobDescription")
        url = get_str(job_data, "url") or get_str(job_data, "jobUrl") or self.workday_url
        posted_date = get_str_opt(job_data, "postedDate") or get_str_opt(job_data, "datePosted")

        return JobPosting(
            source=self.get_source_name(),
            source_url=url,
            company=self.company_name,
            company_url=self.workday_url,
            title=title,
            location=location,
            description=description,
            posted_date=posted_date,
            raw_data=dict(job_data),
        )
