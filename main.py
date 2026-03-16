"""Run the main job discovery workflow for the repository.

This module loads configuration, coordinates each fetcher, filters duplicates,
stores new postings, and records crawl-level metrics for later inspection.
"""

import asyncio
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from loguru import logger

from src.database.db_manager import DatabaseManager
from src.fetchers.apify_fetcher import ApifyWorkdayFetcher
from src.fetchers.greenhouse_fetcher import GreenhouseFetcher
from src.fetchers.jobspy_fetcher import JobSpyFetcher
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


def _filter_by_title_patterns(jobs: list, include_patterns: list[str]) -> list:
    """Keep only jobs whose title matches at least one include pattern."""
    if not include_patterns:
        return jobs
    compiled = [re.compile(p, re.IGNORECASE) for p in include_patterns]
    return [j for j in jobs if any(rx.search(j.title) for rx in compiled)]


async def fetch_greenhouse_jobs(
    companies: dict,
    db: DatabaseManager,
    deduplicator: Deduplicator,
    title_include_patterns: list[str] | None = None,
) -> tuple[int, int, int, int]:
    """Fetch jobs for every configured Greenhouse company.

    Purpose:
        Iterate the Greenhouse section of the config, run each crawl, and
        aggregate per-company results into cycle-level counters.
    Args:
        companies: Mapping of company names to their Greenhouse configuration.
        db: Connected database manager used to track crawl metadata and inserts.
        deduplicator: Helper that filters out jobs already present in storage.
    Output:
        Returns a tuple of `(total_discovered, total_new, sources_success,
        sources_failed)` for the Greenhouse portion of the cycle.
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
        crawl_jobs_new = 0
        start_time = time.time()

        try:
            crawl_id = await db.start_crawl("greenhouse", company_name)

            async with GreenhouseFetcher(company_name, greenhouse_id) as fetcher:
                jobs = await fetcher.fetch_jobs()
                if title_include_patterns:
                    jobs = _filter_by_title_patterns(jobs, title_include_patterns)
                crawl_jobs_found = len(jobs)
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                for job in new_jobs:
                    was_inserted = await db.insert_job(job.to_db_dict())
                    if was_inserted:
                        crawl_jobs_new += 1

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
                    jobs_new=crawl_jobs_new,
                    error=str(exc),
                )
            sources_failed += 1
        finally:
            total_discovered += crawl_jobs_found
            total_new += crawl_jobs_new

    return total_discovered, total_new, sources_success, sources_failed


async def fetch_workday_jobs(
    companies: dict,
    db: DatabaseManager,
    deduplicator: Deduplicator,
    title_include_patterns: list[str] | None = None,
) -> tuple[int, int, int, int]:
    """Fetch jobs for every configured Workday company via Apify.

    Purpose:
        Run the Workday portion of the discovery cycle while handling the
        environment requirements of the Apify-backed scraper.
    Args:
        companies: Mapping of company names to their Workday configuration.
        db: Connected database manager used to track crawl metadata and inserts.
        deduplicator: Helper that filters out jobs already present in storage.
    Output:
        Returns a tuple of `(total_discovered, total_new, sources_success,
        sources_failed)` for the Workday portion of the cycle.
    """
    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    # Workday crawling depends on Apify credentials, so the orchestrator skips
    # this whole section when the environment is not ready.
    if not os.getenv("APIFY_API_TOKEN"):
        logger.warning("APIFY_API_TOKEN not set, skipping Workday sources")
        return 0, 0, 0, 0

    for company_name, config in companies.items():
        workday_url = config.get("workday_url")
        if not workday_url:
            logger.warning(f"No workday_url for {company_name}, skipping")
            continue

        crawl_id: int | None = None
        crawl_jobs_found = 0
        crawl_jobs_new = 0
        start_time = time.time()

        try:
            crawl_id = await db.start_crawl("apify_workday", company_name)

            async with ApifyWorkdayFetcher(company_name, workday_url) as fetcher:
                jobs = await fetcher.fetch_jobs()
                if title_include_patterns:
                    jobs = _filter_by_title_patterns(jobs, title_include_patterns)
                crawl_jobs_found = len(jobs)
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                for job in new_jobs:
                    was_inserted = await db.insert_job(job.to_db_dict())
                    if was_inserted:
                        crawl_jobs_new += 1

                duration = time.time() - start_time
                log_crawl_summary(
                    "apify_workday",
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
                    jobs_new=crawl_jobs_new,
                    error=str(exc),
                )
            sources_failed += 1
        finally:
            total_discovered += crawl_jobs_found
            total_new += crawl_jobs_new

    return total_discovered, total_new, sources_success, sources_failed


async def fetch_jobspy_jobs(
    job_boards: dict,
    db: DatabaseManager,
    deduplicator: Deduplicator,
    default_search_terms: list[str] | None = None,
    title_include_patterns: list[str] | None = None,
) -> tuple[int, int, int, int]:
    """Fetch jobs from enabled job boards through JobSpy.

    Purpose:
        Expand search-term and location combinations for each configured board,
        run the scrape, and aggregate results back into cycle metrics.
    Args:
        job_boards: Mapping of job-board settings from `config/companies.yaml`.
        db: Connected database manager used to track crawl metadata and inserts.
        deduplicator: Helper that filters out jobs already present in storage.
        default_search_terms: Optional fallback search terms used when a board
            config omits explicit `search_terms`.
    Output:
        Returns a tuple of `(total_discovered, total_new, sources_success,
        sources_failed)` for all JobSpy-backed board searches.
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
            search_terms = ["software engineering internship"]
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
                crawl_jobs_new = 0
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

                    # Keeping the persistence loop local makes the success and
                    # failure accounting line up with the exact crawl variant.
                    for job in new_jobs:
                        was_inserted = await db.insert_job(job.to_db_dict())
                        if was_inserted:
                            crawl_jobs_new += 1

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
                            jobs_new=crawl_jobs_new,
                            error=str(exc),
                        )
                    sources_failed += 1
                finally:
                    total_discovered += crawl_jobs_found
                    total_new += crawl_jobs_new

                # A short delay reduces the chance of hammering job boards with
                # back-to-back requests from many search variants.
                await asyncio.sleep(2)

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
    default_search_terms = resolve_job_board_default_search_terms(
        search_criteria_config=search_criteria_config,
        candidate_profile_config=candidate_profile_config,
    )
    title_include_patterns = _normalize_string_list(
        search_criteria_config.get("include_title_patterns"),
        field_name="include_title_patterns",
        source_name="search_criteria",
    )

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
