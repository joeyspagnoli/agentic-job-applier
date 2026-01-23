#!/usr/bin/env python3
"""Status dashboard script for job discovery system.

Run with: uv run python scripts/status.py
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_status():
    """Print current system status."""
    db_path = Path(__file__).parent.parent / "data" / "jobs.db"

    if not db_path.exists():
        print("Database not found. Run the job discovery first.")
        return

    db = sqlite3.connect(db_path)
    cursor = db.cursor()

    print("=" * 60)
    print("JOB DISCOVERY STATUS")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Total jobs
    total = cursor.execute("SELECT COUNT(*) FROM job_postings").fetchone()[0]
    print(f"\nTotal jobs in database: {total}")

    # New jobs today
    today = datetime.now().strftime("%Y-%m-%d")
    new_today = cursor.execute(
        "SELECT COUNT(*) FROM job_postings WHERE DATE(fetched_at) = ?",
        (today,),
    ).fetchone()[0]
    print(f"New jobs today: {new_today}")

    # New jobs in last 7 days
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    new_week = cursor.execute(
        "SELECT COUNT(*) FROM job_postings WHERE DATE(fetched_at) >= ?",
        (week_ago,),
    ).fetchone()[0]
    print(f"New jobs (last 7 days): {new_week}")

    # Jobs by status
    print("\nJobs by status:")
    statuses = cursor.execute(
        "SELECT status, COUNT(*) FROM job_postings GROUP BY status ORDER BY COUNT(*) DESC"
    ).fetchall()
    for status, count in statuses:
        print(f"  {status}: {count}")

    # Jobs by source
    print("\nJobs by source:")
    sources = cursor.execute(
        "SELECT source, COUNT(*) FROM job_postings GROUP BY source ORDER BY COUNT(*) DESC LIMIT 15"
    ).fetchall()
    for source, count in sources:
        print(f"  {source}: {count}")

    # Jobs by company (top 10)
    print("\nTop 10 companies:")
    companies = cursor.execute(
        "SELECT company, COUNT(*) as cnt FROM job_postings GROUP BY company ORDER BY cnt DESC LIMIT 10"
    ).fetchall()
    for company, count in companies:
        print(f"  {company}: {count}")

    # Recent crawls
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
        status_icon = "✓" if status == "SUCCESS" else "✗" if status == "FAILED" else "…"
        company_str = f"/{company}" if company else ""
        print(f"  {status_icon} {started} | {source}{company_str} | {new}/{found} new")

    # Failed crawls in last 24 hours
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    failed = cursor.execute(
        """
        SELECT source, company, error_message, started_at
        FROM crawl_history
        WHERE status = 'FAILED' AND started_at > ?
        ORDER BY started_at DESC
        """,
        (yesterday,),
    ).fetchall()

    if failed:
        print(f"\nFailed crawls (last 24h): {len(failed)}")
        for source, company, error, started in failed[:5]:
            company_str = f"/{company}" if company else ""
            error_short = (error[:50] + "...") if error and len(error) > 50 else error
            print(f"  {source}{company_str}: {error_short}")

    # Daily stats
    print("\nDaily statistics (last 7 days):")
    stats = cursor.execute(
        """
        SELECT date, total_jobs_discovered, jobs_new, jobs_duplicate, sources_crawled, sources_failed
        FROM daily_stats
        ORDER BY date DESC
        LIMIT 7
        """
    ).fetchall()
    for date, discovered, new, dup, crawled, failed in stats:
        print(
            f"  {date}: discovered={discovered}, new={new}, dup={dup}, "
            f"sources={crawled}, failed={failed}"
        )

    print("\n" + "=" * 60)
    db.close()


if __name__ == "__main__":
    print_status()
