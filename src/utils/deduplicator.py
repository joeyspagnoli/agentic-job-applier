"""Job deduplication utility."""

from typing import List

from loguru import logger

from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


class Deduplicator:
    """Filters out jobs that already exist in the database."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def filter_new_jobs(self, jobs: List[JobPosting]) -> List[JobPosting]:
        """Return only jobs not already in database.

        Jobs are considered duplicates if their hash matches an existing record.
        """
        new_jobs = []
        duplicate_count = 0

        for job in jobs:
            existing = await self.db.get_job_by_hash(job.job_hash)

            if existing is None:
                new_jobs.append(job)
            else:
                duplicate_count += 1

        if duplicate_count > 0:
            logger.debug(
                f"Filtered {duplicate_count} duplicate jobs, {len(new_jobs)} new"
            )

        return new_jobs

    async def get_stats(self, jobs: List[JobPosting]) -> dict:
        """Get deduplication statistics without filtering.

        Returns dict with counts of new vs duplicate jobs.
        """
        new_count = 0
        duplicate_count = 0

        for job in jobs:
            existing = await self.db.get_job_by_hash(job.job_hash)
            if existing is None:
                new_count += 1
            else:
                duplicate_count += 1

        return {
            "total": len(jobs),
            "new": new_count,
            "duplicate": duplicate_count,
        }
