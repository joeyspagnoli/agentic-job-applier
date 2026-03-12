"""Main orchestrator for job discovery system.

Coordinates fetching from multiple sources, deduplication, and storage.
"""

import asyncio
import os
import time
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from loguru import logger

from src.database.db_manager import DatabaseManager
from src.fetchers.apify_fetcher import ApifyWorkdayFetcher
from src.fetchers.greenhouse_fetcher import GreenhouseFetcher
from src.fetchers.jobspy_fetcher import JobSpyFetcher
from src.utils.deduplicator import Deduplicator
from src.utils.logger import log_crawl_summary, log_cycle_summary, setup_logger


def load_yaml(path: str) -> dict:
    """Load a YAML configuration file."""
    with open(path) as f:
        return yaml.safe_load(f)


async def fetch_greenhouse_jobs(
    companies: dict,
    db: DatabaseManager,
    deduplicator: Deduplicator,
) -> tuple[int, int, int, int]:
    """Fetch jobs from all configured Greenhouse companies.

    Returns: (total_discovered, total_new, sources_success, sources_failed)
    """
    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    for company_name, config in companies.items():
        greenhouse_id = config.get("greenhouse_id")
        if not greenhouse_id:
            logger.warning(f"No greenhouse_id for {company_name}, skipping")
            continue

        crawl_id = await db.start_crawl("greenhouse", company_name)
        start_time = time.time()

        try:
            async with GreenhouseFetcher(company_name, greenhouse_id) as fetcher:
                jobs = await fetcher.fetch_jobs()
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                for job in new_jobs:
                    await db.insert_job(job.to_db_dict())

                duration = time.time() - start_time
                log_crawl_summary(
                    "greenhouse", company_name, len(jobs), len(new_jobs), duration
                )

                await db.complete_crawl(crawl_id, len(jobs), len(new_jobs))

                total_discovered += len(jobs)
                total_new += len(new_jobs)
                sources_success += 1

        except Exception as e:
            logger.error(f"Error fetching Greenhouse jobs for {company_name}: {e}")
            await db.complete_crawl(crawl_id, 0, 0, str(e))
            sources_failed += 1

    return total_discovered, total_new, sources_success, sources_failed


async def fetch_workday_jobs(
    companies: dict,
    db: DatabaseManager,
    deduplicator: Deduplicator,
) -> tuple[int, int, int, int]:
    """Fetch jobs from all configured Workday companies via Apify.

    Returns: (total_discovered, total_new, sources_success, sources_failed)
    """
    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    # Check if Apify is configured
    if not os.getenv("APIFY_API_TOKEN"):
        logger.warning("APIFY_API_TOKEN not set, skipping Workday sources")
        return 0, 0, 0, 0

    for company_name, config in companies.items():
        workday_url = config.get("workday_url")
        if not workday_url:
            logger.warning(f"No workday_url for {company_name}, skipping")
            continue

        crawl_id = await db.start_crawl("apify_workday", company_name)
        start_time = time.time()

        try:
            async with ApifyWorkdayFetcher(company_name, workday_url) as fetcher:
                jobs = await fetcher.fetch_jobs()
                new_jobs = await deduplicator.filter_new_jobs(jobs)

                for job in new_jobs:
                    await db.insert_job(job.to_db_dict())

                duration = time.time() - start_time
                log_crawl_summary(
                    "apify_workday", company_name, len(jobs), len(new_jobs), duration
                )

                await db.complete_crawl(crawl_id, len(jobs), len(new_jobs))

                total_discovered += len(jobs)
                total_new += len(new_jobs)
                sources_success += 1

        except Exception as e:
            logger.error(f"Error fetching Workday jobs for {company_name}: {e}")
            await db.complete_crawl(crawl_id, 0, 0, str(e))
            sources_failed += 1

    return total_discovered, total_new, sources_success, sources_failed


