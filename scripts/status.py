#!/usr/bin/env python3
"""Print a terminal summary of the current job discovery database."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from typing import Any

from src.utils.paths import resolve_database_path

CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _sanitize_terminal_text(value: Any) -> str:
    """Strip terminal control characters from untrusted text fields.

    Purpose:
        Prevent ANSI/control-sequence log spoofing when rendering company,
        source, or error strings that originated from external data.
    Args:
        value: Raw value loaded from SQLite.
    Output:
        Returns a printable string with control characters removed.
    """

    if value is None:
        return ""
    return CONTROL_CHAR_PATTERN.sub("", str(value))


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    """Check whether a SQLite table exists in the current database.

    Purpose:
        Allow the status script to degrade gracefully when schema migrations are
        incomplete or the database is partially initialized.
    Args:
        cursor: Active SQLite cursor.
        table_name: Name of the table to verify.
    Output:
        Returns `True` when the table exists, otherwise `False`.
    """

    row = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def print_status() -> None:
    """Print a summary dashboard for the local SQLite database.

    Purpose:
        Give operators a fast terminal view into job counts, crawl history, and
        recent failures without needing to inspect raw SQL manually.
    Args:
        None.
    Output:
        Returns `None` after printing the status report or an empty-state
        message when the database file does not exist yet.
    """

    db_path = resolve_database_path()
    if not db_path.exists():
        print("Database not found. Run the job discovery first.")
        return

    db = sqlite3.connect(db_path)
    try:
        cursor = db.cursor()

        print("=" * 60)
        print("JOB DISCOVERY STATUS")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        if not _table_exists(cursor, "job_postings"):
            print("\njob_postings table is missing. Run database migrations first.")
            print("\n" + "=" * 60)
            return

        total = cursor.execute("SELECT COUNT(*) FROM job_postings").fetchone()[0]
        print(f"\nTotal jobs in database: {total}")

        new_today = cursor.execute(
            """
            SELECT COUNT(*)
            FROM job_postings
            WHERE fetched_at >= datetime('now', 'start of day')
              AND fetched_at < datetime('now', 'start of day', '+1 day')
            """
        ).fetchone()[0]
        print(f"New jobs today: {new_today}")

        new_week = cursor.execute(
            """
            SELECT COUNT(*)
            FROM job_postings
            WHERE fetched_at >= datetime('now', '-7 days')
            """
        ).fetchone()[0]
        print(f"New jobs (last 7 days): {new_week}")

        print("\nJobs by status:")
        statuses = cursor.execute(
            "SELECT status, COUNT(*) FROM job_postings GROUP BY status ORDER BY COUNT(*) DESC"
        ).fetchall()
        for status, count in statuses:
            print(f"  {_sanitize_terminal_text(status)}: {count}")

        agent_columns = {
            row[1]
            for row in cursor.execute("PRAGMA table_info(job_postings)").fetchall()
        }
        has_agent_columns = {
            "agent_processed_at",
            "agent_failed_at",
            "agent_next_retry_at",
        }.issubset(agent_columns)
        if has_agent_columns:
            print("\nGate processing:")
            processed_count = cursor.execute(
                """
                SELECT COUNT(*)
                FROM job_postings
                WHERE agent_processed_at IS NOT NULL
                """
            ).fetchone()[0]
            terminal_failed_count = cursor.execute(
                """
                SELECT COUNT(*)
                FROM job_postings
                WHERE agent_failed_at IS NOT NULL
                """
            ).fetchone()[0]
            retry_ready_count = cursor.execute(
                """
                SELECT COUNT(*)
                FROM job_postings
                WHERE status = 'NEW'
                  AND agent_failed_at IS NULL
                  AND agent_processed_at IS NULL
                  AND agent_next_retry_at IS NOT NULL
                  AND agent_next_retry_at <= CURRENT_TIMESTAMP
                """
            ).fetchone()[0]
            retry_waiting_count = cursor.execute(
                """
                SELECT COUNT(*)
                FROM job_postings
                WHERE status = 'NEW'
                  AND agent_failed_at IS NULL
                  AND agent_processed_at IS NULL
                  AND agent_next_retry_at IS NOT NULL
                  AND agent_next_retry_at > CURRENT_TIMESTAMP
                """
            ).fetchone()[0]

            print(f"  Processed by gate: {processed_count}")
            print(f"  Terminal gate failures: {terminal_failed_count}")
            print(f"  Retry-ready rows: {retry_ready_count}")
            print(f"  Waiting-for-retry rows: {retry_waiting_count}")

        print("\nJobs by source:")
        sources = cursor.execute(
            "SELECT source, COUNT(*) FROM job_postings GROUP BY source ORDER BY COUNT(*) DESC LIMIT 15"
        ).fetchall()
        for source, count in sources:
            print(f"  {_sanitize_terminal_text(source)}: {count}")

        print("\nTop 10 companies:")
        companies = cursor.execute(
            "SELECT company, COUNT(*) as cnt FROM job_postings GROUP BY company ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        for company, count in companies:
            print(f"  {_sanitize_terminal_text(company)}: {count}")

        if _table_exists(cursor, "crawl_history"):
            print("\nRecent crawls (last 10):")
            recent = cursor.execute(
                """
                SELECT source, company, status, jobs_found, jobs_new, started_at
                FROM crawl_history
                ORDER BY started_at DESC
                LIMIT 10
                """
            ).fetchall()
            for source, company, status, found, new, started in recent:
                status_icon = (
                    "✓" if status == "SUCCESS" else "✗" if status == "FAILED" else "…"
                )
                source_text = _sanitize_terminal_text(source)
                company_text = _sanitize_terminal_text(company)
                started_text = _sanitize_terminal_text(started)
                company_suffix = f"/{company_text}" if company_text else ""
                print(
                    f"  {status_icon} {started_text} | {source_text}{company_suffix} | {new}/{found} new"
                )

            failed = cursor.execute(
                """
                SELECT source, company, error_message, started_at
                FROM crawl_history
                WHERE status = 'FAILED'
                  AND started_at >= datetime('now', '-1 day')
                ORDER BY started_at DESC
                """
            ).fetchall()

            if failed:
                print(f"\nFailed crawls (last 24h): {len(failed)}")
                for source, company, error, _started in failed[:5]:
                    source_text = _sanitize_terminal_text(source)
                    company_text = _sanitize_terminal_text(company)
                    error_text = _sanitize_terminal_text(error)
                    company_suffix = f"/{company_text}" if company_text else ""
                    if len(error_text) > 50:
                        error_text = f"{error_text[:50]}..."
                    print(f"  {source_text}{company_suffix}: {error_text}")
        else:
            print("\nRecent crawls: unavailable (crawl_history table missing)")

        if _table_exists(cursor, "daily_stats"):
            print("\nDaily statistics (last 7 days):")
            stats = cursor.execute(
                """
                SELECT date, total_jobs_discovered, jobs_new, jobs_duplicate, sources_crawled, sources_failed
                FROM daily_stats
                ORDER BY date DESC
                LIMIT 7
                """
            ).fetchall()
            for date_str, discovered, new, dup, crawled, failed_count in stats:
                print(
                    f"  {date_str}: discovered={discovered}, new={new}, dup={dup}, "
                    f"sources={crawled}, failed={failed_count}"
                )
        else:
            print("\nDaily statistics: unavailable (daily_stats table missing)")

        print("\n" + "=" * 60)
    except sqlite3.OperationalError as exc:
        print(f"Status unavailable due to schema error: {exc}")
    finally:
        db.close()


if __name__ == "__main__":
    print_status()
