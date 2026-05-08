"""GitHub repository (SimplifyJobs and similar) fetcher orchestration."""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from src.database.db_manager import DatabaseManager
from src.fetchers.github_repo_fetcher import GitHubRepoFetcher
from src.filters.job_filter import JobFilter
from src.orchestrator.fetchers._resolve import resolve_fetcher_attr
from src.orchestrator.insert_pipeline import (
    filter_by_title_patterns,
    resolve_insert_with_filters,
)
from src.utils.deduplicator import Deduplicator
from src.utils.logger import log_crawl_summary


async def fetch_github_repo_jobs(
    repos: list[dict[str, Any]],
    db: DatabaseManager,
    deduplicator: Deduplicator,
    *,
    title_include_patterns: list[str] | None = None,
    job_filter: JobFilter | None = None,
) -> tuple[int, int, int, int]:
    """Fetch job listings from configured GitHub internship repositories.

    Args:
        repos: List of repo config dicts from ``companies.yaml``.
        db: Connected database manager.
        deduplicator: Dedup helper.
        title_include_patterns: Regex patterns a title must match.
        job_filter: Pre-gate filter instance.

    Returns:
        A tuple of ``(total_discovered, total_new, sources_success,
        sources_failed)``.
    """
    fetcher_cls = resolve_fetcher_attr("GitHubRepoFetcher", GitHubRepoFetcher)
    insert_with_filters = resolve_insert_with_filters()

    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    for repo_config in repos:
        if not repo_config.get("enabled", True):
            continue

        owner = repo_config.get("owner", "")
        repo_name = repo_config.get("repo", "")
        if not owner or not repo_name:
            logger.warning("GitHub repo config missing owner/repo, skipping")
            continue

        repo_label = f"{owner}/{repo_name}"
        crawl_id: int | None = None
        crawl_jobs_found = 0
        partial_counters = [0, 0, 0, 0]
        start_time = time.time()

        try:
            crawl_id = await db.start_crawl("github_repo", repo_label)

            async with fetcher_cls(
                owner,
                repo_name,
                branch=repo_config.get("branch", "dev"),
                json_path=repo_config.get("json_path", ".github/scripts/listings.json"),
                categories=repo_config.get("categories"),
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
                    "github_repo", repo_label,
                    crawl_jobs_found, crawl_jobs_new, duration,
                )
                await db.complete_crawl(
                    crawl_id=crawl_id,
                    jobs_found=crawl_jobs_found,
                    jobs_new=crawl_jobs_new,
                )
                sources_success += 1
        except Exception as exc:
            logger.error("Error fetching GitHub repo {}: {}", repo_label, exc)
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
