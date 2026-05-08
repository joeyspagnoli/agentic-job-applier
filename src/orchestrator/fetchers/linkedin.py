"""LinkedIn (guest API) fetcher orchestration entry point."""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

from loguru import logger

from src.database.db_manager import DatabaseManager
from src.fetchers.linkedin_fetcher import LinkedInFetcher
from src.filters.job_filter import JobFilter
from src.orchestrator.fetchers._resolve import resolve_fetcher_attr
from src.orchestrator.insert_pipeline import (
    filter_by_title_patterns,
    resolve_insert_with_filters,
)
from src.utils.deduplicator import Deduplicator
from src.utils.logger import log_crawl_summary


async def fetch_linkedin_jobs(
    linkedin_config: dict[str, Any],
    db: DatabaseManager,
    deduplicator: Deduplicator,
    *,
    default_search_terms: list[str] | None = None,
    title_include_patterns: list[str] | None = None,
    job_filter: JobFilter | None = None,
) -> tuple[int, int, int, int]:
    """Fetch jobs from LinkedIn using the guest API.

    Args:
        linkedin_config: LinkedIn section from ``companies.yaml``.
        db: Connected database manager.
        deduplicator: Dedup helper.
        default_search_terms: Fallback terms from candidate profile when searches
            list is empty.
        title_include_patterns: Regex patterns a title must match.
        job_filter: Pre-gate filter instance.

    Returns:
        A tuple of ``(total_discovered, total_new, sources_success,
        sources_failed)``.
    """
    fetcher_cls = resolve_fetcher_attr("LinkedInFetcher", LinkedInFetcher)
    insert_with_filters = resolve_insert_with_filters()

    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    configured_searches: list[dict[str, Any]] = linkedin_config.get("searches", [])
    # Candidate-profile defaults win over the seed defaults — same reasoning as
    # the JobSpy block. The dist seed keeps ``searches: []`` so this only
    # matters when an advanced user filled in companies.yaml manually; the more
    # common path is a fresh onboarding writing target_roles into the profile.
    if default_search_terms:
        searches = [
            {"search_term": term, "location": "United States"}
            for term in default_search_terms
        ]
    elif configured_searches:
        searches = configured_searches
    else:
        logger.warning("No LinkedIn searches configured and no profile defaults — skipping LinkedIn")
        return total_discovered, total_new, sources_success, sources_failed
    time_range = linkedin_config.get("time_range_seconds", 86400)
    max_pages = linkedin_config.get("max_pages", 4)
    fetch_descriptions = linkedin_config.get("fetch_descriptions", False)

    # Check for aggressive mode in danger settings.
    danger = linkedin_config.get("danger", {})
    if danger.get("aggressive_mode", False):
        time_range = danger.get("aggressive_time_range", 3600)
        max_pages = danger.get("aggressive_max_pages", 10)

    proxy_url = danger.get("proxy_url", "") or None

    for search_index, search_config in enumerate(searches):
        search_term = search_config.get("search_term", "")
        if not search_term:
            continue

        if search_index > 0:
            inter_search_delay = random.uniform(30, 90)
            logger.debug(
                "LinkedIn inter-search delay: {:.0f}s before '{}'",
                inter_search_delay,
                search_term,
            )
            await asyncio.sleep(inter_search_delay)

        location = search_config.get("location", "United States")
        experience_level = search_config.get("experience_level")
        work_type = search_config.get("work_type")

        crawl_id: int | None = None
        crawl_jobs_found = 0
        partial_counters = [0, 0, 0, 0]
        start_time = time.time()

        try:
            crawl_id = await db.start_crawl(
                "linkedin", f"{search_term}@{location}",
            )

            async with fetcher_cls(
                search_term,
                location=location,
                time_range_seconds=time_range,
                experience_level=experience_level,
                work_type=work_type,
                max_pages=max_pages,
                proxy_url=proxy_url,
                fetch_descriptions=fetch_descriptions,
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
                    "linkedin", f"{search_term}@{location}",
                    crawl_jobs_found, crawl_jobs_new, duration,
                )
                await db.complete_crawl(
                    crawl_id=crawl_id,
                    jobs_found=crawl_jobs_found,
                    jobs_new=crawl_jobs_new,
                )
                sources_success += 1
        except Exception as exc:
            logger.error(
                "Error fetching LinkedIn jobs for '{}': {}", search_term, exc,
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
