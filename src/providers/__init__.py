"""Unified AI provider abstraction for all pipeline stages.

This module provides a single interface for routing AI calls through
either Codex (OAuth device auth) or a user-supplied API key (BYOK).
All pipeline stages — gate, tailor, review — use this abstraction
instead of importing provider-specific SDKs directly.
"""

from src.providers.errors import ProviderAuthError, ProviderError, ProviderRateLimitError
from src.providers.types import (
    AIProvider,
    CompletionRequest,
    CompletionResponse,
    ProviderConfig,
    ProviderMode,
    ProviderType,
)

__all__ = [
    "AIProvider",
    "CompletionRequest",
    "CompletionResponse",
    "ProviderAuthError",
    "ProviderConfig",
    "ProviderError",
    "ProviderMode",
    "ProviderRateLimitError",
    "ProviderType",
]
