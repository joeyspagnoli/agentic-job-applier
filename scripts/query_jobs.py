#!/usr/bin/env python3
"""Query jobs from the database.

Examples:
  uv run python scripts/query_jobs.py --company Stripe
  uv run python scripts/query_jobs.py --title "senior engineer"
  uv run python scripts/query_jobs.py --remote
  uv run python scripts/query_jobs.py --new --limit 20
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def query_jobs(
    company: Optional[str] = None,
    title: Optional[str] = None,
    location: Optional[str] = None,
    remote: bool = False,
    new_only: bool = False,
    limit: int = 50,
):
    """Query jobs from database based on filters."""
    db_path = Path(__file__).parent.parent / "data" / "jobs.db"

    if not db_path.exists():
        print("Database not found. Run main.py first to populate the database.")
        return

    db = sqlite3.connect(db_path)
    cursor = db.cursor()

    # Build query
    query = "SELECT company, title, location, is_remote, source_url, fetched_at FROM job_postings WHERE 1=1"
    params = []

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
        query += " AND DATE(fetched_at) = DATE('now')"

    query += " ORDER BY fetched_at DESC LIMIT ?"
    params.append(limit)

    # Execute query
    cursor.execute(query, params)
    jobs = cursor.fetchall()

    if not jobs:
        print("No jobs found matching your criteria.")
        return

    # Display results
    print(f"\nFound {len(jobs)} jobs:\n")
    print("=" * 100)

    for i, (comp, title, loc, remote, url, fetched) in enumerate(jobs, 1):
        remote_badge = "[REMOTE]" if remote else ""
        print(f"{i}. {comp} - {title} {remote_badge}")
        print(f"   Location: {loc}")
        print(f"   URL: {url}")
        print(f"   Discovered: {fetched}")
        print("-" * 100)

    db.close()


def main():
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
