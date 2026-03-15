#!/usr/bin/env python3
"""Run manual smoke tests for the Greenhouse and JobSpy fetchers."""

import asyncio

from src.fetchers.greenhouse_fetcher import GreenhouseFetcher
from src.fetchers.jobspy_fetcher import JobSpyFetcher

# This module is intentionally a manual smoke script, not an automated test.
__test__ = False


async def smoke_greenhouse():
    """Run a manual Greenhouse smoke test against Stripe's board.

    Purpose:
        Give maintainers a quick end-to-end check that the Greenhouse fetcher
        still reaches the API and produces normalized jobs.
    Args:
        None.
    Output:
        Returns `None` after printing the smoke-test result to stdout.
    """

    print("\n" + "=" * 60)
    print("Testing Greenhouse Fetcher (Stripe)")
    print("=" * 60)

    try:
        async with GreenhouseFetcher("Stripe", "stripe") as fetcher:
            jobs = await fetcher.fetch_jobs()
            print(f"✓ Found {len(jobs)} jobs from Stripe")

            # A sample row helps confirm the parser produced a usable model
            # without dumping an entire payload to the terminal.
            if jobs:
                sample_job = jobs[0]
                print(f"  Sample job: {sample_job.title}")
                print(f"  Location: {sample_job.location}")
                print(f"  Hash: {sample_job.job_hash}")
    except Exception as e:
        print(f"✗ Error: {e}")


async def smoke_jobspy():
    """Run a manual JobSpy smoke test against Indeed.

    Purpose:
        Provide a quick sanity check that JobSpy scraping still works and that
        the parser can build normalized job objects from the results.
    Args:
        None.
    Output:
        Returns `None` after printing the smoke-test result to stdout.
    """

    print("\n" + "=" * 60)
    print("Testing JobSpy Fetcher (Indeed)")
    print("=" * 60)

    try:
        fetcher = JobSpyFetcher(
            site_name="indeed",
            search_term="python developer",
            location="Remote",
            results_wanted=5,
        )
        jobs = await fetcher.fetch_jobs()
        print(f"✓ Found {len(jobs)} jobs from Indeed")

        if jobs:
            sample_job = jobs[0]
            print(f"  Sample job: {sample_job.title} at {sample_job.company}")
            print(f"  Location: {sample_job.location}")
            print(f"  Hash: {sample_job.job_hash}")
    except Exception as e:
        print(f"✗ Error: {e}")


async def main():
    """Run the manual fetcher smoke-test sequence.

    Purpose:
        Bundle the source-specific smoke tests into one script that maintainers
        can run after changing fetcher code or local credentials.
    Args:
        None.
    Output:
        Returns `None` after running the manual smoke tests and printing the
        suggested next steps.
    """

    print("\nFetcher Test Suite")
    print("=" * 60)

    # Running both smoke tests in one place gives maintainers a fast snapshot
    # of whether the two primary fetch paths still work locally.
    await smoke_greenhouse()
    await smoke_jobspy()

    print("\n" + "=" * 60)
    print("Tests complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Configure your .env file")
    print("  2. Edit config/companies.yaml with your target companies")
    print("  3. Run: uv run python main.py")
    print("  4. Check status: uv run python -m scripts.status")


if __name__ == "__main__":
    asyncio.run(main())
