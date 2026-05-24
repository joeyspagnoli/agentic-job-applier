"""Workday fetcher orchestration entry point."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from src.database.db_manager import DatabaseManager
from src.fetchers.workday_fetcher import WorkdayFetcher
from src.filters.job_filter import JobFilter
from src.orchestrator.config_loader import EE_FRIENDLY_INDUSTRIES
from src.orchestrator.fetchers._resolve import resolve_fetcher_attr
from src.orchestrator.insert_pipeline import (
    filter_by_title_patterns,
    resolve_insert_with_filters,
)
from src.utils.deduplicator import Deduplicator
from src.utils.logger import log_crawl_summary

# Per-company crawl ceilings.  Workday tenants for large enterprises (Merck,
# J&J) can return 800+ listings; without this guard the orchestrator runs
# blockingly serial and a single slow/hung tenant stalls every later source
# family.
WORKDAY_PER_COMPANY_TIMEOUT_SEC = 120

# Per-job detail enrichment is on so the tailor receives a real JD body
# instead of an empty string.  Roughly doubles per-tenant wall-clock but
# `INTER_PAGE_SLEEP` inside `WorkdayFetcher` already paces requests well
# under typical Workday 429 thresholds.
WORKDAY_FETCH_DESCRIPTIONS = True


async def fetch_workday_jobs(
    companies: dict[str, Any],
    db: DatabaseManager,
    deduplicator: Deduplicator,
    *,
    title_include_patterns: list[str] | None = None,
    job_filter: JobFilter | None = None,
    loose_job_filter: JobFilter | None = None,
    search_text: str = "",
) -> tuple[int, int, int, int]:
    """Fetch jobs for every configured Workday company via the public CXS API.

    Args:
        companies: Mapping of company names to their Workday configuration.
        db: Connected database manager used to track crawl metadata and inserts.
        deduplicator: Helper that filters out jobs already present in storage.
        title_include_patterns: Regex patterns a title must match to be kept.
        job_filter: Pre-gate filter instance for hard/soft filtering.
        loose_job_filter: Optional relaxed-title clone of ``job_filter`` used
            for tenants whose ``industry`` tag is in
            :data:`EE_FRIENDLY_INDUSTRIES`. The strict ``domain + intern``
            requirement misses EE-relevant titles like "Engineering Intern"
            and "Process Engineering Intern", so for EE-tagged employers we
            relax to "intern (any kind)". Pass ``None`` to use the strict
            filter for every company.
        search_text: Free-text token forwarded to Workday CXS as ``searchText``.
            Anonymous queries with an empty string return only ~40 default-
            sorted results per tenant; passing a token like ``"intern"``
            expands the result set by 10x-20x. Pass ``""`` to preserve the
            legacy default-results behavior.

    Returns:
        A tuple of ``(total_discovered, total_new, sources_success,
        sources_failed)`` for the Workday portion of the cycle.
    """
    fetcher_cls = resolve_fetcher_attr("WorkdayFetcher", WorkdayFetcher)
    insert_with_filters = resolve_insert_with_filters()

    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    for company_name, config in companies.items():
        workday_url = config.get("workday_url")
        if not workday_url:
            logger.warning(f"No workday_url for {company_name}, skipping")
            continue

        crawl_id: int | None = None
        crawl_jobs_found = 0
        partial_counters = [0, 0, 0, 0]
        start_time = time.time()

        try:
            crawl_id = await db.start_crawl("workday", company_name)

            async with fetcher_cls(
                company_name,
                workday_url,
                fetch_descriptions=WORKDAY_FETCH_DESCRIPTIONS,
                search_text=search_text,
            ) as fetcher:
                jobs = await asyncio.wait_for(
                    fetcher.fetch_jobs(),
                    timeout=WORKDAY_PER_COMPANY_TIMEOUT_SEC,
                )
                if title_include_patterns:
                    jobs = filter_by_title_patterns(jobs, title_include_patterns)
                crawl_jobs_found = len(jobs)
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                # Pick a filter based on the company's industry tag — EE-
                # friendly tenants accept any entry-level title; everyone
                # else stays on the strict domain+intern requirement.
                industry = ""
                if isinstance(config, dict):
                    industry_value = config.get("industry")
                    if isinstance(industry_value, str):
                        industry = industry_value
                effective_filter = (
                    loose_job_filter
                    if loose_job_filter is not None
                    and industry in EE_FRIENDLY_INDUSTRIES
                    else job_filter
                )
                await insert_with_filters(
                    new_jobs, db=db, job_filter=effective_filter,
                    counters=partial_counters,
                )
                crawl_jobs_new = partial_counters[0] + partial_counters[1]

                duration = time.time() - start_time
                log_crawl_summary(
                    "workday",
                    company_name,
                    crawl_jobs_found,
                    crawl_jobs_new,
                    duration,
                )
                await db.complete_crawl(
                    crawl_id=crawl_id,
                    jobs_found=crawl_jobs_found,
                    jobs_new=crawl_jobs_new,
                )
                sources_success += 1

        except Exception as exc:
            logger.error(
                "Error fetching Workday jobs for {}: {}",
                company_name,
                exc,
            )
            if crawl_id is not None:
                await db.complete_crawl(
                    crawl_id=crawl_id,
                    jobs_found=crawl_jobs_found,
                    jobs_new=partial_counters[0] + partial_counters[1],
                    error=str(exc),
                )
            sources_failed += 1
        finally:
            total_discovered += crawl_jobs_found
            total_new += partial_counters[0] + partial_counters[1]

    return total_discovered, total_new, sources_success, sources_failed
