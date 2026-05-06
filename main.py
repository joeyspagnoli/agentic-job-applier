"""Run the main job discovery workflow for the repository.

This module loads configuration, coordinates each fetcher, filters duplicates,
stores new postings, and records crawl-level metrics for later inspection.
"""

import asyncio
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from loguru import logger

from src.database.db_manager import DatabaseManager
from src.fetchers.ashby_fetcher import AshbyFetcher
from src.fetchers.career_page_watcher import CareerPageWatcher
from src.fetchers.github_repo_fetcher import GitHubRepoFetcher
from src.fetchers.greenhouse_fetcher import GreenhouseFetcher
from src.fetchers.jobspy_fetcher import JobSpyFetcher
from src.fetchers.lever_fetcher import LeverFetcher
from src.fetchers.linkedin_fetcher import LinkedInFetcher
from src.fetchers.workday_fetcher import WorkdayFetcher
from src.filters.job_filter import FilterAction, JobFilter
from src.models.job_posting import JobPosting
from src.utils.deduplicator import Deduplicator
from src.utils.logger import log_crawl_summary, log_cycle_summary, setup_logger
from src.utils.paths import resolve_database_path


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file and return the parsed mapping.

    Purpose:
        Centralize YAML loading so the orchestrator can read repo config files
        without repeating file-handling logic.
    Args:
        path: Filesystem path to the YAML file that should be parsed.
    Output:
        Returns the parsed YAML content as a dictionary.
    """

    # The orchestrator relies on YAML configs for source definitions, so this
    # helper keeps parsing behavior consistent anywhere config is loaded.
    with open(path) as f:
        loaded = yaml.safe_load(f)
        if isinstance(loaded, dict):
            return loaded
        return {}


def load_optional_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping when present, otherwise return an empty mapping.

    Purpose:
        Support optional configuration files while keeping discovery resilient
        when users have not created every optional config artifact yet.
    Args:
        path: Filesystem path to the YAML file that may or may not exist.
    Output:
        Returns the parsed YAML mapping when available, otherwise `{}`.
    """

    if not path.exists():
        return {}
    return load_yaml(path)


def _normalize_string_list(
    value: Any,
    *,
    field_name: str,
    source_name: str,
) -> list[str]:
    """Normalize config values into a non-empty list of strings.

    Purpose:
        Protect fan-out loops from malformed YAML values such as a scalar
        string or mixed-type lists that would otherwise create noisy failures.
    Args:
        value: Raw config value to normalize.
        field_name: Human-readable field name for warning logs.
        source_name: Config section label used in warning logs.
    Output:
        Returns a list of non-empty trimmed strings.
    """

    if value is None:
        return []

    if not isinstance(value, list):
        logger.warning(
            "Expected list for {}.{}; got {}. Ignoring value.",
            source_name,
            field_name,
            type(value).__name__,
        )
        return []

    normalized_values: list[str] = []
    for item in value:
        normalized_item = str(item).strip()
        if normalized_item:
            normalized_values.append(normalized_item)
    return normalized_values


def _normalize_positive_int(
    value: Any,
    *,
    field_name: str,
    source_name: str,
    default_value: int,
) -> int:
    """Normalize a positive integer config value with fallback behavior.

    Purpose:
        Keep numeric crawl configuration deterministic even when YAML values
        are missing, malformed, or non-positive.
    Args:
        value: Raw config value to normalize.
        field_name: Human-readable field name for warning logs.
        source_name: Config section label used in warning logs.
        default_value: Fallback value when normalization fails.
    Output:
        Returns a positive integer.
    """

    if value is None:
        return default_value

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        logger.warning(
            "Expected integer for {}.{}; got {!r}. Using default {}.",
            source_name,
            field_name,
            value,
            default_value,
        )
        return default_value

    if parsed <= 0:
        logger.warning(
            "Expected positive integer for {}.{}; got {}. Using default {}.",
            source_name,
            field_name,
            parsed,
            default_value,
        )
        return default_value
    return parsed


