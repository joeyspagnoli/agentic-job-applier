"""Career-page watcher orchestration entry point."""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from src.database.db_manager import DatabaseManager
from src.fetchers.career_page_watcher import CareerPageWatcher
from src.filters.job_filter import JobFilter
from src.orchestrator.fetchers._resolve import resolve_fetcher_attr
from src.orchestrator.insert_pipeline import resolve_insert_with_filters
from src.utils.deduplicator import Deduplicator
from src.utils.logger import log_crawl_summary


async def fetch_career_page_jobs(
    watched_pages: list[dict[str, Any]],
    db: DatabaseManager,
    deduplicator: Deduplicator,
    *,
    job_filter: JobFilter | None = None,
) -> tuple[int, int, int, int]:
    """Fetch new job links from watched career pages.

    Args:
        watched_pages: List of career page configs from ``companies.yaml``.
        db: Connected database manager.
        deduplicator: Dedup helper.
        job_filter: Pre-gate filter instance.

    Returns:
        A tuple of ``(total_discovered, total_new, sources_success,
        sources_failed)``.
    """
    watcher_cls = resolve_fetcher_attr("CareerPageWatcher", CareerPageWatcher)
    insert_with_filters = resolve_insert_with_filters()

    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    for page_config in watched_pages:
        company = page_config.get("company", "Unknown")
        url = page_config.get("url", "")
        if not url:
            continue

        link_selector = page_config.get("link_selector", "a[href*='/jobs/']")
        link_pattern = page_config.get("link_pattern")

        crawl_id: int | None = None
        crawl_jobs_found = 0
        partial_counters = [0, 0, 0, 0]
        start_time = time.time()

        try:
            crawl_id = await db.start_crawl("career_page", company)

            async with watcher_cls(
                company, url,
                link_selector=link_selector,
                link_pattern=link_pattern,
            ) as watcher:
                jobs = await watcher.fetch_jobs()
                crawl_jobs_found = len(jobs)
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                await insert_with_filters(
                    new_jobs, db=db, job_filter=job_filter,
                    counters=partial_counters,
                )
                crawl_jobs_new = partial_counters[0] + partial_counters[1]

                duration = time.time() - start_time
                log_crawl_summary(
                    "career_page", company,
                    crawl_jobs_found, crawl_jobs_new, duration,
                )
                await db.complete_crawl(
                    crawl_id=crawl_id,
                    jobs_found=crawl_jobs_found,
                    jobs_new=crawl_jobs_new,
                )
                sources_success += 1
        except Exception as exc:
            logger.error("Error watching career page for {}: {}", company, exc)
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
