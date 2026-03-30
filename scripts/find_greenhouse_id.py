#!/usr/bin/env python3
"""Find or verify Greenhouse company IDs from the public boards API."""

import argparse

import httpx


def check_greenhouse_id(company_id: str) -> tuple[bool, int]:
    """Check whether a Greenhouse board token exists and count its jobs.

    Purpose:
        Provide the primitive API probe used by both the search and verify
        flows in this helper script.
    Args:
        company_id: Candidate Greenhouse board token to validate.
    Output:
        Returns a tuple of `(is_valid, job_count)` describing whether the board
        exists and how many jobs the API currently exposes.
    """

    url = f"https://boards-api.greenhouse.io/v1/boards/{company_id}/jobs"

    try:
        response = httpx.get(url, timeout=10.0)
        if response.status_code == 200:
            jobs = response.json().get("jobs", [])
            return True, len(jobs)
        if response.status_code == 404:
            return False, 0

        print(f"Unexpected status code: {response.status_code}")
        return False, 0
    except Exception as e:
        print(f"Error checking {company_id}: {e}")
        return False, 0


def find_greenhouse_id(company_name: str) -> None:
    """Try several common token patterns for a company name.

    Purpose:
        Help users guess a likely Greenhouse board token when they know the
        company name but not the exact board identifier.
    Args:
        company_name: Human-readable company name to derive token guesses from.
    Output:
        Returns `None` after printing either a matching token suggestion or a
        message explaining that no pattern worked.
    """

    # The candidate patterns mirror the naming conventions Greenhouse boards
    # commonly use for multi-word company names.
    patterns = [
        company_name.lower().replace(" ", ""),
        company_name.lower().replace(" ", "-"),
        company_name.lower().split()[0],
    ]

    print(f"Searching for Greenhouse ID for: {company_name}")
    print("=" * 60)

    for pattern in patterns:
        print(f"Trying: {pattern}...", end=" ")
        is_valid, job_count = check_greenhouse_id(pattern)

        if is_valid:
            print(f"✓ FOUND! ({job_count} jobs)")
            print(f"\nAdd to config/companies.yaml:")
            print(
                f"""
  {company_name}:
    greenhouse_id: "{pattern}"
    priority: 1
"""
            )
            return

        print("✗")

    print(f"\nCould not find Greenhouse ID for {company_name}")
    print("Try searching manually at their careers page.")


def verify_greenhouse_id(company_id: str) -> None:
    """Verify one exact Greenhouse token and print its job count.

    Purpose:
        Provide a direct check for users who already know the candidate board
        token and only need confirmation.
    Args:
        company_id: Exact Greenhouse board token to validate.
    Output:
        Returns `None` after printing whether the token appears valid.
    """

    print(f"Verifying Greenhouse ID: {company_id}")
    print("=" * 60)

    is_valid, job_count = check_greenhouse_id(company_id)
    if is_valid:
        print(f"✓ Valid! Found {job_count} jobs")
        print(f"URL: https://boards.greenhouse.io/{company_id}")
        return

    print("✗ Invalid ID or no jobs found")
    print(f"Check: https://boards.greenhouse.io/{company_id}")


def main() -> None:
    """Parse CLI args and run either the search or verify flow.

    Purpose:
        Expose the Greenhouse helper functions as a small command-line utility
        for configuring new companies in the repo.
    Args:
        None.
    Output:
        Returns `None` after parsing CLI args and printing the requested result.
    """

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
