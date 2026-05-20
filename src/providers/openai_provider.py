"""OpenAI-compatible provider for BYOK mode.

Handles OpenAI, OpenRouter, and any OpenAI-compatible endpoint
(Ollama, LM Studio, etc.) through the same implementation.
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

DEFAULT_OPENAI_MODEL = "gpt-5-mini"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-5-mini"


class OpenAIProvider:
    """Send completions to OpenAI or any OpenAI-compatible endpoint.

    Attributes:
        _api_key: The user-supplied API key.
        _base_url: Custom endpoint URL (None uses OpenAI default).
        _default_model: Model to use when the request omits one.
        _provider_type: Whether this is OpenAI proper or OpenRouter.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        default_model: str | None = None,
        provider_type: ProviderType = ProviderType.OPENAI,
    ) -> None:
        """Initialize the OpenAI provider with credentials.

        Args:
            api_key: User-supplied API key.
            base_url: Custom endpoint URL for OpenRouter, Ollama, etc.
            default_model: Default model when requests omit one.
            provider_type: OPENAI or OPENROUTER.
        """
        if not api_key:
            raise ProviderAuthError(
                "API key is required for OpenAI provider",
                provider="openai",
            )
        self._api_key = api_key
        self._base_url = base_url
        self._provider_type = provider_type
        self._default_model = default_model or (
            DEFAULT_OPENROUTER_MODEL
            if provider_type == ProviderType.OPENROUTER
            else DEFAULT_OPENAI_MODEL
        )

    @property
    def provider_type(self) -> ProviderType:
        """Return the provider backend type."""
        return self._provider_type

    @property
    def is_authenticated(self) -> bool:
        """Return True if an API key is present."""
        return bool(self._api_key)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Send a chat completion to the OpenAI-compatible endpoint.

        Args:
            request: Provider-agnostic completion request.

        Returns:
            Normalized completion response.

        Raises:
            ProviderAuthError: If the API key is invalid.
            ProviderRateLimitError: If rate-limited by the endpoint.
            ProviderResponseError: If the response cannot be parsed.
            ProviderConnectionError: If the endpoint is unreachable.
        """
        try:
            import openai
        except ImportError as exc:
            raise ProviderConnectionError(
                "openai package is not installed. Run: pip install openai",
                provider=self._provider_type.value,
            ) from exc

        model = request.model or self._default_model
        client_kwargs: dict[str, object] = {"api_key": self._api_key}
        if self._base_url:
            client_kwargs["base_url"] = self._base_url

        client = openai.AsyncOpenAI(**client_kwargs)  # type: ignore[arg-type]

        messages = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]

        create_kwargs: dict[str, object] = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_format == "json":
            create_kwargs["response_format"] = {"type": "json_object"}

        try:
            # Unpacking a heterogeneous dict[str, object] does not match
            # the overload-based typing of openai's create method.  The
            # values are validated upstream by ``LLMRequest``.
            response = await client.chat.completions.create(**create_kwargs)  # type: ignore[call-overload]
        except openai.AuthenticationError as exc:
            raise ProviderAuthError(
                f"OpenAI authentication failed: {exc}",
                provider=self._provider_type.value,
            ) from exc
        except openai.RateLimitError as exc:
            retry_after = getattr(exc, "retry_after", None)
            raise ProviderRateLimitError(
                f"OpenAI rate limit hit: {exc}",
                provider=self._provider_type.value,
                retry_after_seconds=float(retry_after) if retry_after else None,
            ) from exc
        except openai.APIConnectionError as exc:
            raise ProviderConnectionError(
                f"Could not connect to OpenAI: {exc}",
                provider=self._provider_type.value,
            ) from exc
        except openai.APIError as exc:
            raise ProviderResponseError(
                f"OpenAI API error: {exc}",
                provider=self._provider_type.value,
            ) from exc

        choice = response.choices[0]
        content = choice.message.content or ""
        usage = response.usage

        logger.debug(
            "OpenAI completion: model={} tokens={}+{}",
            response.model,
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
        )

        return CompletionResponse(
            content=content,
            model=response.model or model,
            provider=self._provider_type.value,
            usage_prompt_tokens=usage.prompt_tokens if usage else 0,
            usage_completion_tokens=usage.completion_tokens if usage else 0,
        )

    async def validate_credentials(self) -> bool:
        """Test the API key by listing models.

        Returns:
            True if the key is valid, False otherwise.
        """
        try:
            import openai
        except ImportError:
            return False

        client_kwargs: dict[str, object] = {"api_key": self._api_key}
        if self._base_url:
            client_kwargs["base_url"] = self._base_url

        client = openai.AsyncOpenAI(**client_kwargs)  # type: ignore[arg-type]

        try:
            await client.models.list()
            return True
        except Exception:
            logger.debug("OpenAI credential validation failed")
            return False
