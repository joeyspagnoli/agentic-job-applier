"""Define the shared interface that all job fetchers must implement."""

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Any

from src.models.job_posting import JobPosting


class BaseFetcher(ABC):
    """Abstract base class for all job fetchers."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Store fetcher configuration and compute the source name.

        Purpose:
            Give each concrete fetcher a small shared initializer for storing
            config and exposing a stable source identifier.
        Args:
            self: The fetcher instance being initialized.
            config: Optional fetcher-specific configuration metadata.
        Output:
            Returns `None` after saving the config and derived source name.
        """
        self.config = config or {}
        self.source_name = self.get_source_name()

    @abstractmethod
    async def fetch_jobs(self) -> list[JobPosting]:
        """Fetch jobs from the source and normalize them to `JobPosting`.

        Purpose:
            Define the contract that each concrete fetcher must satisfy before
            its results can enter the deduplication and persistence pipeline.
        Args:
            self: The fetcher instance performing the network or scrape request.
        Output:
            Returns a list of normalized `JobPosting` objects.
        """
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Return the stable source identifier for the fetcher.

        Purpose:
            Ensure each fetcher can label its jobs and crawl history with a
            predictable, source-specific identifier.
        Args:
            self: The fetcher instance reporting its source name.
        Output:
            Returns a machine-friendly source identifier string.
        """
        pass

    async def __aenter__(self) -> "BaseFetcher":
        """Enter the async context manager for the fetcher.

        Purpose:
            Provide a default context-manager implementation so subclasses can
            opt into setup behavior only when they need external resources.
        Args:
            self: The fetcher instance entering the context.
        Output:
            Returns the fetcher instance itself.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager for the fetcher.

        Purpose:
            Provide a default no-op cleanup hook that subclasses can override
            when they manage clients or other external resources.
        Args:
            self: The fetcher instance exiting the context.
            exc_type: Exception type raised inside the context, if any.
            exc_val: Exception instance raised inside the context, if any.
            exc_tb: Traceback for the exception raised inside the context.
        Output:
            Returns `None` after the default no-op cleanup path.
        """
        pass
