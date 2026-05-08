"""Anthropic provider for BYOK mode.

Routes completions through the Anthropic Messages API using the
user-supplied API key.
"""

from __future__ import annotations

from loguru import logger

from src.providers.errors import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from src.providers.types import (
    CompletionRequest,
    CompletionResponse,
    ProviderType,
)

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"


class AnthropicProvider:
    """Send completions to the Anthropic Messages API.

    Attributes:
        _api_key: The user-supplied Anthropic API key.
        _default_model: Model to use when the request omits one.
    """

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str | None = None,
    ) -> None:
        """Initialize the Anthropic provider with credentials.

        Args:
            api_key: User-supplied Anthropic API key.
            default_model: Default model when requests omit one.
        """
        if not api_key:
            raise ProviderAuthError(
                "API key is required for Anthropic provider",
                provider="anthropic",
            )
        self._api_key = api_key
        self._default_model = default_model or DEFAULT_ANTHROPIC_MODEL

    @property
    def provider_type(self) -> ProviderType:
        """Return the provider backend type."""
        return ProviderType.ANTHROPIC

    @property
    def is_authenticated(self) -> bool:
        """Return True if an API key is present."""
        return bool(self._api_key)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Send a chat completion to the Anthropic Messages API.

        Args:
            request: Provider-agnostic completion request.

        Returns:
            Normalized completion response.

        Raises:
            ProviderAuthError: If the API key is invalid.
            ProviderRateLimitError: If rate-limited by Anthropic.
            ProviderResponseError: If the response cannot be parsed.
            ProviderConnectionError: If the endpoint is unreachable.
        """
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderConnectionError(
                "anthropic package is not installed. Run: pip install anthropic",
                provider="anthropic",
            ) from exc

        model = request.model or self._default_model
        client = anthropic.AsyncAnthropic(api_key=self._api_key)

        # Anthropic uses a separate system parameter instead of a system message.
        system_text = ""
        api_messages: list[dict[str, str]] = []
        for msg in request.messages:
            if msg.role == "system":
                system_text = msg.content
            else:
                api_messages.append({"role": msg.role, "content": msg.content})

        create_kwargs: dict[str, object] = {
            "model": model,
            "messages": api_messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if system_text:
            create_kwargs["system"] = system_text

        try:
            # Unpacking a heterogeneous dict[str, object] does not match
            # the overload-based typing of anthropic's create method.  The
            # values are validated upstream by ``LLMRequest``.
            response = await client.messages.create(**create_kwargs)  # type: ignore[call-overload]
        except anthropic.AuthenticationError as exc:
            raise ProviderAuthError(
                f"Anthropic authentication failed: {exc}",
                provider="anthropic",
            ) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderRateLimitError(
                f"Anthropic rate limit hit: {exc}",
                provider="anthropic",
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderConnectionError(
                f"Could not connect to Anthropic: {exc}",
                provider="anthropic",
            ) from exc
        except anthropic.APIError as exc:
            raise ProviderResponseError(
                f"Anthropic API error: {exc}",
                provider="anthropic",
            ) from exc

        # Extract text from the response content blocks.
        content_parts: list[str] = []
        for block in response.content:
            if hasattr(block, "text"):
                content_parts.append(block.text)
        content = "".join(content_parts)

        usage = response.usage

        logger.debug(
            "Anthropic completion: model={} tokens={}+{}",
            response.model,
            usage.input_tokens,
            usage.output_tokens,
        )

        return CompletionResponse(
            content=content,
            model=response.model,
            provider="anthropic",
            usage_prompt_tokens=usage.input_tokens,
            usage_completion_tokens=usage.output_tokens,
        )

    async def validate_credentials(self) -> bool:
        """Test the API key with a minimal completion call.

        Returns:
            True if the key is valid, False otherwise.
        """
        try:
            import anthropic
        except ImportError:
            return False

        client = anthropic.AsyncAnthropic(api_key=self._api_key)

        try:
            await client.messages.create(
                model=self._default_model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            logger.debug("Anthropic credential validation failed")
            return False
