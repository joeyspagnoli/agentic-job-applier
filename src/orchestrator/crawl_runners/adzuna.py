"""Adzuna-backed orchestrator entry point.

The Adzuna public API is a stable, free, API-keyed alternative to
scraping job boards that lack public APIs. This module mirrors
``orchestrator.crawl_runners.jobspy``: it expands a single Adzuna config block
into one crawl per ``search_term × location × country`` combination so
the crawl history reflects which queries are actually paying off.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from loguru import logger

from src.database.db_manager import DatabaseManager
from src.fetchers.adzuna_fetcher import AdzunaFetcher
from src.filters.job_filter import JobFilter
from src.orchestrator.config_loader import (
    normalize_positive_int,
    normalize_string_list,
)
from src.orchestrator.crawl_runners._resolve import resolve_fetcher_attr
from src.orchestrator.insert_pipeline import (
    filter_by_title_patterns,
    resolve_insert_with_filters,
)
from src.utils.deduplicator import Deduplicator
from src.utils.logger import log_crawl_summary

ADZUNA_APP_ID_ENV = "ADZUNA_APP_ID"
ADZUNA_APP_KEY_ENV = "ADZUNA_APP_KEY"


async def fetch_adzuna_jobs(
    adzuna_config: dict[str, Any],
    db: DatabaseManager,
    deduplicator: Deduplicator,
    *,
    default_search_terms: list[str] | None = None,
    title_include_patterns: list[str] | None = None,
    job_filter: JobFilter | None = None,
) -> tuple[int, int, int, int]:
    """Fetch Adzuna jobs across configured search terms × locations.

    Args:
        adzuna_config: Mapping of the ``adzuna:`` block from ``companies.yaml``.
        db: Connected database manager used to track crawl metadata and inserts.
        deduplicator: Helper that filters out jobs already present in storage.
        default_search_terms: Fallback search terms when the block omits them.
        title_include_patterns: Regex patterns a title must match to be kept.
        job_filter: Pre-gate filter instance for hard/soft filtering.

    Returns:
        A tuple of ``(total_discovered, total_new, sources_success,
        sources_failed)`` for all Adzuna search variants.
    """
    if not adzuna_config.get("enabled", False):
        logger.debug("Adzuna disabled; skipping")
        return 0, 0, 0, 0

    app_id = os.environ.get(ADZUNA_APP_ID_ENV, "").strip()
    app_key = os.environ.get(ADZUNA_APP_KEY_ENV, "").strip()
    if not app_id or not app_key:
        logger.warning(
            "Adzuna enabled but {}/{} are not set — skipping",
            ADZUNA_APP_ID_ENV,
            ADZUNA_APP_KEY_ENV,
        )
        return 0, 0, 0, 0

    fetcher_cls = resolve_fetcher_attr("AdzunaFetcher", AdzunaFetcher)
    insert_with_filters = resolve_insert_with_filters()

    source_name = "adzuna"
    country = str(adzuna_config.get("country", "us")).lower().strip() or "us"
    configured_search_terms = normalize_string_list(
        adzuna_config.get("search_terms"),
        field_name="search_terms",
        source_name=source_name,
    )
    if default_search_terms:
        search_terms = default_search_terms
    elif configured_search_terms:
        search_terms = configured_search_terms
    else:
        logger.warning(
            "No search terms configured for Adzuna and no profile defaults — skipping"
        )
        return 0, 0, 0, 0

    locations = normalize_string_list(
        adzuna_config.get("locations"),
        field_name="locations",
        source_name=source_name,
    )
    if not locations:
        locations = [""]  # Empty-string sentinel = whole-country search.

    results_wanted = normalize_positive_int(
        adzuna_config.get("results_wanted"),
        field_name="results_wanted",
        source_name=source_name,
        default_value=50,
    )

    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    for search_term in search_terms:
        for location in locations:
            crawl_id: int | None = None
            crawl_jobs_found = 0
            partial_counters = [0, 0, 0, 0]
            start_time = time.time()
            label = f"{search_term}@{location or 'any'}"

            try:
                crawl_id = await db.start_crawl(f"adzuna_{country}", label)
                fetcher = fetcher_cls(
                    app_id=app_id,
                    app_key=app_key,
                    search_term=search_term,
                    location=location or None,
                    country=country,
                    results_wanted=results_wanted,
                )
                async with fetcher:
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
                    f"adzuna_{country}",
                    label,
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
                    "Error fetching Adzuna jobs for '{}' in {}: {}",
                    search_term,
                    location or "any",
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

            await asyncio.sleep(1)

    return total_discovered, total_new, sources_success, sources_failed
