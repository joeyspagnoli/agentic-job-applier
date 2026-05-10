"""Source-label and source-filter helpers shared across job endpoints.

Discovery writes raw source strings such as `workday_kbr`,
`linkedin_civil_engineering_intern`, `icims_skanska_usa`, or
`jobspy_indeed_civil_engineer_student`. The dashboard surfaces a
compact, stable enum (`WORKDAY`, `LINKEDIN`, ...) so users can filter by
fetcher family without having to know per-tenant slugs. These helpers
own the mapping in both directions: raw -> label for display, and
label -> SQL clause for `/api/jobs?source=...` filtering. Any new
fetcher family should land in both functions and gain a regression
test in `tests/test_api_jobs_source_filter.py`.
"""

from __future__ import annotations

# Canonical user-facing source labels. Keep this tuple in lockstep with
# `dashboard/src/pages/JobsPage.tsx::SOURCE_OPTIONS` so the dropdown,
# the API filter accept list, and the row Source column all use the
# same string set.
SOURCE_LABEL_GREENHOUSE = "GREENHOUSE"
SOURCE_LABEL_WORKDAY = "WORKDAY"
SOURCE_LABEL_JOBSPY = "JOBSPY"
SOURCE_LABEL_LINKEDIN = "LINKEDIN"
SOURCE_LABEL_ICIMS = "ICIMS"
SOURCE_LABEL_TALEO = "TALEO"
SOURCE_LABEL_LEVER = "LEVER"
SOURCE_LABEL_ASHBY = "ASHBY"
SOURCE_LABEL_ADZUNA = "ADZUNA"
SOURCE_LABEL_GITHUB_REPOS = "GITHUB_REPOS"
SOURCE_LABEL_MANUAL_IMPORT = "MANUAL_IMPORT"
SOURCE_LABEL_OTHER = "OTHER"


def _source_label(raw_source: str) -> str:
    """Map an internal source identifier to its compact frontend label.

    Purpose:
        Normalize source strings written by every fetcher family to the
        single set of canonical labels the dashboard renders and filters
        on. New fetcher families must extend the cascade below.
    Args:
        raw_source: Source string persisted in `job_postings.source`.
    Output:
        Returns one of the `SOURCE_LABEL_*` constants. Unknown sources
        fall through to `SOURCE_LABEL_OTHER` so they remain visible in
        the UI rather than being silently bucketed.
    """

    normalized = raw_source.lower()
    # Order matters: `apify_workday_*` rows must classify as WORKDAY,
    # not as a separate Apify family. Greenhouse comes first because the
    # `greenhouse_*` prefix is unambiguous.
    if "greenhouse" in normalized:
        return SOURCE_LABEL_GREENHOUSE
    if "workday" in normalized or "apify" in normalized:
        return SOURCE_LABEL_WORKDAY
    if normalized.startswith("jobspy"):
        return SOURCE_LABEL_JOBSPY
    if normalized.startswith("linkedin"):
        return SOURCE_LABEL_LINKEDIN
    if normalized.startswith("icims"):
        return SOURCE_LABEL_ICIMS
    if normalized.startswith("taleo"):
        return SOURCE_LABEL_TALEO
    if normalized.startswith("lever"):
        return SOURCE_LABEL_LEVER
    if normalized.startswith("ashby"):
        return SOURCE_LABEL_ASHBY
    if normalized.startswith("adzuna"):
        return SOURCE_LABEL_ADZUNA
    if normalized.startswith("github"):
        return SOURCE_LABEL_GITHUB_REPOS
    if normalized.startswith("manual"):
        return SOURCE_LABEL_MANUAL_IMPORT
    return SOURCE_LABEL_OTHER


# Mapping from canonical filter labels to the SQL fragments that match
# the corresponding raw source rows. Each entry is `(sql_clause,
# parameter_list)`. Keep aligned with `_source_label` — every label
# must be reachable in both directions.
_LABEL_TO_FILTER: dict[str, tuple[str, list[object]]] = {
    SOURCE_LABEL_GREENHOUSE: ("LOWER(jp.source) LIKE ?", ["%greenhouse%"]),
    SOURCE_LABEL_WORKDAY: (
        "(LOWER(jp.source) LIKE ? OR LOWER(jp.source) LIKE ?)",
        ["%workday%", "%apify%"],
    ),
    SOURCE_LABEL_JOBSPY: ("LOWER(jp.source) LIKE ?", ["jobspy%"]),
    SOURCE_LABEL_LINKEDIN: ("LOWER(jp.source) LIKE ?", ["linkedin%"]),
    SOURCE_LABEL_ICIMS: ("LOWER(jp.source) LIKE ?", ["icims%"]),
    SOURCE_LABEL_TALEO: ("LOWER(jp.source) LIKE ?", ["taleo%"]),
    SOURCE_LABEL_LEVER: ("LOWER(jp.source) LIKE ?", ["lever%"]),
    SOURCE_LABEL_ASHBY: ("LOWER(jp.source) LIKE ?", ["ashby%"]),
    SOURCE_LABEL_ADZUNA: ("LOWER(jp.source) LIKE ?", ["adzuna%"]),
    SOURCE_LABEL_GITHUB_REPOS: ("LOWER(jp.source) LIKE ?", ["github%"]),
    SOURCE_LABEL_MANUAL_IMPORT: ("LOWER(jp.source) LIKE ?", ["manual%"]),
}


def _source_filter_sql(source_filter: str) -> tuple[str, list[object]]:
    """Return SQL clause/params for canonical source filtering in jobs API.

    Purpose:
        Translate a user-supplied source filter (e.g. `LINKEDIN`) into
        a `WHERE` clause that matches the raw source strings persisted
        by the various fetcher families. Keeps the API contract aligned
        with `_source_label` so the dropdown values map round-trip.
    Args:
        source_filter: Requested source filter from query params. Case
            insensitive; whitespace tolerated.
    Output:
        Returns `(sql_clause, sql_params)` to append to WHERE filters.
        Unknown filter values fall through to an exact match on
        `jp.source` so callers passing a raw source string still work.
    """

    normalized_filter = source_filter.strip().upper()
    fragment = _LABEL_TO_FILTER.get(normalized_filter)
    if fragment is not None:
        return fragment
    return ("jp.source = ?", [source_filter.strip()])
