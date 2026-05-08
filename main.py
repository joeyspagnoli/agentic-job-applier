"""Synchronous entry point for the job-discovery orchestration cycle.

Loads environment + logger configuration and hands off to
``src.orchestrator.discovery.run_job_discovery``.  Per-fetcher logic lives
under ``src.orchestrator.fetchers``; this module re-exports the helpers and
fetcher classes that tests and external scripts already import from
``main`` so the public surface stays unchanged.
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from loguru import logger

# Fetcher classes are imported here so tests that patch ``main.<Fetcher>``
# (e.g. ``monkeypatch.setattr(main, "GreenhouseFetcher", FakeFetcher)``)
# can swap the implementation that per-fetcher modules pick up via the
# late-bound ``resolve_fetcher_attr`` helper.
from src.fetchers.ashby_fetcher import AshbyFetcher
from src.fetchers.career_page_watcher import CareerPageWatcher
from src.fetchers.github_repo_fetcher import GitHubRepoFetcher
from src.fetchers.greenhouse_fetcher import GreenhouseFetcher
from src.fetchers.icims_fetcher import ICIMSFetcher
from src.fetchers.jobspy_fetcher import JobSpyFetcher
from src.fetchers.lever_fetcher import LeverFetcher
from src.fetchers.linkedin_fetcher import LinkedInFetcher
from src.fetchers.taleo_fetcher import TaleoFetcher
from src.fetchers.workday_fetcher import WorkdayFetcher
from src.orchestrator.config_loader import (
    load_optional_yaml,
    load_yaml,
    resolve_job_board_default_search_terms,
)
from src.orchestrator.discovery import run_job_discovery
from src.orchestrator.fetchers.ashby import fetch_ashby_jobs
from src.orchestrator.fetchers.career_pages import fetch_career_page_jobs
from src.orchestrator.fetchers.github_repos import fetch_github_repo_jobs
from src.orchestrator.fetchers.greenhouse import fetch_greenhouse_jobs
from src.orchestrator.fetchers.icims import fetch_icims_jobs
from src.orchestrator.fetchers.jobspy import fetch_jobspy_jobs
from src.orchestrator.fetchers.lever import fetch_lever_jobs
from src.orchestrator.fetchers.linkedin import fetch_linkedin_jobs
from src.orchestrator.fetchers.taleo import fetch_taleo_jobs
from src.orchestrator.fetchers.workday import fetch_workday_jobs
from src.orchestrator.insert_pipeline import insert_with_filters as _insert_with_filters
from src.utils.logger import log_crawl_summary, setup_logger
from src.utils.paths import resolve_database_path


def main() -> None:
    """Load runtime configuration and execute the discovery cycle.

    Purpose:
        Provide the synchronous entrypoint used by ``python main.py`` and
        ``python -m main``, including environment loading, logger setup, and
        top-level error handling.
    Args:
        None.
    Output:
        Returns ``None`` after running the async discovery workflow or
        re-raising unexpected failures after logging them.
    """

    # Environment variables control database paths, logging settings, and
    # external service credentials, so they are loaded before any setup work.
    load_dotenv()

    # Logging is initialized once here so every downstream module writes to
    # the same console and file sinks.
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
    "AshbyFetcher",
    "CareerPageWatcher",
    "GitHubRepoFetcher",
    "GreenhouseFetcher",
    "ICIMSFetcher",
    "JobSpyFetcher",
    "LeverFetcher",
    "LinkedInFetcher",
    "TaleoFetcher",
    "WorkdayFetcher",
    "_insert_with_filters",
    "asyncio",
    "fetch_ashby_jobs",
    "fetch_career_page_jobs",
    "fetch_github_repo_jobs",
    "fetch_greenhouse_jobs",
    "fetch_icims_jobs",
    "fetch_jobspy_jobs",
    "fetch_lever_jobs",
    "fetch_linkedin_jobs",
    "fetch_taleo_jobs",
    "fetch_workday_jobs",
    "load_optional_yaml",
    "load_yaml",
    "log_crawl_summary",
    "main",
    "resolve_database_path",
    "resolve_job_board_default_search_terms",
    "run_job_discovery",
]
