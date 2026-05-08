"""Helpers for building unified failure records from stage-specific SQL sources."""

from __future__ import annotations

from typing import Any
from typing import cast

from src.database.db_manager import DatabaseManager


async def fetch_gate_failure_rows(conn: Any) -> list[Any]:
    """Fetch gate-failure rows from `job_postings`.

    Purpose:
        Centralize the GATE-stage failure SQL so the failures endpoint can
        compose stage rows without inlining repetitive queries.
    Args:
        conn: Active aiosqlite connection.
    Output:
        Returns ordered list of gate-failure rows.
    """

    cursor = await conn.execute(
        """
        SELECT
            jp.job_hash,
            jp.company,
            jp.title,
            jp.agent_error,
            jp.agent_retry_count,
            jp.agent_failed_at,
            jp.source,
            jp.source_url
        FROM job_postings jp
        WHERE jp.agent_failed_at IS NOT NULL
        """
    )
    return cast(list[Any], await cursor.fetchall())


async def fetch_tailor_failure_rows(conn: Any) -> list[Any]:
    """Fetch tailor-failure rows joined with their job postings.

    Purpose:
        Encapsulate TAILOR failure aggregation so the route handler stays
        focused on response composition.
    Args:
        conn: Active aiosqlite connection.
    Output:
        Returns ordered list of tailor-failure rows.
    """

    cursor = await conn.execute(
        """
        SELECT
            tr.id,
            tr.job_hash,
            tr.error,
            tr.next_retry_at,
            COALESCE(tr.completed_at, tr.started_at) AS event_time,
            jp.company,
            jp.title,
            jp.source,
            jp.source_url,
            (
                SELECT COUNT(*)
                FROM tailor_runs tr_count
                WHERE tr_count.job_hash = tr.job_hash
                  AND tr_count.status = 'FAILED'
            ) AS attempts
        FROM tailor_runs tr
        JOIN job_postings jp ON jp.job_hash = tr.job_hash
        WHERE tr.status = 'FAILED'
        """
    )
    return cast(list[Any], await cursor.fetchall())


async def fetch_review_failure_rows(conn: Any) -> list[Any]:
    """Fetch review-failure rows joined with their job postings.

    Purpose:
        Encapsulate REVIEW failure aggregation so the route handler stays
        focused on response composition.
    Args:
        conn: Active aiosqlite connection.
    Output:
        Returns ordered list of review-failure rows.
    """

    cursor = await conn.execute(
        """
        SELECT
            rr.id,
            rr.job_hash,
            rr.error,
            rr.next_retry_at,
            COALESCE(rr.completed_at, rr.started_at) AS event_time,
            jp.company,
            jp.title,
            jp.source,
            jp.source_url,
            (
                SELECT COUNT(*)
                FROM review_runs rr_count
                WHERE rr_count.tailor_run_id = rr.tailor_run_id
                  AND rr_count.status = 'FAILED'
            ) AS attempts
        FROM review_runs rr
        JOIN job_postings jp ON jp.job_hash = rr.job_hash
        WHERE rr.status = 'FAILED'
        """
    )
    return cast(list[Any], await cursor.fetchall())


async def fetch_apply_failure_rows(conn: Any) -> list[Any]:
    """Fetch apply-failure rows joined with their job postings.

    Purpose:
        Encapsulate APPLY failure aggregation so the route handler stays
        focused on response composition.
    Args:
        conn: Active aiosqlite connection.
    Output:
        Returns ordered list of apply-failure rows.
    """

    cursor = await conn.execute(
        """
        SELECT
            ar.id,
            ar.job_hash,
            ar.error,
            ar.next_retry_at,
            COALESCE(ar.completed_at, ar.started_at) AS event_time,
            jp.company,
            jp.title,
            jp.source,
            jp.source_url,
            (
                SELECT COUNT(*)
                FROM apply_runs ar_count
                WHERE ar_count.review_run_id = ar.review_run_id
                  AND ar_count.status = 'FAILED'
            ) AS attempts
        FROM apply_runs ar
        JOIN job_postings jp ON jp.job_hash = ar.job_hash
        WHERE ar.status = 'FAILED'
        """
    )
    return cast(list[Any], await cursor.fetchall())


async def collect_failure_rows(
    db: DatabaseManager,
) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
    """Run all four stage failure queries against an active database manager.

    Purpose:
        Reduce inline SQL noise inside the failures route handler.
    Args:
        db: Open `DatabaseManager` with migrations already applied.
    Output:
        Returns gate/tailor/review/apply failure rows in that order.
    """

    assert db.conn is not None
    conn = db.conn
    gate_rows = await fetch_gate_failure_rows(conn)
    tailor_rows = await fetch_tailor_failure_rows(conn)
    review_rows = await fetch_review_failure_rows(conn)
    apply_rows = await fetch_apply_failure_rows(conn)
    return gate_rows, tailor_rows, review_rows, apply_rows


def serialize_failure_record(
    *,
    failure_id: str,
    stage: str,
    company: str,
    position: str,
    error_text: str,
    attempts: int,
    max_attempts: int,
    status: str,
    platform: str,
    job_posting_url: str,
    event_time: str,
) -> dict[str, object]:
    """Build one normalized failure record for the failures endpoint.

    Purpose:
        Keep the failures API response shape stable across stage-specific SQL
        sources (gate/tailor/review/apply).
    Args:
        failure_id: Stage-qualified failure identifier.
        stage: Pipeline stage label.
        company: Company name for the failed job.
        position: Job title for the failed job.
        error_text: Raw error text.
        attempts: Number of attempts recorded.
        max_attempts: Maximum retry attempts configured for the stage.
        status: Retry status (`RETRYING` or `EXHAUSTED`).
        platform: Source platform label.
        job_posting_url: Original job posting URL.
        event_time: Timestamp string for sorting.
    Output:
        Returns normalized failure record dictionary.
    """

    short_error_code = (
        error_text.split("\n", maxsplit=1)[0].split(":", maxsplit=1)[0].strip().upper()
    )
    if short_error_code == "":
        short_error_code = "UNKNOWN_FAILURE"

    return {
        "id": failure_id,
        "stage": stage,
        "company": company,
        "position": position,
        "error_code": short_error_code,
        "attempts": attempts,
        "max_attempts": max_attempts,
        "time": event_time,
        "status": status,
        "error_trace": [line for line in error_text.splitlines() if line.strip() != ""],
        "platform": platform,
        "job_posting_url": job_posting_url,
    }