def resolve_job_board_default_search_terms(
    *,
    search_criteria_config: dict[str, Any],
    candidate_profile_config: dict[str, Any],
) -> list[str]:
    """Resolve default board search terms from profile and search criteria.

    Purpose:
        Keep discovery targeting config-driven and agnostic by deriving fallback
        query terms from user-owned config rather than hardcoded role strings.
    Args:
        search_criteria_config: Parsed `config/search_criteria.yaml` mapping.
        candidate_profile_config: Parsed `config/candidate_profile.yaml` mapping.
    Output:
        Returns an ordered list of unique default search terms.
    """

    search_defaults = candidate_profile_config.get("search_defaults", {})
    if not isinstance(search_defaults, dict):
        search_defaults = {}

    defaults_from_profile = _normalize_string_list(
        search_defaults.get("job_board_search_terms"),
        field_name="search_defaults.job_board_search_terms",
        source_name="candidate_profile",
    )
    defaults_from_criteria = _normalize_string_list(
        search_criteria_config.get("target_titles"),
        field_name="target_titles",
        source_name="search_criteria",
    )

    combined_defaults = defaults_from_profile + defaults_from_criteria

    unique_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in combined_defaults:
        normalized_term = str(term).strip()
        if not normalized_term:
            continue
        dedup_key = normalized_term.casefold()
        if dedup_key in seen_terms:
            continue
        seen_terms.add(dedup_key)
        unique_terms.append(normalized_term)

    return unique_terms


def _filter_by_title_patterns(
    jobs: list[JobPosting],
    include_patterns: list[str],
) -> list[JobPosting]:
    """Keep only jobs whose title matches at least one include pattern."""
    if not include_patterns:
        return jobs
    compiled = [re.compile(p, re.IGNORECASE) for p in include_patterns]
    return [j for j in jobs if any(rx.search(j.title) for rx in compiled)]


async def _insert_with_filters(
    jobs: list[JobPosting],
    *,
    db: DatabaseManager,
    job_filter: JobFilter | None,
    counters: list[int] | None = None,
) -> tuple[int, int, int, int]:
    """Insert jobs after applying pre-gate filters.

    Runs each job through the filter pipeline and inserts according to the
    resulting action.  Returns counts for downstream crawl accounting.

    Args:
        jobs: Deduplicated job postings ready for filtering and insertion.
        db: Connected database manager for persistence.
        job_filter: Pre-gate filter instance, or ``None`` to skip filtering.
        counters: Optional 4-element list mutated in place as inserts happen.
            Lets the caller observe partial progress if an insert raises.

    Returns:
        A tuple of ``(inserted_new, inserted_qualified, soft_filtered,
        hard_rejected)`` counts.
    """
    if counters is None:
        counters = [0, 0, 0, 0]

    for job in jobs:
        if job_filter is not None:
            action, reason = job_filter.filter_job(job)
        else:
            action = FilterAction.ACCEPT_NEW
            reason = "no filter configured"

        if action == FilterAction.REJECT:
            logger.debug("Hard-rejected {}: {}", job.title, reason)
            counters[3] += 1
            continue

        db_dict = job.to_db_dict()

        if action == FilterAction.REJECT_FILTERED:
            db_dict["status"] = "FILTERED"
            was_inserted = await db.insert_job(db_dict)
            if was_inserted:
                counters[2] += 1
                logger.debug("Soft-filtered {}: {}", job.title, reason)

        elif action == FilterAction.ACCEPT_QUALIFIED:
            db_dict["status"] = "QUALIFIED"
            was_inserted = await db.insert_job(db_dict)
            if was_inserted:
                counters[1] += 1
                logger.debug("Auto-qualified {}: {}", job.title, reason)

        else:
            was_inserted = await db.insert_job(db_dict)
            if was_inserted:
                counters[0] += 1

    return counters[0], counters[1], counters[2], counters[3]


