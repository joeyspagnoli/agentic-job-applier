"""Provide helpers for filtering and measuring duplicate job postings."""

from typing import List

from loguru import logger

from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


class Deduplicator:
    """Filters out jobs that already exist in the database."""

    def __init__(self, db_manager: DatabaseManager):
        """Store the database manager used for duplicate checks.

        Purpose:
            Bind the deduplicator to the persistence layer so duplicate checks
            always use the same SQLite connection as the active workflow.
        Args:
            self: The deduplicator instance being initialized.
            db_manager: Connected database manager used for hash lookups.
        Output:
            Returns `None` after saving the database dependency.
        """
        self.db = db_manager

    async def filter_new_jobs(self, jobs: List[JobPosting]) -> List[JobPosting]:
        """Return only the jobs whose hashes are not already stored.

        Purpose:
            Prevent duplicate inserts during a crawl by checking each normalized
            job against the current database contents.
        Args:
            self: The deduplicator performing the duplicate checks.
            jobs: Normalized job postings returned by a fetcher.
        Output:
            Returns a list containing only jobs whose `job_hash` is not yet
            present in the database.
        """
        new_jobs: list[JobPosting] = []
        duplicate_count = 0
        seen_in_batch: set[str] = set()

        # In-batch dedup removes repeated rows before any database lookups,
        # which avoids redundant hash checks during one crawl response.
        unique_jobs: list[JobPosting] = []
        for job in jobs:
            if job.job_hash in seen_in_batch:
                duplicate_count += 1
                continue
            seen_in_batch.add(job.job_hash)
            unique_jobs.append(job)

        existing_hashes = await self.db.get_existing_job_hashes(
            [job.job_hash for job in unique_jobs]
        )

        for job in unique_jobs:
            if job.job_hash in existing_hashes:
                duplicate_count += 1
                continue
            new_jobs.append(job)

        if duplicate_count > 0:
            logger.debug(
                f"Filtered {duplicate_count} duplicate jobs, {len(new_jobs)} new"
            )

        return new_jobs

    async def get_stats(self, jobs: List[JobPosting]) -> dict:
        """Count how many jobs are new versus already present.

        Purpose:
            Provide reporting-friendly deduplication counts without mutating the
            input list or filtering jobs out of the caller's workflow.
        Args:
            self: The deduplicator performing the duplicate checks.
            jobs: Normalized job postings whose hash status should be measured.
        Output:
            Returns a dictionary with `total`, `new`, and `duplicate` counts.
        """
        duplicate_count = 0
        seen_in_batch: set[str] = set()
        unique_jobs: list[JobPosting] = []

        # Stats follow the same in-batch behavior as filtering so reporting and
        # persistence decisions do not diverge on duplicate definitions.
        for job in jobs:
            if job.job_hash in seen_in_batch:
                duplicate_count += 1
                continue
            seen_in_batch.add(job.job_hash)
            unique_jobs.append(job)

        existing_hashes = await self.db.get_existing_job_hashes(
            [job.job_hash for job in unique_jobs]
        )
        existing_duplicate_count = sum(
            1 for job in unique_jobs if job.job_hash in existing_hashes
        )
        duplicate_count += existing_duplicate_count
        new_count = len(unique_jobs) - existing_duplicate_count

        return {
            "total": len(jobs),
            "new": new_count,
            "duplicate": duplicate_count,
        }
