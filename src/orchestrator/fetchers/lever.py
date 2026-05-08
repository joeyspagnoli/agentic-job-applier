"""Lever fetcher orchestration entry point."""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from src.database.db_manager import DatabaseManager
from src.fetchers.lever_fetcher import LeverFetcher
from src.filters.job_filter import JobFilter
from src.orchestrator.fetchers._resolve import resolve_fetcher_attr
from src.orchestrator.insert_pipeline import (
    filter_by_title_patterns,
    resolve_insert_with_filters,
)
from src.utils.deduplicator import Deduplicator
from src.utils.logger import log_crawl_summary


async def fetch_lever_jobs(
    companies: dict[str, Any],
    db: DatabaseManager,
    deduplicator: Deduplicator,
    *,
    title_include_patterns: list[str] | None = None,
    job_filter: JobFilter | None = None,
) -> tuple[int, int, int, int]:
    """Fetch jobs for every configured Lever company.

    Args:
        companies: Mapping of company names to their Lever configuration.
        db: Connected database manager.
        deduplicator: Dedup helper.
        title_include_patterns: Regex patterns a title must match.
        job_filter: Pre-gate filter instance.

    Returns:
        A tuple of ``(total_discovered, total_new, sources_success,
        sources_failed)``.
    """
    fetcher_cls = resolve_fetcher_attr("LeverFetcher", LeverFetcher)
    insert_with_filters = resolve_insert_with_filters()

    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    for company_name, config in companies.items():
        lever_id = config.get("lever_id")
        if not lever_id:
            logger.warning("No lever_id for {}, skipping", company_name)
            continue

        crawl_id: int | None = None
        crawl_jobs_found = 0
        partial_counters = [0, 0, 0, 0]
        start_time = time.time()

        try:
            crawl_id = await db.start_crawl("lever", company_name)

            async with fetcher_cls(company_name, lever_id) as fetcher:
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
                    "lever", company_name, crawl_jobs_found, crawl_jobs_new, duration,
                )
                await db.complete_crawl(
                    crawl_id=crawl_id,
                    jobs_found=crawl_jobs_found,
                    jobs_new=crawl_jobs_new,
                )
                sources_success += 1
        except Exception as exc:
            logger.error("Error fetching Lever jobs for {}: {}", company_name, exc)
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
