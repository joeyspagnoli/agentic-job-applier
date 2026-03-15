"""Define typed exceptions shared by fetcher implementations."""


class FetchError(RuntimeError):
    """Represent a source fetch failure that should count as crawl failure.

    Purpose:
        Differentiate transport/provider failures from valid empty-result
        crawls so orchestrator metrics can track outages accurately.
    Args:
        RuntimeError args: Error message describing the fetch failure.
    Output:
        Constructs an exception instance used to signal fetch failure.
    """

