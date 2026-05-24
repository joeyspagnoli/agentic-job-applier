"""Core types and protocol for the AI provider abstraction.

The unified abstraction kept its name even after Codex / Anthropic /
Gemini providers were removed in the post-issue-61 cleanup, so the gate
/ tailor / review stages can continue depending on the `AIProvider`
protocol rather than importing the OpenAI SDK directly.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ProviderMode(str, Enum):
    """How the user authenticates with the AI backend.

    BYOK: User supplies their own API key for the configured provider.
    """

    BYOK = "byok"


class ProviderType(str, Enum):
    """Supported AI provider backends.

    Each value maps to a concrete AIProvider implementation.
    """

    OPENAI = "openai"
    OPENROUTER = "openrouter"


class CompletionMessage(BaseModel):
    """A single message in a chat completion exchange.

    Attributes:
        role: Message author role (system, user, assistant).
        content: Text content of the message.
    """

    role: str
    content: str


class CompletionRequest(BaseModel):
    """Provider-agnostic request for a chat completion.

    Attributes:
        messages: Ordered list of conversation messages.
        model: Optional model override (provider uses its default if omitted).
        temperature: Sampling temperature. Lower values are more deterministic.
        max_tokens: Maximum tokens in the completion response.
        response_format: Optional response format hint (e.g. "json").
    """

    messages: list[CompletionMessage]
    model: str | None = None
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, gt=0)
    response_format: str | None = None


class CompletionResponse(BaseModel):
    """Provider-agnostic response from a chat completion.

    Attributes:
        content: The generated text content.
        model: The model that produced this response.
        provider: The provider backend that handled the request.
        usage_prompt_tokens: Number of prompt tokens consumed.
        usage_completion_tokens: Number of completion tokens generated.
        raw_response: Optional raw response payload for debugging.
    """

    content: str
    model: str
    provider: str
    usage_prompt_tokens: int = 0
    usage_completion_tokens: int = 0
    raw_response: dict[str, object] | None = None


class ProviderConfig(BaseModel):
    """Persisted configuration for the active AI provider.

    Attributes:
        mode: Whether the user is using Codex OAuth or BYOK.
        provider_type: Which backend to route requests to.
        api_key: Encrypted API key for BYOK mode. None for Codex.
        base_url: Optional custom endpoint URL (for OpenRouter, Ollama, etc.).
        default_model: Optional default model to use when requests omit one.
        codex_home_path: Directory where Codex stores auth tokens.
    """

    mode: ProviderMode
    provider_type: ProviderType
    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    codex_home_path: str | None = None


@runtime_checkable
class AIProvider(Protocol):
    """Contract that all AI provider implementations must satisfy.

    Providers handle authentication, request formatting, and response
    parsing for a specific backend (OpenAI, Anthropic, Gemini, Codex).
    """

    @property
    def provider_type(self) -> ProviderType:
        """Return the provider backend type."""
        ...

    @property
    def is_authenticated(self) -> bool:
        """Return True if the provider has valid credentials."""
        ...

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Send a chat completion request and return the response.

        Args:
            request: Provider-agnostic completion request.

        Returns:
            A normalized completion response.

        Raises:
            ProviderAuthError: If credentials are missing or expired.
            ProviderRateLimitError: If the provider rate-limits the request.
            ProviderError: For all other provider failures.
        """
        ...

    async def validate_credentials(self) -> bool:
        """Test whether the current credentials are valid.

        Makes a minimal API call to verify the key/session works.

        Returns:
            True if credentials are valid, False otherwise.
        """
        ...
