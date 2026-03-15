"""Export the fetcher implementations used by the orchestrator."""

from src.fetchers.base_fetcher import BaseFetcher
from src.fetchers.errors import FetchError
from src.fetchers.greenhouse_fetcher import GreenhouseFetcher
from src.fetchers.apify_fetcher import ApifyWorkdayFetcher
from src.fetchers.jobspy_fetcher import JobSpyFetcher

# Re-exporting the fetchers from one module makes the package easier to browse
# and gives callers a single import surface for supported source types.
__all__ = [
    "BaseFetcher",
    "FetchError",
    "GreenhouseFetcher",
    "ApifyWorkdayFetcher",
    "JobSpyFetcher",
]
