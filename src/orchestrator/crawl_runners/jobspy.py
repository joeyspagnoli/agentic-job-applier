"""JobSpy-backed job-board fetcher orchestration entry point."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Literal, cast

from loguru import logger

from src.database.db_manager import DatabaseManager
from src.fetchers.jobspy_fetcher import JobSpyFetcher
from src.filters.job_filter import JobFilter
from src.orchestrator.config_loader import (
    normalize_positive_int,
    normalize_string_list,
)
from src.orchestrator.crawl_runners._resolve import resolve_fetcher_attr
from src.orchestrator.insert_pipeline import (
    filter_by_title_patterns,
    resolve_digest_category,
    resolve_insert_with_filters,
    stamp_digest_category,
)
from src.utils.deduplicator import Deduplicator
from src.utils.logger import log_crawl_summary

# JobSpy's fetcher class only types-checks the three site values it actually
# supports today.  The orchestrator iterates user-supplied board labels, so
# we keep the original validation responsibility on the fetcher itself and
# narrow the lower-cased label to the same Literal here.
_JobSpySite = Literal["indeed", "glassdoor", "linkedin"]


async def fetch_jobspy_jobs(
    job_boards: dict[str, Any],
    db: DatabaseManager,
    deduplicator: Deduplicator,
    *,
    default_search_terms: list[str] | None = None,
    title_include_patterns: list[str] | None = None,
    job_filter: JobFilter | None = None,
) -> tuple[int, int, int, int]:
    """Fetch jobs from enabled job boards through JobSpy.

    Args:
        job_boards: Mapping of job-board settings from ``config/companies.yaml``.
        db: Connected database manager used to track crawl metadata and inserts.
        deduplicator: Helper that filters out jobs already present in storage.
        default_search_terms: Fallback search terms when a board config omits them.
        title_include_patterns: Regex patterns a title must match to be kept.
        job_filter: Pre-gate filter instance for hard/soft filtering.

    Returns:
        A tuple of ``(total_discovered, total_new, sources_success,
        sources_failed)`` for all JobSpy-backed board searches.
    """
    fetcher_cls = resolve_fetcher_attr("JobSpyFetcher", JobSpyFetcher)
    insert_with_filters = resolve_insert_with_filters()

    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    for board_name, config in job_boards.items():
        # Disabled boards stay in config so they can be toggled without deleting
        # search settings, but they should not consume crawl time.
        if not config.get("enabled", False):
            logger.debug(f"Skipping disabled board: {board_name}")
            continue

        # Board labels come from user YAML, so the lower-cased value is a
        # plain ``str`` until the JobSpy fetcher itself validates it.  Cast
        # to the documented Literal so the constructor stays typed, and let
        # the fetcher reject unsupported sites at runtime as before.
        site_name = cast(_JobSpySite, board_name.lower())
        source_name = f"job_boards.{board_name}"
        configured_search_terms = normalize_string_list(
            config.get("search_terms"),
            field_name="search_terms",
            source_name=source_name,
        )
        # Candidate-profile defaults win over the seed defaults baked into
        # companies.yaml — a fresh user's onboarding populates
        # ``search_defaults.job_board_search_terms`` from their target roles
        # ("electrical engineering intern", "fpga intern", ...), and the seed's
        # placeholder ``search_terms: ["software engineer"]`` would otherwise
        # mute that profile entirely. Empty profile defaults still allow the
        # configured terms (or a fully-cleared block) to take effect.
        if default_search_terms:
            search_terms = default_search_terms
        elif configured_search_terms:
            search_terms = configured_search_terms
        else:
            logger.warning(
                "No search terms configured for {} and no profile defaults — skipping",
                board_name,
            )
            continue
        locations = normalize_string_list(
            config.get("locations"),
            field_name="locations",
            source_name=source_name,
        )
        if not locations:
            locations = ["Remote"]
        results_wanted = normalize_positive_int(
            config.get("results_wanted"),
            field_name="results_wanted",
            source_name=source_name,
            default_value=25,
        )

        # JobSpy searches are expanded into one crawl record per query variant
        # so the crawl history shows which search terms are paying off.
        for search_term in search_terms:
            for location in locations:
                crawl_id: int | None = None
                crawl_jobs_found = 0
                partial_counters = [0, 0, 0, 0]
                start_time = time.time()

                try:
                    crawl_id = await db.start_crawl(
                        f"jobspy_{site_name}",
                        f"{search_term}@{location}",
                    )
                    fetcher = fetcher_cls(
                        site_name=site_name,
                        search_term=search_term,
                        location=location,
                        results_wanted=results_wanted,
                    )
                    jobs = await fetcher.fetch_jobs()
                    if title_include_patterns:
                        jobs = filter_by_title_patterns(jobs, title_include_patterns)
                    crawl_jobs_found = len(jobs)
                    new_jobs = await deduplicator.filter_new_jobs(jobs)
                    # Route this board's jobs to the right digest category
                    # (e.g. an Indeed_Business board → "Business") so they only
                    # reach subscribers who opted into that field.
                    stamp_digest_category(new_jobs, resolve_digest_category(config))

                    await insert_with_filters(
                        new_jobs, db=db, job_filter=job_filter,
                        counters=partial_counters,
                    )
                    crawl_jobs_new = partial_counters[0] + partial_counters[1]

                    duration = time.time() - start_time
                    log_crawl_summary(
                        f"jobspy_{site_name}",
                        f"{search_term}@{location}",
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
                        "Error fetching {} jobs for '{}' in {}: {}",
                        site_name,
                        search_term,
                        location,
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

                # A short delay reduces the chance of hammering job boards with
                # back-to-back requests from many search variants.
                await asyncio.sleep(2)

    return total_discovered, total_new, sources_success, sources_failed
