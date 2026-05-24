"""Provider factory for the OpenAI BYOK pipeline.

Anthropic, Gemini, and Codex device-auth providers were removed in the
post-issue-61 cleanup. The pipeline now resolves to a single OpenAI
provider built from `OPENAI_API_KEY`, keeping a thin abstraction so the
gate / tailor / review stages can still depend on the `AIProvider`
protocol without re-importing the OpenAI SDK directly.
"""

from __future__ import annotations

import os

from src.providers.errors import ProviderAuthError, ProviderError
from src.providers.openai_provider import OpenAIProvider
from src.providers.types import (
    AIProvider,
    ProviderConfig,
    ProviderType,
)


def build_provider(config: ProviderConfig) -> AIProvider:
    """Build an AI provider from a configuration object.

    Purpose:
        Centralize provider construction so the pipeline never imports the
        OpenAI SDK directly. Only the OpenAI BYOK provider type is supported
        in this release.
    Args:
        config: Provider configuration with type and credentials.
    Output:
        Returns a configured `OpenAIProvider` (or `OpenAIProvider` aimed at
        OpenRouter when `config.provider_type == OPENROUTER`).
    Raises:
        ProviderAuthError: When `api_key` is missing.
        ProviderError: When `provider_type` is not OpenAI or OpenRouter.
    """

    if not config.api_key:
        raise ProviderAuthError(
            f"API key is required for {config.provider_type.value} provider",
            provider=config.provider_type.value,
        )

    if config.provider_type == ProviderType.OPENAI:
        return OpenAIProvider(
            api_key=config.api_key,
            base_url=config.base_url,
            default_model=config.default_model,
            provider_type=ProviderType.OPENAI,
        )

    if config.provider_type == ProviderType.OPENROUTER:
        return OpenAIProvider(
            api_key=config.api_key,
            base_url=config.base_url or "https://openrouter.ai/api/v1",
            default_model=config.default_model,
            provider_type=ProviderType.OPENROUTER,
        )

    raise ProviderError(
        (
            f"Unsupported provider type: {config.provider_type.value}. "
            "Anthropic, Gemini, and Codex providers were removed."
        ),
        provider=config.provider_type.value,
    )


def build_provider_from_env() -> AIProvider:
    """Build an OpenAI provider from `OPENAI_API_KEY` in the environment.

    Purpose:
        Provide a single env-driven entry point for any caller that wants
        the project's "default" provider without threading config objects.
    Args:
        None.
    Output:
        Returns an `OpenAIProvider` initialized from `OPENAI_API_KEY`.
    Raises:
        ProviderAuthError: When `OPENAI_API_KEY` is not set.
    """

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not openai_key:
        raise ProviderAuthError(
            "OPENAI_API_KEY is not set; cannot build an AI provider.",
            provider=ProviderType.OPENAI.value,
        )
    return OpenAIProvider(api_key=openai_key)
