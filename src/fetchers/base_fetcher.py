"""Abstract base class for job fetchers."""

from abc import ABC, abstractmethod
from typing import List

from src.models.job_posting import JobPosting


class BaseFetcher(ABC):
    """Abstract base class for all job fetchers."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.source_name = self.get_source_name()

    @abstractmethod
    async def fetch_jobs(self) -> List[JobPosting]:
        """Fetch jobs from source and return standardized JobPosting objects."""
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Return identifier for this source (e.g., 'greenhouse_stripe')."""
        pass

    async def __aenter__(self):
        """Support async context manager - setup resources."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup on context exit."""
        pass
