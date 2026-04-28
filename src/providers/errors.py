"""Domain-specific error hierarchy for the AI provider subsystem.

All provider errors inherit from ProviderError so callers can catch
the entire family or narrow to specific failure modes.
"""


class ProviderError(Exception):
    """Base error for all AI provider failures.

    Attributes:
        message: Human-readable error description.
        provider: Name of the provider that raised the error.
    """

    def __init__(self, message: str, *, provider: str = "unknown") -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider


class ProviderAuthError(ProviderError):
    """Raised when authentication fails or credentials are missing."""


class ProviderRateLimitError(ProviderError):
    """Raised when the provider returns a rate-limit response.

    Attributes:
        retry_after_seconds: Seconds to wait before retrying, if known.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str = "unknown",
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message, provider=provider)
        self.retry_after_seconds = retry_after_seconds


class ProviderConnectionError(ProviderError):
    """Raised when the provider endpoint is unreachable."""


class ProviderResponseError(ProviderError):
    """Raised when the provider returns an unparseable or invalid response."""
