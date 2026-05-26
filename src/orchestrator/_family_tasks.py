"""Per-cycle fetcher-family task assembly used by ``run_job_discovery``.

Lifting the family-by-family task construction out of ``discovery.py`` keeps
the cycle coordinator small and readable, and makes it straightforward to
add or reorder fetcher families without touching loop control flow.
"""

from __future__ import annotations

import sys
from typing import Any, Awaitable, Callable, cast

from loguru import logger

from src.database.db_manager import DatabaseManager
from src.filters.job_filter import JobFilter
from src.orchestrator.crawl_runners.adzuna import fetch_adzuna_jobs
from src.orchestrator.crawl_runners.ashby import fetch_ashby_jobs
from src.orchestrator.crawl_runners.career_pages import fetch_career_page_jobs
from src.orchestrator.crawl_runners.github_repos import fetch_github_repo_jobs
from src.orchestrator.crawl_runners.greenhouse import fetch_greenhouse_jobs
from src.orchestrator.crawl_runners.icims import fetch_icims_jobs
from src.orchestrator.crawl_runners.jobspy import fetch_jobspy_jobs
from src.orchestrator.crawl_runners.lever import fetch_lever_jobs
from src.orchestrator.crawl_runners.linkedin import fetch_linkedin_jobs
from src.orchestrator.crawl_runners.taleo import fetch_taleo_jobs
from src.orchestrator.crawl_runners.workday import fetch_workday_jobs
from src.utils.deduplicator import Deduplicator

# Type alias for any fetcher-family coroutine awaited in ``run_job_discovery``.
_FamilyResult = tuple[int, int, int, int]
_FamilyCoroutine = Awaitable[_FamilyResult]
_FetchFn = Callable[..., _FamilyCoroutine]


def _resolve_main_attr(name: str, default: Any) -> Any:
    """Return ``main.<name>`` when ``main`` exposes it, otherwise ``default``.

    Purpose:
        Tests monkey-patch helpers like ``main.fetch_greenhouse_jobs`` and
        then call ``run_job_discovery``; looking the attributes up via the
        ``main`` module at call time keeps those patches effective without
        leaking the patch surface into the production code path.
    Args:
        name: Attribute name to look up on the ``main`` module.
        default: Value used when ``main`` is not yet imported or does not
            expose the attribute.
    Output:
        Returns the resolved attribute or the supplied default.
    """

    main_module = sys.modules.get("main")
    if main_module is None:
        return default
    return getattr(main_module, name, default)


def _resolve_fetch_fn(name: str, default: _FetchFn) -> _FetchFn:
    """Resolve a fetch coroutine factory through ``main`` for monkeypatching."""

    return cast(_FetchFn, _resolve_main_attr(name, default))


