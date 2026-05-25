"""OpenAI-compatible provider for BYOK mode.

Handles OpenAI, OpenRouter, and any OpenAI-compatible endpoint
(Ollama, LM Studio, etc.) through the same implementation. Cost
computation delegates to `litellm.cost_per_token()` which ships a
bundled pricing table covering the gpt-5 family (set
`LITELLM_LOCAL_MODEL_COST_MAP=true` to force local-only pricing and
avoid the network lookup).
"""

from __future__ import annotations

from typing import Any

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
    CostBreakdown,
    ProviderType,
    TokenUsage,
)

DEFAULT_OPENAI_MODEL = "gpt-5-mini"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-5-mini"

OPENAI_CACHED_INPUT_DISCOUNT = 0.5  # OpenAI bills cached input at 50% rate.


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
            Normalized completion response carrying `usage` and `cost`.

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
        token_usage = _extract_token_usage(response.usage)
        resolved_model = response.model or model
        cost = self.compute_cost(resolved_model, token_usage)

        logger.debug(
            "OpenAI completion: model={} tokens={}+{} cost=${:.6f} ({})",
            resolved_model,
            token_usage.prompt_tokens,
            token_usage.completion_tokens,
            cost.total_cost_usd,
            cost.source,
        )

        return CompletionResponse(
            content=content,
            model=resolved_model,
            provider=self._provider_type.value,
            usage=token_usage,
            cost=cost,
        )

    def compute_cost(self, model: str, usage: TokenUsage) -> CostBreakdown:
        """Compute USD cost for one OpenAI/OpenRouter completion.

        Purpose:
            Delegate to `litellm.cost_per_token()` which ships a bundled
            pricing table covering OpenAI, OpenRouter, and most major
            providers. Cached input is billed at 50% per OpenAI's policy;
            the discount is applied before summing into `total_cost_usd`.
        Args:
            model: Fully qualified or provider-bare model identifier.
                LiteLLM accepts both `openai/gpt-5.4-mini` and
                `gpt-5.4-mini`.
            usage: Token counts captured from the raw completion.
        Returns:
            A populated `CostBreakdown` with `source="computed"` on
            success, or `source="unknown"` and zero costs when pricing
            for the model is not available.
        """

        try:
            from litellm import cost_per_token
        except ImportError:
            logger.warning(
                "litellm not installed; cost computation unavailable for {}",
                model,
            )
            return CostBreakdown(source="unknown")

        billable_prompt_tokens = max(
            usage.prompt_tokens - usage.cached_input_tokens, 0
        )

        try:
            prompt_cost, completion_cost = cost_per_token(
                model=model,
                prompt_tokens=billable_prompt_tokens,
                completion_tokens=usage.completion_tokens,
            )
        except Exception as exc:  # litellm raises BadRequestError for unknown models
            logger.debug(
                "litellm cost_per_token failed for model {}: {}",
                model,
                exc,
            )
            return CostBreakdown(source="unknown")

        cached_cost = 0.0
        if usage.cached_input_tokens > 0:
            try:
                cached_prompt_cost, _ = cost_per_token(
                    model=model,
                    prompt_tokens=usage.cached_input_tokens,
                    completion_tokens=0,
                )
            except Exception:  # pragma: no cover - already-warned model path
                cached_prompt_cost = 0.0
            cached_cost = float(cached_prompt_cost) * OPENAI_CACHED_INPUT_DISCOUNT

        input_cost = float(prompt_cost)
        output_cost = float(completion_cost)
        total = input_cost + output_cost + cached_cost

        return CostBreakdown(
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            cached_input_cost_usd=cached_cost,
            total_cost_usd=total,
            source="computed",
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


def _extract_token_usage(raw_usage: Any) -> TokenUsage:
    """Build a `TokenUsage` from an OpenAI-shaped usage object.

    Purpose:
        Centralize the parsing so both ChatCompletions and Responses
        shapes resolve to the same canonical accounting; missing fields
        default to zero so the caller never has to guard.
    Args:
        raw_usage: Provider response usage object, or `None`.
    Returns:
        Populated `TokenUsage` (zero-filled when `raw_usage is None`).
    """

    if raw_usage is None:
        return TokenUsage()

    prompt_tokens = int(getattr(raw_usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(raw_usage, "completion_tokens", 0) or 0)

    cached_input_tokens = 0
    prompt_details = getattr(raw_usage, "prompt_tokens_details", None)
    if prompt_details is not None:
        cached_input_tokens = int(getattr(prompt_details, "cached_tokens", 0) or 0)

    reasoning_tokens = 0
    completion_details = getattr(raw_usage, "completion_tokens_details", None)
    if completion_details is not None:
        reasoning_tokens = int(
            getattr(completion_details, "reasoning_tokens", 0) or 0
        )

    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_input_tokens=cached_input_tokens,
        reasoning_tokens=reasoning_tokens,
    )
