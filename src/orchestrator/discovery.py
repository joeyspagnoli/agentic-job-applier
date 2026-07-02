"""Top-level discovery cycle coordinator.

``run_job_discovery`` loads configuration, opens the database, fans out
across every configured fetcher family concurrently, and writes the
cycle-level rollup row to ``daily_stats``.  Per-fetcher logic lives in
``src.orchestrator.crawl_runners``; this module owns coordination only.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, cast

from loguru import logger

from src.database.db_manager import DatabaseManager
from src.utils.notification_dispatcher import NotificationDispatcher
from src.utils.notifications import is_ntfy_enabled, send_ntfy_notification
from src.filters.job_filter import JobFilter
from src.orchestrator._family_tasks import build_family_tasks
from src.orchestrator.config_loader import (
    build_loose_filter,
    load_optional_yaml,
    load_yaml,
    normalize_string_list,
    resolve_job_board_default_search_terms,
    resolve_workday_search_text,
)
from src.orchestrator.domains import (
    apply_domain_filter_to_config,
    resolve_user_domains,
)
from src.utils.deduplicator import Deduplicator
from src.utils.logger import log_cycle_summary
from src.utils.paths import resolve_database_path


def _section_dict(
    companies_config: dict[str, Any], section: str
) -> dict[str, Any]:
    """Return a watchlist section as a dict, treating missing/non-dict as empty.

    Purpose:
        Safely measure section sizes for the domain-filter log line without
        leaking ``object`` typing through ``mapping.get(...)`` into ``len()``.
    Args:
        companies_config: Parsed `companies.yaml` mapping.
        section: Top-level key (e.g. ``"workday_companies"``).
    Output:
        Returns the section mapping or an empty dict.
    """

    raw = companies_config.get(section)
    return raw if isinstance(raw, dict) else {}


def _resolve_main_attr(name: str, default: Any) -> Any:
    """Return ``main.<name>`` when ``main`` exposes it, otherwise ``default``.

    Purpose:
        Tests monkey-patch helpers like ``main.load_yaml`` and
        ``main.resolve_database_path`` and then call ``run_job_discovery``;
        looking the attributes up via the ``main`` module at call time keeps
        those patches effective without leaking the patch surface into the
        production code path.
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


def _resolve_load_yaml() -> Callable[[str | Path], dict[str, Any]]:
    """Return the active YAML loader, honoring monkeypatched stubs."""

    return cast(
        Callable[[str | Path], dict[str, Any]],
        _resolve_main_attr("load_yaml", load_yaml),
    )


def _resolve_database_path_resolver() -> Callable[[], Path | str]:
    """Return the active database-path resolver, honoring monkeypatches."""

    return cast(
        Callable[[], Path | str],
        _resolve_main_attr("resolve_database_path", resolve_database_path),
    )


