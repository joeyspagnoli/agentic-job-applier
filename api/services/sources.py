"""Source-label and source-filter helpers shared across job endpoints."""

from __future__ import annotations


def _source_label(raw_source: str) -> str:
    """Map internal source identifiers to compact frontend labels.

    Purpose:
        Normalize source strings from multiple fetchers to one stable UI enum
        without changing existing database source values.
    Args:
        raw_source: Source string persisted in `job_postings.source`.
    Output:
        Returns one of `GREENHOUSE`, `WORKDAY`, or `JOBSPY`.
    """

    normalized = raw_source.lower()
    if "greenhouse" in normalized:
        return "GREENHOUSE"
    if "workday" in normalized or "apify" in normalized:
        return "WORKDAY"
    return "JOBSPY"


def _source_filter_sql(source_filter: str) -> tuple[str, list[object]]:
    """Return SQL clause/params for canonical source filtering in jobs API.

    Purpose:
        Keep `/api/jobs` filtering aligned with `_source_label` so frontend
        source enums (`GREENHOUSE`, `WORKDAY`, `JOBSPY`) match raw persisted
        source strings such as `jobspy_linkedin_python`.
    Args:
        source_filter: Requested source filter from query params.
    Output:
        Returns `(sql_clause, sql_params)` to append to WHERE filters.
    """

    normalized_filter = source_filter.strip().upper()
    if normalized_filter == "GREENHOUSE":
        return ("LOWER(jp.source) LIKE ?", ["%greenhouse%"])
    if normalized_filter == "WORKDAY":
        return (
            "(LOWER(jp.source) LIKE ? OR LOWER(jp.source) LIKE ?)",
            ["%workday%", "%apify%"],
        )
    if normalized_filter == "JOBSPY":
        return (
            """
            (
                LOWER(jp.source) NOT LIKE ?
                AND LOWER(jp.source) NOT LIKE ?
                AND LOWER(jp.source) NOT LIKE ?
            )
            """,
            ["%greenhouse%", "%workday%", "%apify%"],
        )
    return ("jp.source = ?", [source_filter.strip()])
