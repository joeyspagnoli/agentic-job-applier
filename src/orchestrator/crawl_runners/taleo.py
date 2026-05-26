"""Taleo Enterprise fetcher orchestration entry point."""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from src.database.db_manager import DatabaseManager
from src.fetchers.taleo_fetcher import TaleoFetcher
from src.filters.job_filter import JobFilter
from src.orchestrator.crawl_runners._resolve import resolve_fetcher_attr
from src.orchestrator.insert_pipeline import (
    filter_by_title_patterns,
    resolve_insert_with_filters,
)
from src.utils.deduplicator import Deduplicator
from src.utils.logger import log_crawl_summary


async def fetch_taleo_jobs(
    companies: dict[str, Any],
    db: DatabaseManager,
    deduplicator: Deduplicator,
    *,
    title_include_patterns: list[str] | None = None,
    job_filter: JobFilter | None = None,
) -> tuple[int, int, int, int]:
    """Fetch jobs for every configured Taleo Enterprise company.

    Args:
        companies: Mapping of company names to their Taleo configuration.
        db: Connected database manager used to track crawl metadata and inserts.
        deduplicator: Helper that filters out jobs already present in storage.
        title_include_patterns: Regex patterns a title must match to be kept.
        job_filter: Pre-gate filter instance for hard/soft filtering.

    Returns:
        A tuple of ``(total_discovered, total_new, sources_success,
        sources_failed)`` for the Taleo portion of the cycle.
    """
    fetcher_cls = resolve_fetcher_attr("TaleoFetcher", TaleoFetcher)
    insert_with_filters = resolve_insert_with_filters()

    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    for company_name, config in companies.items():
        tenant_id = config.get("tenant_id")
        career_section = config.get("career_section")
        if not tenant_id or not career_section:
            logger.warning(
                "Taleo config for {} missing tenant_id or career_section, skipping",
                company_name,
            )
            continue

        portal_id = config.get("portal_id")
        if portal_id is not None:
            portal_id = str(portal_id)

        crawl_id: int | None = None
        crawl_jobs_found = 0
        partial_counters = [0, 0, 0, 0]
        start_time = time.time()

        try:
            crawl_id = await db.start_crawl("taleo", company_name)

            async with fetcher_cls(
                company_name,
                str(tenant_id),
                str(career_section),
                portal_id=portal_id,
            ) as fetcher:
                jobs = await fetcher.fetch_jobs()
                if title_include_patterns:
                    jobs = filter_by_title_patterns(jobs, title_include_patterns)
                crawl_jobs_found = len(jobs)
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                await insert_with_filters(
                    new_jobs, db=db, job_filter=job_filter,
                    counters=partial_counters,
                )
                crawl_jobs_new = partial_counters[0] + partial_counters[1]

                duration = time.time() - start_time
                log_crawl_summary(
                    "taleo",
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
                "Error fetching Taleo jobs for {}: {}",
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
