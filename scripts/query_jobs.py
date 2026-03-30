#!/usr/bin/env python3
"""Query jobs from the local SQLite database.

Examples:
  uv run python -m scripts.query_jobs --company Stripe
  uv run python -m scripts.query_jobs --title "senior engineer"
  uv run python -m scripts.query_jobs --remote
  uv run python -m scripts.query_jobs --new --limit 20
"""

import argparse
import sqlite3
from typing import Optional

from src.utils.paths import resolve_database_path


def query_jobs(
    company: Optional[str] = None,
    title: Optional[str] = None,
    location: Optional[str] = None,
    remote: bool = False,
    new_only: bool = False,
    limit: int = 50,
) -> None:
    """Query the jobs database using simple CLI filters.

    Purpose:
        Provide a lightweight inspection tool for the stored job postings
        without requiring users to open SQLite manually.
    Args:
        company: Optional company-name fragment to match.
        title: Optional job-title fragment to match.
        location: Optional location fragment to match.
        remote: Whether to restrict results to remote jobs.
        new_only: Whether to restrict results to jobs discovered today.
        limit: Maximum number of rows to print.
    Output:
        Returns `None` after printing matching jobs or a helpful empty-state
        message to stdout.
    """

    db_path = resolve_database_path()
    if not db_path.exists():
        print("Database not found. Run main.py first to populate the database.")
        return

    db = sqlite3.connect(db_path)
    try:
        cursor = db.cursor()

        # The query starts with a neutral predicate so optional filters can append
        # simple `AND` clauses without branching into many query templates.
        query = (
            "SELECT company, title, location, is_remote, source_url, fetched_at "
            "FROM job_postings WHERE 1=1"
        )
        params: list[str | int] = []

        if company:
            query += " AND company LIKE ?"
            params.append(f"%{company}%")

        if title:
            query += " AND title LIKE ?"
            params.append(f"%{title}%")

        if location:
            query += " AND location LIKE ?"
            params.append(f"%{location}%")

        if remote:
            query += " AND is_remote = 1"

        if new_only:
            query += (
                " AND fetched_at >= datetime('now', 'start of day')"
                " AND fetched_at < datetime('now', 'start of day', '+1 day')"
            )

        query += " ORDER BY fetched_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        jobs = cursor.fetchall()
        if not jobs:
            print("No jobs found matching your criteria.")
            return

        print(f"\nFound {len(jobs)} jobs:\n")
        print("=" * 100)

        # The display favors scanability so users can quickly skim companies,
        # titles, remote status, URLs, and discovery times from the terminal.
        for index, (comp, job_title, loc, is_remote, url, fetched) in enumerate(jobs, 1):
            remote_badge = "[REMOTE]" if is_remote else ""
            print(f"{index}. {comp} - {job_title} {remote_badge}")
            print(f"   Location: {loc}")
            print(f"   URL: {url}")
            print(f"   Discovered: {fetched}")
            print("-" * 100)
    finally:
        db.close()


def main() -> None:
    """Parse CLI flags and print the filtered job list.

    Purpose:
        Expose the `query_jobs` helper as a command-line tool for quick local
        inspection of the SQLite database.
    Args:
        None.
    Output:
        Returns `None` after parsing CLI flags and delegating to `query_jobs`.
    """

    parser = argparse.ArgumentParser(description="Query jobs from the database")
    parser.add_argument("--company", help="Filter by company name (partial match)")
    parser.add_argument("--title", help="Filter by job title (partial match)")
    parser.add_argument("--location", help="Filter by location (partial match)")
    parser.add_argument("--remote", action="store_true", help="Show only remote jobs")
    parser.add_argument("--new", action="store_true", help="Show only jobs from today")
    parser.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")

    args = parser.parse_args()
    query_jobs(
        company=args.company,
        title=args.title,
        location=args.location,
        remote=args.remote,
        new_only=args.new,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
