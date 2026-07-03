"""Filter-and-insert pipeline shared by every per-fetcher orchestrator entry.

Each fetcher family runs jobs through the same hard/soft filter check and
DB-write sequence, so consolidating the logic here keeps the per-fetcher
modules small and the filter/insert behavior consistent.
"""

from __future__ import annotations

import re
import sys
from typing import Any, Callable, Coroutine

from loguru import logger

from src.database.db_manager import DatabaseManager
from src.filters.job_filter import FilterAction, JobFilter
from src.models.job_posting import JobPosting


def filter_by_title_patterns(
    jobs: list[JobPosting],
    include_patterns: list[str],
    exclude_patterns: list[str] | None = None,
) -> list[JobPosting]:
    """Keep only jobs whose title matches at least one include pattern
    and none of the exclude patterns."""
    if not include_patterns:
        return jobs
    compiled_inc = [re.compile(p, re.IGNORECASE) for p in include_patterns]
    compiled_exc = [re.compile(p, re.IGNORECASE) for p in (exclude_patterns or [])]
    return [
        j for j in jobs
        if any(rx.search(j.title) for rx in compiled_inc)
        and not any(rx.search(j.title) for rx in compiled_exc)
    ]


# Non-CS industries whose roles are tagged "Business" in raw_data at insert.
# The digest classifies every job by title at render time
# (src/digest/categorize.py); this stamp only serves as the fallback label
# for vague titles no classifier rule matches, keeping recall for
# finance / real-estate / logistics postings with unusual names.
_BUSINESS_INDUSTRIES: frozenset[str] = frozenset(
    {"finance_banking", "finance", "real_estate", "logistics"}
)


def resolve_digest_category(config: dict[str, Any] | None) -> str | None:
    """Return the digest category a source's jobs should be tagged with.

    Purpose:
        Decide how a company/board's postings are routed in the email digest.
        Prefers an explicit ``digest_category`` config key; otherwise derives
        ``"Business"`` from a non-CS ``industry`` tag.
    Args:
        config: The per-source config mapping (a ``companies.yaml`` company
            entry or a ``job_boards`` entry), or ``None``.
    Output:
        The category string to stamp, or ``None`` for CS/tech sources, which
        stay uncategorized and reach every subscriber.
    """
    if not isinstance(config, dict):
        return None
    explicit = config.get("digest_category")
    if isinstance(explicit, str) and explicit:
        return explicit
    industry = config.get("industry")
    if isinstance(industry, str) and industry in _BUSINESS_INDUSTRIES:
        return "Business"
    return None


def stamp_digest_category(jobs: list[JobPosting], category: str | None) -> None:
    """Tag each job's ``raw_data['category']`` with ``category``, in place.

    Purpose:
        Persist the digest routing category on every posting from a source so
        the digest sender can filter by subscriber field preferences.
    Args:
        jobs: Postings from a single source, mutated in place.
        category: The category to stamp, or ``None`` to leave jobs untagged.
    Output:
        None. Jobs already carrying a category are left untouched.
    """
    if not category:
        return
    for job in jobs:
        job.raw_data.setdefault("category", category)


# Type alias for the insert-with-filters callable; mypy strict needs a
# concrete shape so tests that monkeypatch ``main._insert_with_filters``
# remain checkable when their stand-in returns a 2-tuple.
_InsertCallable = Callable[
    ...,
    Coroutine[Any, Any, tuple[int, ...]],
]


async def insert_with_filters(
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


def resolve_insert_with_filters() -> _InsertCallable:
    """Return the active insert-with-filters implementation.

    Purpose:
        Existing tests monkey-patch ``main._insert_with_filters`` to substitute
        a stub that records call counts.  Because the per-fetcher modules call
        the helper indirectly, they need a late-bound lookup that honors the
        patched attribute on the ``main`` module while falling back to the real
        implementation in this module.
    Args:
        None.
    Output:
        Returns the callable that should be awaited to insert jobs.
    """

    main_module = sys.modules.get("main")
    if main_module is not None:
        candidate = getattr(main_module, "_insert_with_filters", None)
        if candidate is not None:
            # ``getattr`` strips the static type back to ``Any``; a single
            # cast here keeps the rest of the orchestrator strictly typed.
            from typing import cast
            return cast(_InsertCallable, candidate)
    return insert_with_filters