async def _send_watched_job_notifications(
    db: DatabaseManager, cycle_start: float
) -> None:
    """Send ntfy notifications for new jobs matching the watch list.

    Purpose:
        After a discovery cycle, check for newly added jobs from watched
        companies and send a single consolidated notification with titles
        and URLs for quick access.
    Args:
        db: Active database manager.
        cycle_start: Epoch timestamp of when this cycle began.
    Output:
        Returns None.  Notification failures are logged but never raised.
    """
    config_path = Path("config/notifications.yaml")
    if not config_path.exists():
        return

    import yaml

    with open(config_path) as f:
        notify_config = yaml.safe_load(f) or {}

    watch_companies = notify_config.get("watch_companies", [])
    if not watch_companies:
        return

    exclude_patterns = notify_config.get("exclude_title_patterns", [])
    compiled_excludes = [re.compile(p) for p in exclude_patterns]

    cycle_iso = datetime.fromtimestamp(cycle_start, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    assert db.conn is not None
    cursor = await db.conn.execute(
        "SELECT company, title, source_url FROM job_postings "
        "WHERE fetched_at >= ? "
        "  AND id = (SELECT MIN(p2.id) FROM job_postings p2 "
        "            WHERE LOWER(p2.company) = LOWER(job_postings.company) "
        "              AND LOWER(p2.title) = LOWER(job_postings.title)) "
        "ORDER BY company, title",
        (cycle_iso,),
    )
    rows = await cursor.fetchall()

    seen_keys: set[tuple[str, str]] = set()
    unique: list[tuple[str, str, str]] = []
    for company, title, url in rows:
        company_lower = (company or "").lower()
        if not any(w.lower() in company_lower for w in watch_companies):
            continue
        if any(pat.search(title or "") for pat in compiled_excludes):
            continue
        key = (" ".join(company_lower.split()), " ".join((title or "").lower().split()))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique.append((company, title, url or ""))

    if not unique:
        return

    lines = []
    for company, title, url in unique:
        line = f"{company}: {title}"
        if url:
            line += f"\n  {url}"
        lines.append(line)

    count = len(unique)
    batches: list[list[str]] = [[]]
    batch_size = 0
    for line in lines:
        entry_size = len(line.encode("utf-8")) + 1
        if batch_size + entry_size > 3700 and batches[-1]:
            batches.append([])
            batch_size = 0
        batches[-1].append(line)
        batch_size += entry_size

    for i, batch in enumerate(batches):
        part = f" ({i + 1}/{len(batches)})" if len(batches) > 1 else ""
        await send_ntfy_notification(
            title=f"{count} new job{'s' if count != 1 else ''} at watched companies{part}",
            message="\n".join(batch),
            tags=("briefcase", "star"),
        )
    logger.info("Sent {} ntfy notification(s) for {} watched-company jobs", len(batches), count)


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
    # versioned alongside code updates. ``main.load_yaml`` and
    # ``main.resolve_database_path`` may be monkeypatched in tests, so they
    # are looked up via the ``main`` module rather than imported eagerly.
    yaml_loader = _resolve_load_yaml()
    db_path_resolver = _resolve_database_path_resolver()

    config_dir = Path(__file__).resolve().parents[2] / "config"
    companies_config = yaml_loader(config_dir / "companies.yaml")
    search_criteria_config = load_optional_yaml(config_dir / "search_criteria.yaml")
    candidate_profile_config = load_optional_yaml(
        config_dir / "candidate_profile.yaml",
    )
    filters_config = load_optional_yaml(config_dir / "filters.yaml")

    # Scope the company watchlist to the user's chosen domains. Untagged
    # companies and search-term-driven sections (LinkedIn, JobSpy, GitHub
    # repos, watched_pages) are left intact so the filter never silently
    # hides results that have no industry classification yet.
    user_domains = resolve_user_domains(candidate_profile_config)
    if user_domains:
        before_counts = {
            section: len(_section_dict(companies_config, section))
            for section in (
                "greenhouse_companies",
                "workday_companies",
                "icims_companies",
                "taleo_companies",
                "lever_companies",
                "ashby_companies",
            )
        }
        companies_config = apply_domain_filter_to_config(
            companies_config, user_domains
        )
        after_counts = {
            section: len(_section_dict(companies_config, section))
            for section in before_counts
        }
        logger.info(
            "Domain filter active for {}: watchlist {} -> {}",
            sorted(user_domains),
            sum(before_counts.values()),
            sum(after_counts.values()),
        )
    default_search_terms = resolve_job_board_default_search_terms(
        search_criteria_config=search_criteria_config,
        candidate_profile_config=candidate_profile_config,
    )
    title_include_patterns = normalize_string_list(
        search_criteria_config.get("include_title_patterns"),
        field_name="include_title_patterns",
        source_name="search_criteria",
    )

    # Pre-gate filters reduce gate agent invocations by auto-rejecting or
    # auto-qualifying jobs that are obviously outside the user's criteria.
    job_filter: JobFilter | None = None
    loose_job_filter: JobFilter | None = None
    if filters_config:
        job_filter = JobFilter(filters_config)
        loose_job_filter = build_loose_filter(filters_config)
        logger.info("Pre-gate filters loaded from config/filters.yaml")

    # Workday CXS anonymous queries return only ~40 default-sorted results per
    # tenant. Passing a single high-value entry-level token as ``searchText``
    # widens that to hundreds of relevant listings without changing API quotas.
    workday_search_text = resolve_workday_search_text(candidate_profile_config)
    if workday_search_text:
        logger.info(
            "Workday searchText derived from candidate target_roles: {!r}",
            workday_search_text,
        )

    # The database layer owns schema creation and lightweight migrations so each
    # run can safely bootstrap a fresh local environment.
    db_path = str(db_path_resolver())
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
        # so users can enable integrations incrementally. Families run
        # concurrently via ``asyncio.gather`` so a slow tenant in one family
        # (e.g., a hung Workday CXS endpoint) cannot stall fast families
        # like Greenhouse or GitHub-repo internship lists.
        family_tasks = build_family_tasks(
            companies_config=companies_config,
            db=db,
            deduplicator=deduplicator,
            title_include_patterns=title_include_patterns,
            job_filter=job_filter,
            loose_job_filter=loose_job_filter,
            workday_search_text=workday_search_text,
            default_search_terms=default_search_terms,
        )

        # ``return_exceptions=True`` ensures one family raising does not
        # cancel the others — the cycle still publishes whatever jobs the
        # remaining families produced.
        if family_tasks:
            family_names = [name for name, _ in family_tasks]
            logger.info(
                "Running {} fetcher families concurrently: {}",
                len(family_tasks),
                ", ".join(family_names),
            )
            family_results = await asyncio.gather(
                *(coro for _, coro in family_tasks),
                return_exceptions=True,
            )
            for (family_name, _), result in zip(family_tasks, family_results):
                if isinstance(result, BaseException):
                    logger.error(
                        "Fetcher family {} raised {}: {}",
                        family_name,
                        type(result).__name__,
                        result,
                    )
                    sources_failed += 1
                    continue
                discovered, new_count, succeeded, failed = result
                total_discovered += discovered
                total_new += new_count
                total_duplicate += discovered - new_count
                sources_success += succeeded
                sources_failed += failed

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

        # TODO: Replace direct ntfy calls with NotificationDispatcher.from_yaml("config/notifications.yaml")
        if total_new > 0 and is_ntfy_enabled():
            await _send_watched_job_notifications(db, cycle_start)

        cleanup = await db.cleanup_old_records()
        if cleanup["crawl_deleted"] or cleanup["jobs_deleted"]:
            logger.info("TTL cleanup: {}", cleanup)
