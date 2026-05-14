"""Single source of truth for the reviewer's DB-stored verdict enum.

Purpose:
    Collapse three previously duplicated string lists (the pipeline's
    `VERDICT_*_DB` constants and two `review_runs` CHECK clauses) into
    one Python `Enum` and a small SQL helper. Adding or removing a
    value now requires editing this file alone.

    This enum is intentionally separate from `pipeline_schemas.ReviewerVerdict`
    (the LLM-emitted lowercase enum) — they are different concepts:
    `DBReviewVerdict` captures the *stored* state on `review_runs`,
    while `ReviewerVerdict` captures the *LLM output* before mapping.
"""

from __future__ import annotations

from enum import Enum


class DBReviewVerdict(str, Enum):
    """Allowed values for `review_runs.verdict` after a successful run.

    Purpose:
        Mirror the historical six-value verdict list (`PASS` from the
        legacy reviewer plus the five values added during the tailor
        rewrite) so the DB-stored values match what the pipeline writes.
    """

    PASS_ = "PASS"
    TAILORED = "TAILORED"
    BASE = "BASE"
    FAIL = "FAIL"
    NO_IMPROVEMENT = "NO_IMPROVEMENT"
    PAGE_FIT_FAILED = "PAGE_FIT_FAILED"


def db_verdict_check_sql(column: str = "verdict") -> str:
    """Build the `<column> IN (...)` clause for the DB CHECK constraint.

    Purpose:
        Generate the SQL fragment from the enum so the CHECK string used
        in `migrate_review_schema` and `_widen_verdict_check_if_needed`
        cannot drift from the Python-side values.
    Args:
        column: Column name to constrain. Defaults to `verdict`.
    Output:
        Returns a SQL fragment of the form ``verdict IN ('PASS', ...)``.
    """

    values = ", ".join(repr(item.value) for item in DBReviewVerdict)
    return f"{column} IN ({values})"