async def fetch_jobspy_jobs(
    job_boards: dict,
    db: DatabaseManager,
    deduplicator: Deduplicator,
) -> tuple[int, int, int, int]:
    """Fetch jobs from job boards via JobSpy.

    Returns: (total_discovered, total_new, sources_success, sources_failed)
    """
    total_discovered = 0
    total_new = 0
    sources_success = 0
    sources_failed = 0

    for board_name, config in job_boards.items():
        if not config.get("enabled", False):
            logger.debug(f"Skipping disabled board: {board_name}")
            continue

        site_name = board_name.lower()
        search_terms = config.get("search_terms", ["software engineer"])
        locations = config.get("locations", ["Remote"])
        results_wanted = config.get("results_wanted", 25)

        # Search each term/location combination
        for search_term in search_terms:
            for location in locations:
                crawl_id = await db.start_crawl(
                    f"jobspy_{site_name}", f"{search_term}@{location}"
                )
                start_time = time.time()

                try:
                    fetcher = JobSpyFetcher(
                        site_name=site_name,
                        search_term=search_term,
                        location=location,
                        results_wanted=results_wanted,
                    )
                    jobs = await fetcher.fetch_jobs()
                    new_jobs = await deduplicator.filter_new_jobs(jobs)

                    for job in new_jobs:
                        await db.insert_job(job.to_db_dict())

                    duration = time.time() - start_time
                    log_crawl_summary(
                        f"jobspy_{site_name}",
                        f"{search_term}@{location}",
                        len(jobs),
                        len(new_jobs),
                        duration,
                    )

                    await db.complete_crawl(crawl_id, len(jobs), len(new_jobs))

                    total_discovered += len(jobs)
                    total_new += len(new_jobs)
                    sources_success += 1

                except Exception as e:
                    logger.error(
                        f"Error fetching {site_name} jobs for '{search_term}' in {location}: {e}"
                    )
                    await db.complete_crawl(crawl_id, 0, 0, str(e))
                    sources_failed += 1

                # Small delay between requests to be respectful
                await asyncio.sleep(2)

    return total_discovered, total_new, sources_success, sources_failed


async def run_job_discovery() -> None:
    """Main orchestration function for job discovery cycle."""
    cycle_start = time.time()

    logger.info("=" * 60)
    logger.info("STARTING JOB DISCOVERY CYCLE")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info("=" * 60)

    # Load configuration
    config_dir = Path(__file__).parent / "config"
    companies_config = load_yaml(config_dir / "companies.yaml")

    # Initialize database
    db_path = os.getenv("DATABASE_PATH", "data/jobs.db")
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_agent_schema()
        deduplicator = Deduplicator(db)

        # Track totals
        total_discovered = 0
        total_new = 0
        total_duplicate = 0
        sources_success = 0
        sources_failed = 0

        # Fetch from Greenhouse
        greenhouse_companies = companies_config.get("greenhouse_companies", {})
        if greenhouse_companies:
            logger.info(
                f"Fetching from {len(greenhouse_companies)} Greenhouse companies..."
            )
            d, n, s, f = await fetch_greenhouse_jobs(
                greenhouse_companies, db, deduplicator
            )
            total_discovered += d
            total_new += n
            total_duplicate += d - n
            sources_success += s
            sources_failed += f

        # Fetch from Workday (via Apify)
        workday_companies = companies_config.get("workday_companies", {})
        if workday_companies:
            logger.info(f"Fetching from {len(workday_companies)} Workday companies...")
            d, n, s, f = await fetch_workday_jobs(workday_companies, db, deduplicator)
            total_discovered += d
            total_new += n
            total_duplicate += d - n
            sources_success += s
            sources_failed += f

        # Fetch from job boards (via JobSpy)
        job_boards = companies_config.get("job_boards", {})
        if job_boards:
            enabled_boards = [b for b, c in job_boards.items() if c.get("enabled")]
            logger.info(f"Fetching from {len(enabled_boards)} job boards...")
            d, n, s, f = await fetch_jobspy_jobs(job_boards, db, deduplicator)
            total_discovered += d
            total_new += n
            total_duplicate += d - n
            sources_success += s
            sources_failed += f

        # Update daily stats
        today = datetime.now().strftime("%Y-%m-%d")
        await db.update_daily_stats(
            date=today,
            jobs_discovered=total_discovered,
            jobs_new=total_new,
            jobs_duplicate=total_duplicate,
            sources_crawled=sources_success,
            sources_failed=sources_failed,
        )

        # Log final summary
        cycle_duration = time.time() - cycle_start
        log_cycle_summary(
            total_discovered,
            total_new,
            total_duplicate,
            sources_success,
            sources_failed,
            cycle_duration,
        )

        # Log database state
        total_jobs = await db.get_job_count()
        jobs_today = await db.get_jobs_today()
        logger.info(f"Database: {total_jobs} total jobs, {jobs_today} added today")


def main() -> None:
    """Entry point for job discovery."""
    # Load environment variables
    load_dotenv()

    # Setup logging
    log_file = os.getenv("LOG_FILE", "logs/job_monitor.log")
    log_level = os.getenv("LOG_LEVEL", "INFO")
    setup_logger(log_file=log_file, level=log_level)

    # Run discovery
    try:
        asyncio.run(run_job_discovery())
    except KeyboardInterrupt:
        logger.info("Job discovery interrupted by user")
    except Exception as e:
        logger.exception(f"Job discovery failed: {e}")
        raise


if __name__ == "__main__":
    main()
