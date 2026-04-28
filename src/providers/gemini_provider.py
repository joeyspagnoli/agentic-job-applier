"""Google Gemini provider for BYOK mode.

Routes completions through the Google Generative AI API using
the user-supplied API key.
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

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


class GeminiProvider:
    """Send completions to the Google Generative AI API.

    Attributes:
        _api_key: The user-supplied Google API key.
        _default_model: Model to use when the request omits one.
    """

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str | None = None,
    ) -> None:
        """Initialize the Gemini provider with credentials.

        Args:
            api_key: User-supplied Google API key.
            default_model: Default model when requests omit one.
        """
        if not api_key:
            raise ProviderAuthError(
                "API key is required for Gemini provider",
                provider="gemini",
            )
        self._api_key = api_key
        self._default_model = default_model or DEFAULT_GEMINI_MODEL

    @property
    def provider_type(self) -> ProviderType:
        """Return the provider backend type."""
        return ProviderType.GEMINI

    @property
    def is_authenticated(self) -> bool:
        """Return True if an API key is present."""
        return bool(self._api_key)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Send a completion to the Google Generative AI API.

        Args:
            request: Provider-agnostic completion request.

        Returns:
            Normalized completion response.

        Raises:
            ProviderAuthError: If the API key is invalid.
            ProviderRateLimitError: If rate-limited by Google.
            ProviderResponseError: If the response cannot be parsed.
            ProviderConnectionError: If the endpoint is unreachable.
        """
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as exc:
            raise ProviderConnectionError(
                "google-genai package is not installed. "
                "Run: pip install google-genai",
                provider="gemini",
            ) from exc

        model = request.model or self._default_model
        client = genai.Client(api_key=self._api_key)

        # Build the contents list from messages. Gemini uses "user" and "model"
        # roles. System instructions are passed separately.
        system_instruction: str | None = None
        contents: list[genai_types.Content] = []
        for msg in request.messages:
            if msg.role == "system":
                system_instruction = msg.content
                continue
            # Gemini uses "model" instead of "assistant".
            role = "model" if msg.role == "assistant" else "user"
            contents.append(
                genai_types.Content(
                    role=role,
                    parts=[genai_types.Part(text=msg.content)],
                )
            )

        config = genai_types.GenerateContentConfig(
            temperature=request.temperature,
            max_output_tokens=request.max_tokens,
            system_instruction=system_instruction,
        )

        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            error_msg = str(exc).lower()
            if "api key" in error_msg or "401" in error_msg or "403" in error_msg:
                raise ProviderAuthError(
                    f"Gemini authentication failed: {exc}",
                    provider="gemini",
                ) from exc
            if "429" in error_msg or "rate" in error_msg:
                raise ProviderRateLimitError(
                    f"Gemini rate limit hit: {exc}",
                    provider="gemini",
                ) from exc
            if "connect" in error_msg or "timeout" in error_msg:
                raise ProviderConnectionError(
                    f"Could not connect to Gemini: {exc}",
                    provider="gemini",
                ) from exc
            raise ProviderResponseError(
                f"Gemini API error: {exc}",
                provider="gemini",
            ) from exc

        content = response.text or ""
        usage_metadata = response.usage_metadata

        prompt_tokens = 0
        completion_tokens = 0
        if usage_metadata:
            prompt_tokens = getattr(usage_metadata, "prompt_token_count", 0) or 0
            completion_tokens = (
                getattr(usage_metadata, "candidates_token_count", 0) or 0
            )

        logger.debug(
            "Gemini completion: model={} tokens={}+{}",
            model,
            prompt_tokens,
            completion_tokens,
        )

        return CompletionResponse(
            content=content,
            model=model,
            provider="gemini",
            usage_prompt_tokens=prompt_tokens,
            usage_completion_tokens=completion_tokens,
        )

    async def validate_credentials(self) -> bool:
        """Test the API key with a minimal generation call.

        Returns:
            True if the key is valid, False otherwise.
        """
        try:
            from google import genai
        except ImportError:
            return False

        client = genai.Client(api_key=self._api_key)

        try:
            await client.aio.models.generate_content(
                model=self._default_model,
                contents="ping",
            )
            return True
        except Exception:
            logger.debug("Gemini credential validation failed")
            return False
