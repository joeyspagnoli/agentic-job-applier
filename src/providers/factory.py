"""Provider factory that builds the correct AIProvider from config.

Reads provider settings from the database or environment and returns
a configured provider instance. The factory is the single entry point
that pipeline stages use to get their AI provider.
"""

from __future__ import annotations

import os

from loguru import logger

from src.providers.anthropic_provider import AnthropicProvider
from src.providers.codex_provider import CodexProvider
from src.providers.errors import ProviderAuthError, ProviderError
from src.providers.gemini_provider import GeminiProvider
from src.providers.openai_provider import OpenAIProvider
from src.providers.types import (
    AIProvider,
    ProviderConfig,
    ProviderMode,
    ProviderType,
)

# Singleton Codex provider so device auth state persists across requests.
_codex_provider_instance: CodexProvider | None = None


def get_codex_provider() -> CodexProvider:
    """Return the singleton Codex provider instance.

    Creates the instance on first call with CODEX_HOME from env.

    Returns:
        The shared CodexProvider instance.
    """
    global _codex_provider_instance  # noqa: PLW0603
    if _codex_provider_instance is None:
        codex_home = os.environ.get("CODEX_HOME", "")
        _codex_provider_instance = CodexProvider(codex_home=codex_home)
    return _codex_provider_instance


def build_provider(config: ProviderConfig) -> AIProvider:
    """Build an AI provider from a configuration object.

    Args:
        config: Provider configuration with mode, type, and credentials.

    Returns:
        A configured AIProvider implementation.

    Raises:
        ProviderAuthError: If required credentials are missing.
        ProviderError: If the provider type is not supported.
    """
    if config.mode == ProviderMode.CODEX:
        return get_codex_provider()

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

    if config.provider_type == ProviderType.ANTHROPIC:
        return AnthropicProvider(
            api_key=config.api_key,
            default_model=config.default_model,
        )

    if config.provider_type == ProviderType.GEMINI:
        return GeminiProvider(
            api_key=config.api_key,
            default_model=config.default_model,
        )

    raise ProviderError(
        f"Unsupported provider type: {config.provider_type.value}",
        provider=config.provider_type.value,
    )


def build_provider_from_env() -> AIProvider:
    """Build a provider from environment variables as fallback.

    Checks env vars in priority order: CODEX_HOME (if codex CLI present),
    OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY.

    Returns:
        The first provider with valid credentials.

    Raises:
        ProviderAuthError: If no provider credentials are found.
    """
    # Check Codex first — it doesn't need an API key.
    codex_provider = get_codex_provider()
    if codex_provider.is_authenticated:
        logger.info("Using Codex provider (authenticated session found)")
        return codex_provider

    # Check BYOK keys in priority order.
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        logger.info("Using OpenAI provider from OPENAI_API_KEY env var")
        return OpenAIProvider(api_key=openai_key)

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        logger.info("Using Anthropic provider from ANTHROPIC_API_KEY env var")
        return AnthropicProvider(api_key=anthropic_key)

    google_key = os.environ.get("GOOGLE_API_KEY", "")
    if google_key:
        logger.info("Using Gemini provider from GOOGLE_API_KEY env var")
        return GeminiProvider(api_key=google_key)

    raise ProviderAuthError(
        "No AI provider credentials found. Configure Codex login or set "
        "OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY.",
        provider="none",
    )