def build_family_tasks(
    *,
    companies_config: dict[str, Any],
    db: DatabaseManager,
    deduplicator: Deduplicator,
    title_include_patterns: list[str],
    job_filter: JobFilter | None,
    loose_job_filter: JobFilter | None,
    workday_search_text: str,
    default_search_terms: list[str],
) -> list[tuple[str, _FamilyCoroutine]]:
    """Assemble the list of (family_name, coroutine) pairs to run concurrently.

    Purpose:
        Keep ``run_job_discovery`` readable by lifting the family-by-family
        construction into a single helper. The helper resolves each fetcher
        through ``main`` so test patches replacing ``main.fetch_*_jobs`` are
        honored without losing strict typing.
    Args:
        companies_config: Parsed ``companies.yaml`` mapping.
        db: Connected database manager shared across families.
        deduplicator: Shared deduplicator for the cycle.
        title_include_patterns: Optional regex include list for titles.
        job_filter: Pre-gate filter instance, if configured.
        loose_job_filter: Relaxed-title filter for EE-friendly Workday tenants.
        workday_search_text: Free-text token forwarded to Workday CXS.
        default_search_terms: Default search terms derived from the profile.
    Output:
        Returns the list of family-task pairs ready for ``asyncio.gather``.
    """

    family_tasks: list[tuple[str, _FamilyCoroutine]] = []

    greenhouse_companies = companies_config.get("greenhouse_companies", {})
    if greenhouse_companies:
        logger.info(
            f"Fetching from {len(greenhouse_companies)} Greenhouse companies..."
        )
        greenhouse_fn = _resolve_fetch_fn(
            "fetch_greenhouse_jobs", fetch_greenhouse_jobs,
        )
        family_tasks.append(("greenhouse", greenhouse_fn(
            greenhouse_companies, db, deduplicator,
            title_include_patterns=title_include_patterns,
            job_filter=job_filter,
        )))

    workday_companies = companies_config.get("workday_companies", {})
    if workday_companies:
        logger.info(f"Fetching from {len(workday_companies)} Workday companies...")
        workday_fn = _resolve_fetch_fn("fetch_workday_jobs", fetch_workday_jobs)
        family_tasks.append(("workday", workday_fn(
            workday_companies, db, deduplicator,
            title_include_patterns=title_include_patterns,
            job_filter=job_filter,
            loose_job_filter=loose_job_filter,
            search_text=workday_search_text,
        )))

    taleo_companies = companies_config.get("taleo_companies", {})
    if taleo_companies:
        logger.info(
            "Fetching from {} Taleo companies...", len(taleo_companies),
        )
        taleo_fn = _resolve_fetch_fn("fetch_taleo_jobs", fetch_taleo_jobs)
        family_tasks.append(("taleo", taleo_fn(
            taleo_companies, db, deduplicator,
            title_include_patterns=title_include_patterns,
            job_filter=job_filter,
        )))

    icims_companies = companies_config.get("icims_companies", {})
    if icims_companies:
        logger.info(f"Fetching from {len(icims_companies)} iCIMS companies...")
        icims_fn = _resolve_fetch_fn("fetch_icims_jobs", fetch_icims_jobs)
        family_tasks.append(("icims", icims_fn(
            icims_companies, db, deduplicator,
            title_include_patterns=title_include_patterns,
            job_filter=job_filter,
        )))

    adzuna_config = companies_config.get("adzuna", {})
    if isinstance(adzuna_config, dict) and adzuna_config.get("enabled", False):
        logger.info("Fetching from Adzuna...")
        adzuna_fn = _resolve_fetch_fn("fetch_adzuna_jobs", fetch_adzuna_jobs)
        family_tasks.append(("adzuna", adzuna_fn(
            adzuna_config, db, deduplicator,
            default_search_terms=default_search_terms,
            title_include_patterns=title_include_patterns,
            job_filter=job_filter,
        )))

    job_boards = companies_config.get("job_boards", {})
    if job_boards:
        enabled_boards = [b for b, c in job_boards.items() if c.get("enabled")]
        logger.info(f"Fetching from {len(enabled_boards)} job boards...")
        jobspy_fn = _resolve_fetch_fn("fetch_jobspy_jobs", fetch_jobspy_jobs)
        family_tasks.append(("jobspy", jobspy_fn(
            job_boards, db, deduplicator,
            default_search_terms=default_search_terms,
            title_include_patterns=title_include_patterns,
            job_filter=job_filter,
        )))

    lever_companies = companies_config.get("lever_companies", {})
    if lever_companies:
        logger.info(
            "Fetching from {} Lever companies...", len(lever_companies),
        )
        lever_fn = _resolve_fetch_fn("fetch_lever_jobs", fetch_lever_jobs)
        family_tasks.append(("lever", lever_fn(
            lever_companies, db, deduplicator,
            title_include_patterns=title_include_patterns,
            job_filter=job_filter,
        )))

    ashby_companies = companies_config.get("ashby_companies", {})
    if ashby_companies:
        logger.info(
            "Fetching from {} Ashby companies...", len(ashby_companies),
        )
        ashby_fn = _resolve_fetch_fn("fetch_ashby_jobs", fetch_ashby_jobs)
        family_tasks.append(("ashby", ashby_fn(
            ashby_companies, db, deduplicator,
            title_include_patterns=title_include_patterns,
            job_filter=job_filter,
        )))

    github_repos = companies_config.get("github_repos", [])
    if github_repos:
        enabled_repos = [r for r in github_repos if r.get("enabled", True)]
        if enabled_repos:
            logger.info(
                "Fetching from {} GitHub repos...", len(enabled_repos),
            )
            gh_fn = _resolve_fetch_fn(
                "fetch_github_repo_jobs", fetch_github_repo_jobs,
            )
            family_tasks.append(("github_repos", gh_fn(
                enabled_repos, db, deduplicator,
                title_include_patterns=title_include_patterns,
                job_filter=job_filter,
            )))

    linkedin_config = companies_config.get("linkedin", {})
    if linkedin_config.get("enabled", False):
        logger.info("Fetching from LinkedIn...")
        linkedin_fn = _resolve_fetch_fn("fetch_linkedin_jobs", fetch_linkedin_jobs)
        family_tasks.append(("linkedin", linkedin_fn(
            linkedin_config, db, deduplicator,
            default_search_terms=default_search_terms,
            title_include_patterns=title_include_patterns,
            job_filter=job_filter,
        )))

    watched_pages = companies_config.get("watched_pages", [])
    if watched_pages:
        logger.info(
            "Watching {} career pages...", len(watched_pages),
        )
        career_fn = _resolve_fetch_fn(
            "fetch_career_page_jobs", fetch_career_page_jobs,
        )
        family_tasks.append(("watched_pages", career_fn(
            watched_pages, db, deduplicator,
            job_filter=job_filter,
        )))

    return family_tasks
