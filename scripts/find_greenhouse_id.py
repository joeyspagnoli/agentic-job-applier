#!/usr/bin/env python3
"""Helper script to find and verify Greenhouse company IDs.

Usage:
  uv run python scripts/find_greenhouse_id.py stripe
  uv run python scripts/find_greenhouse_id.py --verify anthropic
"""

import argparse
import sys
from pathlib import Path

import httpx

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def check_greenhouse_id(company_id: str) -> tuple[bool, int]:
    """Check if a Greenhouse ID is valid.

    Returns: (is_valid, job_count)
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{company_id}/jobs"

    try:
        response = httpx.get(url, timeout=10.0)
        if response.status_code == 200:
            jobs = response.json().get("jobs", [])
            return True, len(jobs)
        elif response.status_code == 404:
            return False, 0
        else:
            print(f"Unexpected status code: {response.status_code}")
            return False, 0
    except Exception as e:
        print(f"Error checking {company_id}: {e}")
        return False, 0


def find_greenhouse_id(company_name: str):
    """Try to find a valid Greenhouse ID for a company."""
    # Common patterns
    patterns = [
        company_name.lower().replace(" ", ""),  # "Scale AI" -> "scaleai"
        company_name.lower().replace(" ", "-"),  # "Scale AI" -> "scale-ai"
        company_name.lower().split()[0],  # "Scale AI" -> "scale"
    ]

    print(f"Searching for Greenhouse ID for: {company_name}")
    print("=" * 60)

    for pattern in patterns:
        print(f"Trying: {pattern}...", end=" ")
        is_valid, job_count = check_greenhouse_id(pattern)

        if is_valid:
            print(f"✓ FOUND! ({job_count} jobs)")
            print(f"\nAdd to config/companies.yaml:")
            print(f"""
  {company_name}:
    greenhouse_id: "{pattern}"
    priority: 1
""")
            return
        else:
            print("✗")

    print(f"\nCould not find Greenhouse ID for {company_name}")
    print("Try searching manually at their careers page.")


def verify_greenhouse_id(company_id: str):
    """Verify a Greenhouse ID and show job count."""
    print(f"Verifying Greenhouse ID: {company_id}")
    print("=" * 60)

    is_valid, job_count = check_greenhouse_id(company_id)

    if is_valid:
        print(f"✓ Valid! Found {job_count} jobs")
        print(f"URL: https://boards.greenhouse.io/{company_id}")
    else:
        print(f"✗ Invalid ID or no jobs found")
        print(f"Check: https://boards.greenhouse.io/{company_id}")


def main():
    parser = argparse.ArgumentParser(
        description="Find or verify Greenhouse company IDs"
    )
    parser.add_argument("company", help="Company name or ID to check")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify an exact ID instead of searching",
    )

    args = parser.parse_args()

    if args.verify:
        verify_greenhouse_id(args.company)
    else:
        find_greenhouse_id(args.company)


if __name__ == "__main__":
    main()
