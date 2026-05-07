"""Fetch and normalize jobs from Workday public CXS JSON boards."""

import asyncio
import re
from collections.abc import Mapping
from types import TracebackType
from typing import Optional
from urllib.parse import urlparse

import httpx
from loguru import logger

from src.fetchers.base_fetcher import BaseFetcher
from src.fetchers.errors import FetchError
from src.models.job_posting import JobPosting
from src.utils.json_types import get_dict, get_str, get_str_opt


class WorkdayFetcher(BaseFetcher):
    """Fetch job postings from a public Workday board through the CXS API."""

    LIMIT = 20
    """Universally safe per-page batch size; some tenants silently cap above 20."""

    PAGE_CAP = 150
    """Hard limit on paginated requests per company (≈ 3000 jobs)."""

    INTER_PAGE_SLEEP = 0.5
    """Polite delay (seconds) between paginated POSTs to avoid hammering tenants."""

    REQUEST_TIMEOUT = 30.0

    DEFAULT_SITE = "External"

    LOCALE_RE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")

    USER_AGENT = (
        "Mozilla/5.0 (compatible; agentic-job-applier/1.0; +https://github.com/joeyspagnoli/agentic-job-applier)"
    )

    def __init__(
        self,
        company_name: str,
        workday_url: str,
        *,
        fetch_descriptions: bool = True,
        search_text: str = "",
    ) -> None:
        """Store the Workday board metadata and parse its public URL.

        Purpose:
            Capture the company label and pre-parse the public board URL into the
            origin/tenant/site triple needed by every CXS API call.
        Args:
            self: The fetcher instance being initialized.
            company_name: Human-readable company name used in logs and jobs.
            workday_url: Public Workday URL, e.g.
                ``https://imf.wd5.myworkdayjobs.com/IMF``.
            fetch_descriptions: When ``True``, each listing posting is enriched
                via the detail endpoint so descriptions and ISO posted dates are
                populated; when ``False``, only listing fields are kept.
            search_text: Free-text Workday CXS query forwarded as ``searchText``
                in the listing payload. Anonymous queries with an empty string
                return only ~40 default-sorted results per tenant; passing a
                role keyword like ``"intern"`` typically expands the result set
                by 10–20×. Defaults to ``""`` to preserve legacy behavior.
        Output:
            Returns ``None`` after caching parsed URL components.
        """

        self.company_name = company_name
        self.workday_url = workday_url
        self.fetch_descriptions = fetch_descriptions
        self.search_text = search_text
        self._client: Optional[httpx.AsyncClient] = None

        origin, tenant, site = self._parse_board_url(workday_url)
        self.origin = origin
        self.tenant = tenant
        self.site = site

        super().__init__(
            config={
                "company": company_name,
                "url": workday_url,
                "tenant": tenant,
                "site": site,
            }
        )

    def get_source_name(self) -> str:
        """Return the source identifier recorded on Workday jobs.

        Purpose:
            Provide a stable, human-readable source label for crawl history and
            persisted job rows originating from this Workday board.
        Args:
            self: The fetcher reporting its source name.
        Output:
            Returns a machine-friendly source identifier string.
        """

        return f"workday_{self.company_name.lower().replace(' ', '_')}"

    @staticmethod
    def _parse_board_url(url: str) -> tuple[str, str, str]:
        """Split a public Workday URL into ``(origin, tenant, site)``.

        Purpose:
            Convert the user-facing board URL into the components needed to call
            the CXS endpoints, while gracefully skipping locale path segments.
        Args:
            url: Public Workday board URL such as
                ``https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite``.
        Output:
            Returns a tuple ``(origin, tenant, site)``. ``site`` defaults to
            ``"External"`` when the path is empty or only a locale segment.
        Raises:
            ValueError: If the URL is missing a parseable host.
        """

        target = url if url.startswith("http") else f"https://{url}"
        parts = urlparse(target)

        if not parts.netloc:
            raise ValueError(f"Invalid Workday URL: {url!r}")

        origin = f"{parts.scheme}://{parts.netloc}"
        tenant = parts.netloc.split(".")[0]
        site = next(
            (
                segment
                for segment in parts.path.split("/")
                if segment and not WorkdayFetcher.LOCALE_RE.match(segment)
            ),
            WorkdayFetcher.DEFAULT_SITE,
        )
        return origin, tenant, site

    async def __aenter__(self) -> "WorkdayFetcher":
        """Create the shared HTTP client used during the crawl.

        Purpose:
            Reuse a single async client across every list and detail request so
            connection pooling and headers stay consistent.
        Args:
            self: The fetcher entering the async context.
        Output:
            Returns the fetcher instance after creating the HTTP client.
        """

        self._client = self._build_client()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the shared HTTP client when the crawl context ends.

        Purpose:
            Release the client's network resources once the caller is finished
            using the fetcher.
        Args:
            self: The fetcher exiting the async context.
            exc_type: Exception type raised inside the context, if any.
            exc_val: Exception instance raised inside the context, if any.
            exc_tb: Traceback for the exception raised inside the context.
        Output:
            Returns ``None`` after closing and clearing the HTTP client.
        """

        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _build_client(self) -> httpx.AsyncClient:
        """Construct the configured HTTP client used for CXS requests.

        Purpose:
            Centralize default headers and timeout values so list and detail
            requests stay symmetric and friendly to tenants.
        Args:
            self: The fetcher building its HTTP client.
        Output:
            Returns a configured ``httpx.AsyncClient`` ready to use.
        """

        return httpx.AsyncClient(
            timeout=self.REQUEST_TIMEOUT,
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "application/json",
                "Referer": f"{self.origin}/{self.site}",
            },
        )

    async def fetch_jobs(self) -> list[JobPosting]:
        """Paginate the Workday CXS listing endpoint and normalize results.

        Purpose:
            Drive the full crawl flow for one Workday board: list pages, optional
            per-job detail enrichment, and return ready-to-persist postings.
        Args:
            self: The fetcher performing the crawl.
        Output:
            Returns a list of normalized ``JobPosting`` records. Returns an empty
            list when the tenant is gated by Cloudflare/Akamai or rate-limited.
        Raises:
            FetchError: When an unexpected transport error or unrecoverable HTTP
                status terminates the crawl.
        """

        if self._client is None:
            self._client = self._build_client()

        postings: list[JobPosting] = []
        offset = 0
        page_index = 0
        total_known: int | None = None

        while page_index < self.PAGE_CAP:
            page = await self._list_page(offset)
            if page is None:
                # Cloudflare/Akamai gating or rate limit on first call → fail-soft.
                return []

            raw_jobs = page.get("jobPostings") or []
            if not isinstance(raw_jobs, list) or not raw_jobs:
                break

            total_value = page.get("total")
            if isinstance(total_value, int):
                total_known = total_value

            for raw in raw_jobs:
                if not isinstance(raw, dict):
                    continue
                posting = self._parse_listing_job(raw)

                if self.fetch_descriptions:
                    external_path = get_str(raw, "externalPath")
                    if external_path:
                        detail = await self._fetch_detail(external_path)
                        if detail is not None:
                            posting = self._enrich_with_detail(posting, detail)

                postings.append(posting)

            offset += self.LIMIT
            page_index += 1

            if total_known is not None and offset >= total_known:
                break

            await asyncio.sleep(self.INTER_PAGE_SLEEP)

        if page_index >= self.PAGE_CAP:
            logger.warning(
                "Workday page cap ({}) reached for {}; stopping pagination",
                self.PAGE_CAP,
                self.company_name,
            )

        logger.debug(
            "Fetched {} jobs from Workday tenant {} ({})",
            len(postings),
            self.tenant,
            self.company_name,
        )
        return postings

    async def _list_page(self, offset: int) -> dict | None:
        """Fetch a single CXS listing page, retrying ``/jobs/search`` on 404.

        Purpose:
            Encapsulate the POST request, common failure-mode handling, and the
            ``/jobs`` → ``/jobs/search`` retry contract.
        Args:
            self: The fetcher issuing the listing call.
            offset: Pagination offset for the current page.
        Output:
            Returns the parsed JSON object on success, or ``None`` when the call
            should be treated as fail-soft (Cloudflare gate or 429).
        Raises:
            FetchError: When an unexpected error or non-recoverable HTTP status
                ends the crawl.
        """

        body = {
            "appliedFacets": {},
            "limit": self.LIMIT,
            "offset": offset,
            "searchText": self.search_text,
        }

        page = await self._post_jobs(f"/wday/cxs/{self.tenant}/{self.site}/jobs", body)
        if page == "retry":
            page = await self._post_jobs(
                f"/wday/cxs/{self.tenant}/{self.site}/jobs/search", body
            )
            if page == "retry":
                logger.warning(
                    "Workday listing endpoint not found for {} (tenant={}, site={})",
                    self.company_name,
                    self.tenant,
                    self.site,
                )
                return None
        if isinstance(page, str):
            return None
        return page

    async def _post_jobs(self, path: str, body: dict) -> dict | str | None:
        """POST a CXS listing request and translate the HTTP response.

        Purpose:
            Centralize the small status-code state machine shared between the
            primary ``/jobs`` endpoint and the ``/jobs/search`` retry path.
        Args:
            self: The fetcher issuing the request.
            path: Path component appended to the tenant origin.
            body: JSON payload sent in the POST request.
        Output:
            Returns the parsed JSON dict on success, the literal ``"retry"`` to
            signal the caller should retry on the search endpoint, or ``None``
            when the tenant is gated/rate-limited and the crawl should fail-soft.
        Raises:
            FetchError: When the response indicates an unrecoverable failure.
        """

        client = self._client
        if client is None:
            raise FetchError("Workday HTTP client was not initialized")

        url = f"{self.origin}{path}"
        try:
            response = await client.post(url, json=body)
        except httpx.RequestError as exc:
            raise FetchError(
                f"Network error fetching Workday {self.company_name}: {exc}"
            ) from exc

        status = response.status_code

        if 200 <= status < 300:
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                # Some tenants serve a Cloudflare interstitial as 200 HTML.
                if self._is_blocked_response(status, response.text):
                    logger.warning(
                        "Workday tenant {} appears to be gated by Cloudflare/Akamai",
                        self.tenant,
                    )
                    return None
                raise FetchError(
                    f"Unexpected non-JSON response for {self.company_name}: {content_type}"
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise FetchError(
                    f"Invalid JSON from Workday {self.company_name}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise FetchError(
                    f"Unexpected listing payload type for {self.company_name}"
                )
            return payload

        if status == 404:
            return "retry"

        if status == 429:
            logger.warning("Rate limited by Workday for {}", self.company_name)
            return None

        if status in (401, 403):
            if self._is_blocked_response(status, response.text):
                logger.warning(
                    "Workday tenant {} returned {} (likely Cloudflare/Akamai gate); skipping",
                    self.tenant,
                    status,
                )
                return None
            raise FetchError(
                f"Authorization failure ({status}) from Workday {self.company_name}"
            )

        raise FetchError(
            f"Unexpected HTTP {status} from Workday {self.company_name}"
        )

    async def _fetch_detail(self, external_path: str) -> dict | None:
        """Fetch the per-job detail payload, returning ``None`` on minor errors.

        Purpose:
            Pull richer fields (full description HTML, ISO posted date, canonical
            URL) without aborting the whole crawl when a single posting fails.
        Args:
            self: The fetcher issuing the detail call.
            external_path: ``externalPath`` value from the listing entry.
        Output:
            Returns the parsed detail JSON on success, or ``None`` when the
            individual posting cannot be retrieved.
        """

        client = self._client
        if client is None:
            return None

        normalized_path = external_path if external_path.startswith("/") else f"/{external_path}"
        url = f"{self.origin}/wday/cxs/{self.tenant}/{self.site}{normalized_path}"

        try:
            response = await client.get(url)
        except httpx.RequestError as exc:
            logger.debug(
                "Workday detail network error for {} ({}): {}",
                self.company_name,
                external_path,
                exc,
            )
            return None

        if response.status_code != 200:
            logger.debug(
                "Workday detail returned {} for {} ({})",
                response.status_code,
                self.company_name,
                external_path,
            )
            return None

        try:
            payload = response.json()
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    def _parse_listing_job(self, raw: Mapping[str, object]) -> JobPosting:
        """Convert a CXS listing entry into a baseline ``JobPosting``.

        Purpose:
            Turn the lightweight listing record into a normalized posting that
            can stand on its own when detail enrichment is skipped or fails.
        Args:
            self: The fetcher performing the normalization.
            raw: Raw listing entry from the CXS ``/jobs`` response.
        Output:
            Returns a normalized ``JobPosting``.
        """

        title = get_str(raw, "title", "Unknown Title")
        location = get_str(raw, "locationsText")
        external_path = get_str(raw, "externalPath")
        posted_date = get_str_opt(raw, "postedOn")

        source_url = (
            f"{self.origin}/{self.site}{external_path}"
            if external_path
            else self.workday_url
        )

        return JobPosting(
            source=self.get_source_name(),
            source_url=source_url,
            company=self.company_name,
            company_url=self.workday_url,
            title=title,
            location=location,
            description="",
            posted_date=posted_date,
            raw_data=dict(raw),
        )

    def _enrich_with_detail(
        self, posting: JobPosting, detail: Mapping[str, object]
    ) -> JobPosting:
        """Layer detail-endpoint fields on top of a listing-derived posting.

        Purpose:
            Replace listing placeholders with the canonical title, full plain-text
            description, ISO posted date, and apply URL when available.
        Args:
            self: The fetcher performing the enrichment.
            posting: Posting produced from the listing entry.
            detail: Parsed JSON payload from the detail endpoint.
        Output:
            Returns a new ``JobPosting`` with enriched fields applied.
        """

        info = get_dict(detail, "jobPostingInfo") or {}

        title = get_str(info, "title") or posting.title
        external_url = get_str(info, "externalUrl")
        description_html = get_str(info, "jobDescription")
        description = (
            self._clean_html(description_html) if description_html else posting.description
        )
        start_date = get_str_opt(info, "startDate") or posting.posted_date

        merged_raw: dict[str, object] = dict(posting.raw_data)
        merged_raw["jobPostingInfo"] = dict(info)

        return posting.model_copy(
            update={
                "title": title,
                "source_url": external_url or posting.source_url,
                "description": description,
                "posted_date": start_date,
                "raw_data": merged_raw,
            }
        )

    @staticmethod
    def _clean_html(html: str) -> str:
        """Strip HTML tags and collapse whitespace from job description text.

        Purpose:
            Produce a plain-text description suitable for hashing, storage, and
            downstream prompt construction.
        Args:
            html: Raw HTML string from ``jobPostingInfo.jobDescription``.
        Output:
            Returns the cleaned plain-text description.
        """

        if not html:
            return ""
        text = re.sub(r"<[^>]+>", " ", html)
        # The tag regex only matches balanced pairs; scrub stray angle
        # brackets so cleaned descriptions never leak into prompt context.
        text = text.replace("<", " ").replace(">", " ")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _is_blocked_response(status: int, body: str) -> bool:
        """Check whether a response looks like a Cloudflare/Akamai gate.

        Purpose:
            Identify common bot-mitigation interstitials so the crawler can
            fail-soft for the affected tenant instead of crashing.
        Args:
            status: HTTP status code of the response.
            body: Response body, expected to be HTML when blocked.
        Output:
            Returns ``True`` when the response shape matches a known gating
            pattern; ``False`` otherwise.
        """

        if not body:
            return status in (401, 403)
        sample = body[:4096].lower()
        markers = (
            "cloudflare",
            "cf-chl",
            "attention required",
            "akamai",
            "access denied",
            "<!doctype html",
        )
        return any(marker in sample for marker in markers)