async def fetch_greenhouse_jobs(
    companies: dict,
    db: DatabaseManager,
    deduplicator: Deduplicator,
    *,
    title_include_patterns: list[str] | None = None,
    job_filter: JobFilter | None = None,
) -> tuple[int, int, int, int]:
    """Fetch jobs for every configured Greenhouse company.

    Args:
        companies: Mapping of company names to their Greenhouse configuration.
        db: Connected database manager used to track crawl metadata and inserts.
        deduplicator: Helper that filters out jobs already present in storage.
        title_include_patterns: Regex patterns a title must match to be kept.
        job_filter: Pre-gate filter instance for hard/soft filtering.

    Returns:
        A tuple of ``(total_discovered, total_new, sources_success,
        sources_failed)`` for the Greenhouse portion of the cycle.
    """
    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    for company_name, config in companies.items():
        greenhouse_id = config.get("greenhouse_id")
        if not greenhouse_id:
            logger.warning(f"No greenhouse_id for {company_name}, skipping")
            continue

        crawl_id: int | None = None
        crawl_jobs_found = 0
        partial_counters = [0, 0, 0, 0]
        start_time = time.time()

        try:
            crawl_id = await db.start_crawl("greenhouse", company_name)

            async with GreenhouseFetcher(company_name, greenhouse_id) as fetcher:
                jobs = await fetcher.fetch_jobs()
                if title_include_patterns:
                    jobs = _filter_by_title_patterns(jobs, title_include_patterns)
                crawl_jobs_found = len(jobs)
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                await _insert_with_filters(
                    new_jobs, db=db, job_filter=job_filter,
                    counters=partial_counters,
                )
                crawl_jobs_new = partial_counters[0] + partial_counters[1]

                duration = time.time() - start_time
                log_crawl_summary(
                    "greenhouse",
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
                "Error fetching Greenhouse jobs for {}: {}",
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


async def fetch_workday_jobs(
    companies: dict,
    db: DatabaseManager,
    deduplicator: Deduplicator,
    *,
    title_include_patterns: list[str] | None = None,
    job_filter: JobFilter | None = None,
) -> tuple[int, int, int, int]:
    """Fetch jobs for every configured Workday company via the public CXS API.

    Args:
        companies: Mapping of company names to their Workday configuration.
        db: Connected database manager used to track crawl metadata and inserts.
        deduplicator: Helper that filters out jobs already present in storage.
        title_include_patterns: Regex patterns a title must match to be kept.
        job_filter: Pre-gate filter instance for hard/soft filtering.

    Returns:
        A tuple of ``(total_discovered, total_new, sources_success,
        sources_failed)`` for the Workday portion of the cycle.
    """
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

            async with WorkdayFetcher(company_name, workday_url) as fetcher:
                jobs = await fetcher.fetch_jobs()
                if title_include_patterns:
                    jobs = _filter_by_title_patterns(jobs, title_include_patterns)
                crawl_jobs_found = len(jobs)
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                await _insert_with_filters(
                    new_jobs, db=db, job_filter=job_filter,
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


async def fetch_jobspy_jobs(
    job_boards: dict,
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

        site_name = board_name.lower()
        source_name = f"job_boards.{board_name}"
        configured_search_terms = _normalize_string_list(
            config.get("search_terms"),
            field_name="search_terms",
            source_name=source_name,
        )
        if configured_search_terms:
            search_terms = configured_search_terms
        elif default_search_terms:
            search_terms = default_search_terms
        else:
            logger.warning(
                "No search terms configured for {} and no profile defaults — skipping",
                board_name,
            )
            continue
        locations = _normalize_string_list(
            config.get("locations"),
            field_name="locations",
            source_name=source_name,
        )
        if not locations:
            locations = ["Remote"]
        results_wanted = _normalize_positive_int(
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
                    fetcher = JobSpyFetcher(
                        site_name=site_name,
                        search_term=search_term,
                        location=location,
                        results_wanted=results_wanted,
                    )
                    jobs = await fetcher.fetch_jobs()
                    if title_include_patterns:
                        jobs = _filter_by_title_patterns(jobs, title_include_patterns)
                    crawl_jobs_found = len(jobs)
                    new_jobs = await deduplicator.filter_new_jobs(jobs)

                    await _insert_with_filters(
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


async def fetch_lever_jobs(
    companies: dict,
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

            async with LeverFetcher(company_name, lever_id) as fetcher:
                jobs = await fetcher.fetch_jobs()
                if title_include_patterns:
                    jobs = _filter_by_title_patterns(jobs, title_include_patterns)
                crawl_jobs_found = len(jobs)
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                await _insert_with_filters(
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


async def fetch_ashby_jobs(
    companies: dict,
    db: DatabaseManager,
    deduplicator: Deduplicator,
    *,
    title_include_patterns: list[str] | None = None,
    job_filter: JobFilter | None = None,
) -> tuple[int, int, int, int]:
    """Fetch jobs for every configured Ashby company.

    Args:
        companies: Mapping of company names to their Ashby configuration.
        db: Connected database manager.
        deduplicator: Dedup helper.
        title_include_patterns: Regex patterns a title must match.
        job_filter: Pre-gate filter instance.

    Returns:
        A tuple of ``(total_discovered, total_new, sources_success,
        sources_failed)``.
    """
    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    for company_name, config in companies.items():
        board_id = config.get("board_id")
        if not board_id:
            logger.warning("No board_id for {}, skipping", company_name)
            continue

        crawl_id: int | None = None
        crawl_jobs_found = 0
        partial_counters = [0, 0, 0, 0]
        start_time = time.time()

        try:
            crawl_id = await db.start_crawl("ashby", company_name)

            async with AshbyFetcher(company_name, board_id) as fetcher:
                jobs = await fetcher.fetch_jobs()
                if title_include_patterns:
                    jobs = _filter_by_title_patterns(jobs, title_include_patterns)
                crawl_jobs_found = len(jobs)
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                await _insert_with_filters(
                    new_jobs, db=db, job_filter=job_filter,
                    counters=partial_counters,
                )
                crawl_jobs_new = partial_counters[0] + partial_counters[1]

                duration = time.time() - start_time
                log_crawl_summary(
                    "ashby", company_name, crawl_jobs_found, crawl_jobs_new, duration,
                )
                await db.complete_crawl(
                    crawl_id=crawl_id,
                    jobs_found=crawl_jobs_found,
                    jobs_new=crawl_jobs_new,
                )
                sources_success += 1
        except Exception as exc:
            logger.error("Error fetching Ashby jobs for {}: {}", company_name, exc)
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


async def fetch_github_repo_jobs(
    repos: list[dict],
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

            async with GitHubRepoFetcher(
                owner,
                repo_name,
                branch=repo_config.get("branch", "dev"),
                json_path=repo_config.get("json_path", ".github/scripts/listings.json"),
                categories=repo_config.get("categories"),
            ) as fetcher:
                jobs = await fetcher.fetch_jobs()
                if title_include_patterns:
                    jobs = _filter_by_title_patterns(jobs, title_include_patterns)
                crawl_jobs_found = len(jobs)
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                await _insert_with_filters(
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


async def fetch_linkedin_jobs(
    linkedin_config: dict,
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
    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    configured_searches: list[dict] = linkedin_config.get("searches", [])
    if configured_searches:
        searches = configured_searches
    elif default_search_terms:
        searches = [{"search_term": t, "location": "United States"} for t in default_search_terms]
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

            async with LinkedInFetcher(
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
                    jobs = _filter_by_title_patterns(jobs, title_include_patterns)
                crawl_jobs_found = len(jobs)
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                await _insert_with_filters(
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


async def fetch_career_page_jobs(
    watched_pages: list[dict],
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

            async with CareerPageWatcher(
                company, url,
                link_selector=link_selector,
                link_pattern=link_pattern,
            ) as watcher:
                jobs = await watcher.fetch_jobs()
                crawl_jobs_found = len(jobs)
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                await _insert_with_filters(
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


async def run_job_discovery() -> None:
    """Run one complete discovery cycle across every configured source.

    Purpose:
        Coordinate configuration loading, database setup, per-source crawling,
        daily statistics updates, and the final cycle summary log.
    Args:
        None.
    Output:
        Returns `None` after completing one discovery cycle and persisting the
        resulting jobs and metrics.
    """
    cycle_start = time.time()

    # The start banner makes timer-driven runs easy to spot when reviewing
    # logs from systemd, cron, or interactive executions.
    logger.info("=" * 60)
    logger.info("STARTING JOB DISCOVERY CYCLE")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info("=" * 60)

    # Source configuration lives in the repo so operational changes can be
    # versioned alongside code updates.
    config_dir = Path(__file__).parent / "config"
    companies_config = load_yaml(config_dir / "companies.yaml")
    search_criteria_config = load_optional_yaml(config_dir / "search_criteria.yaml")
    candidate_profile_config = load_optional_yaml(config_dir / "candidate_profile.yaml")
    filters_config = load_optional_yaml(config_dir / "filters.yaml")
    default_search_terms = resolve_job_board_default_search_terms(
        search_criteria_config=search_criteria_config,
        candidate_profile_config=candidate_profile_config,
    )
    title_include_patterns = _normalize_string_list(
        search_criteria_config.get("include_title_patterns"),
        field_name="include_title_patterns",
        source_name="search_criteria",
    )

    # Pre-gate filters reduce gate agent invocations by auto-rejecting or
    # auto-qualifying jobs that are obviously outside the user's criteria.
    job_filter: JobFilter | None = None
    if filters_config:
        job_filter = JobFilter(filters_config)
        logger.info("Pre-gate filters loaded from config/filters.yaml")

    # The database layer owns schema creation and lightweight migrations so each
    # run can safely bootstrap a fresh local environment.
    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_agent_schema()
        deduplicator = Deduplicator(db)

        # Totals are accumulated across all source families so one final daily
        # stats row can summarize the whole cycle.
        total_discovered = 0
        total_new = 0
        total_duplicate = 0
        sources_success = 0
        sources_failed = 0

        # Each source family is optional in config. Empty sections are skipped
        # so users can enable integrations incrementally.
        greenhouse_companies = companies_config.get("greenhouse_companies", {})
        if greenhouse_companies:
            logger.info(
                f"Fetching from {len(greenhouse_companies)} Greenhouse companies..."
            )
            d, n, s, f = await fetch_greenhouse_jobs(
                greenhouse_companies, db, deduplicator,
                title_include_patterns=title_include_patterns,
                job_filter=job_filter,
            )
            total_discovered += d
            total_new += n
            total_duplicate += d - n
            sources_success += s
            sources_failed += f

        # Workday uses a different provider path, but the orchestrator still
        # folds its counts into the same cycle summary.
        workday_companies = companies_config.get("workday_companies", {})
        if workday_companies:
            logger.info(f"Fetching from {len(workday_companies)} Workday companies...")
            d, n, s, f = await fetch_workday_jobs(
                workday_companies, db, deduplicator,
                title_include_patterns=title_include_patterns,
                job_filter=job_filter,
            )
            total_discovered += d
            total_new += n
            total_duplicate += d - n
            sources_success += s
            sources_failed += f

        # Job boards are counted by enabled boards because each board can fan
        # out into multiple search-term and location combinations.
        job_boards = companies_config.get("job_boards", {})
        if job_boards:
            enabled_boards = [b for b, c in job_boards.items() if c.get("enabled")]
            logger.info(f"Fetching from {len(enabled_boards)} job boards...")
            d, n, s, f = await fetch_jobspy_jobs(
                job_boards,
                db,
                deduplicator,
                default_search_terms=default_search_terms,
                title_include_patterns=title_include_patterns,
                job_filter=job_filter,
            )
            total_discovered += d
            total_new += n
            total_duplicate += d - n
            sources_success += s
            sources_failed += f

        # Lever companies (free public API, same pattern as Greenhouse).
        lever_companies = companies_config.get("lever_companies", {})
        if lever_companies:
            logger.info(
                "Fetching from {} Lever companies...", len(lever_companies),
            )
            d, n, s, f = await fetch_lever_jobs(
                lever_companies, db, deduplicator,
                title_include_patterns=title_include_patterns,
                job_filter=job_filter,
            )
            total_discovered += d
            total_new += n
            total_duplicate += d - n
            sources_success += s
            sources_failed += f

        # Ashby companies (free public API).
        ashby_companies = companies_config.get("ashby_companies", {})
        if ashby_companies:
            logger.info(
                "Fetching from {} Ashby companies...", len(ashby_companies),
            )
            d, n, s, f = await fetch_ashby_jobs(
                ashby_companies, db, deduplicator,
                title_include_patterns=title_include_patterns,
                job_filter=job_filter,
            )
            total_discovered += d
            total_new += n
            total_duplicate += d - n
            sources_success += s
            sources_failed += f

        # GitHub internship repos (SimplifyJobs format).
        github_repos = companies_config.get("github_repos", [])
        if github_repos:
            enabled_repos = [r for r in github_repos if r.get("enabled", True)]
            if enabled_repos:
                logger.info(
                    "Fetching from {} GitHub repos...", len(enabled_repos),
                )
                d, n, s, f = await fetch_github_repo_jobs(
                    enabled_repos, db, deduplicator,
                    title_include_patterns=title_include_patterns,
                    job_filter=job_filter,
                )
                total_discovered += d
                total_new += n
                total_duplicate += d - n
                sources_success += s
                sources_failed += f

        # LinkedIn direct scraping (guest API).
        linkedin_config = companies_config.get("linkedin", {})
        if linkedin_config.get("enabled", False):
            logger.info("Fetching from LinkedIn...")
            d, n, s, f = await fetch_linkedin_jobs(
                linkedin_config, db, deduplicator,
                default_search_terms=default_search_terms,
                title_include_patterns=title_include_patterns,
                job_filter=job_filter,
            )
            total_discovered += d
            total_new += n
            total_duplicate += d - n
            sources_success += s
            sources_failed += f

        # Career page watchers (generic HTML scraping).
        watched_pages = companies_config.get("watched_pages", [])
        if watched_pages:
            logger.info(
                "Watching {} career pages...", len(watched_pages),
            )
            d, n, s, f = await fetch_career_page_jobs(
                watched_pages, db, deduplicator,
                job_filter=job_filter,
            )
            total_discovered += d
            total_new += n
            total_duplicate += d - n
            sources_success += s
            sources_failed += f

        # Daily stats are updated after all crawls finish so the row reflects
        # the full cycle rather than one source family at a time.
        today = datetime.now().strftime("%Y-%m-%d")
        await db.update_daily_stats(
            date=today,
            jobs_discovered=total_discovered,
            jobs_new=total_new,
            jobs_duplicate=total_duplicate,
            sources_crawled=sources_success,
            sources_failed=sources_failed,
        )

        # The final summary keeps the most important cycle metrics together in
        # one place for later operational review.
        cycle_duration = time.time() - cycle_start
        log_cycle_summary(
            total_discovered,
            total_new,
            total_duplicate,
            sources_success,
            sources_failed,
            cycle_duration,
        )

        # Logging the steady-state DB totals helps distinguish "quiet day" runs
        # from runs that failed before inserts happened.
        total_jobs = await db.get_job_count()
        jobs_today = await db.get_jobs_today()
        logger.info(f"Database: {total_jobs} total jobs, {jobs_today} added today")


def main() -> None:
    """Load runtime configuration and execute the discovery cycle.

    Purpose:
        Provide the synchronous entrypoint used by `python main.py`, including
        environment loading, logger setup, and top-level error handling.
    Args:
        None.
    Output:
        Returns `None` after running the async discovery workflow or re-raising
        unexpected failures after logging them.
    """
    # Environment variables control database paths, logging settings, and
    # external service credentials, so they are loaded before any setup work.
    load_dotenv()

    # Logging is initialized once here so every downstream module writes to the
    # same console and file sinks.
    log_file = os.getenv("LOG_FILE", "logs/job_monitor.log")
    log_level = os.getenv("LOG_LEVEL", "INFO")
    setup_logger(log_file=log_file, level=log_level)

    # Top-level exception handling keeps interactive runs readable while still
    # preserving tracebacks for unexpected failures.
    try:
        asyncio.run(run_job_discovery())
    except KeyboardInterrupt:
        logger.info("Job discovery interrupted by user")
    except Exception as e:
        logger.exception(f"Job discovery failed: {e}")
        raise


if __name__ == "__main__":
    main()


__all__ = [
    "asyncio",
    "main",
    "run_job_discovery",
]
