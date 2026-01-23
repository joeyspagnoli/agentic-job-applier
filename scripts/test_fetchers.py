#!/usr/bin/env python3
"""Test script to verify all fetchers work correctly.

Run with: uv run python scripts/test_fetchers.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.fetchers.greenhouse_fetcher import GreenhouseFetcher
from src.fetchers.jobspy_fetcher import JobSpyFetcher


async def test_greenhouse():
    """Test Greenhouse fetcher with Stripe."""
    print("\n" + "=" * 60)
    print("Testing Greenhouse Fetcher (Stripe)")
    print("=" * 60)
    try:
        async with GreenhouseFetcher("Stripe", "stripe") as fetcher:
            jobs = await fetcher.fetch_jobs()
            print(f"✓ Found {len(jobs)} jobs from Stripe")
            if jobs:
                j = jobs[0]
                print(f"  Sample job: {j.title}")
                print(f"  Location: {j.location}")
                print(f"  Hash: {j.job_hash}")
    except Exception as e:
        print(f"✗ Error: {e}")


async def test_jobspy():
    """Test JobSpy fetcher with Indeed."""
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
            j = jobs[0]
            print(f"  Sample job: {j.title} at {j.company}")
            print(f"  Location: {j.location}")
            print(f"  Hash: {j.job_hash}")
    except Exception as e:
        print(f"✗ Error: {e}")


async def main():
    """Run all fetcher tests."""
    print("\nFetcher Test Suite")
    print("=" * 60)

    await test_greenhouse()
    await test_jobspy()

    print("\n" + "=" * 60)
    print("Tests complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Configure your .env file")
    print("  2. Edit config/companies.yaml with your target companies")
    print("  3. Run: uv run python main.py")
    print("  4. Check status: uv run python scripts/status.py")


if __name__ == "__main__":
    asyncio.run(main())
