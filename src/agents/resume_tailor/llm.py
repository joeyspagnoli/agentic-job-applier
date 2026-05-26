"""Instructor-backed LLM calls for the tailor, trim, and reviewer stages.

Each public function takes a fully assembled user message, sends it to
the configured model, validates the response against the corresponding
Pydantic schema, and returns the parsed object alongside token usage
for cost tracking. Instructor handles validation re-asks automatically:
when the model returns malformed JSON or a payload that fails Pydantic
validation, the library re-prompts with the error attached, up to
`INSTRUCTOR_MAX_RETRIES` times.

Provider selection is driven by env vars so the rest of the pipeline
does not need to know whether OpenAI, Anthropic, or another backend is
in use. Defaults: tailor/trim run on `openai/gpt-5.4` because smaller
models tend to compress bullets and strip `\textbf{}` macros even with
explicit rules in the prompt; the reviewer stays on `openai/gpt-5-mini`
since rubric scoring tolerates the smaller model and the budget impact
is per-call, per-job.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Generic, Type, TypeVar

import instructor
from loguru import logger
from openai import OpenAI

from src.providers.openai_provider import OpenAIProvider
from src.providers.types import CostBreakdown, ProviderType, TokenUsage

from .pipeline_schemas import ReviewerOutput, TailorOutput
from .prompts import REVIEWER_INSTRUCTION, TAILOR_INSTRUCTION, TRIM_INSTRUCTION

DEFAULT_TAILOR_MODEL = "openai/gpt-5.4"
DEFAULT_REVIEWER_MODEL = "openai/gpt-5-mini"

TAILOR_MODEL_ENV_VAR = "RESUME_TAILOR_MODEL"
REVIEWER_MODEL_ENV_VAR = "RESUME_REVIEWER_MODEL"

INSTRUCTOR_MAX_RETRIES = 3

T = TypeVar("T")


@lru_cache(maxsize=1)
def _get_cost_provider() -> OpenAIProvider:
    """Return a lazily constructed OpenAIProvider used only for cost computation.

    Purpose:
        `compute_cost` delegates to `litellm.cost_per_token` and never
        touches the network, so the `api_key` value here is irrelevant.
        A placeholder is used to satisfy the constructor guard; `OPENAI_API_KEY`
        from the environment is preferred when available.
    """
    return OpenAIProvider(
        api_key=os.environ.get("OPENAI_API_KEY", "x"),
        provider_type=ProviderType.OPENAI,
    )


@dataclass(frozen=True)
class LlmCallResult(Generic[T]):
    """Result of one structured LLM call.

    Purpose:
        Bundle the parsed Pydantic response with the raw token usage
        metadata so the pipeline can record cost telemetry without
        re-querying the provider.

    Attributes:
        parsed: Validated Pydantic model returned by the LLM.
        model: Fully qualified ``provider/model`` identifier used for the call.
        usage: Per-call token accounting extracted from the provider response.
        cost: USD cost breakdown computed from ``usage`` via the provider's
            pricing table.
        prompt_tokens: Convenience alias for ``usage.prompt_tokens``.
        completion_tokens: Convenience alias for ``usage.completion_tokens``.
        total_tokens: Convenience alias for the sum of prompt + completion.
    """

    parsed: T
    model: str
    usage: TokenUsage
    cost: CostBreakdown
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def get_tailor_model_name() -> str:
    """Return the tailor model identifier, honoring env override.

    Purpose:
        Centralize model resolution so the client factory and cost
        metadata observers see the same string.
    Args:
        None.
    Output:
        Returns the fully qualified provider/model identifier.
    """

    return os.getenv(TAILOR_MODEL_ENV_VAR, "").strip() or DEFAULT_TAILOR_MODEL


def get_reviewer_model_name() -> str:
    """Return the reviewer model identifier, honoring env override.

    Purpose:
        Centralize model resolution for the reviewer call path.
    Args:
        None.
    Output:
        Returns the fully qualified provider/model identifier.
    """

    return os.getenv(REVIEWER_MODEL_ENV_VAR, "").strip() or DEFAULT_REVIEWER_MODEL


def _split_provider_and_model(qualified: str) -> tuple[str, str]:
    """Split a `provider/model` identifier into its two parts.

    Purpose:
        Validate the identifier shape and fail fast when a model name
        without a provider prefix is supplied.
    Args:
        qualified: String of the form `provider/model-name`.
    Output:
        Returns `(provider, model)` with both parts non-empty.
    Raises:
        ValueError: When the identifier does not contain a `/` or either
            side is empty.
    """

    if "/" not in qualified:
        raise ValueError(
            f"Model identifier must be 'provider/model', got {qualified!r}"
        )
    provider, _, model = qualified.partition("/")
    provider = provider.strip()
    model = model.strip()
    if not provider or not model:
        raise ValueError(
            f"Model identifier must be 'provider/model', got {qualified!r}"
        )
    return provider, model


def _build_client(qualified_model: str) -> tuple[Any, str]:
    """Build an Instructor-patched client for the given provider/model.

    Purpose:
        Keep credential checks and provider-client selection in one
        place. Only OpenAI is wired today; Anthropic / Gemini can be
        added by extending the provider match without touching call sites.
    Args:
        qualified_model: Identifier of the form `provider/model-name`.
    Output:
        Returns `(instructor_client, bare_model_name)`.
    Raises:
        RuntimeError: When the provider's API key is missing.
        ValueError: When the provider is not supported.
    """

    provider, bare_model = _split_provider_and_model(qualified_model)

    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY is not set; resume-tailor LLM calls cannot run."
            )
        # Use the OpenAI Responses API so newer "responses-only" models
        # (including the gpt-5 family) work alongside legacy models.
        client = instructor.from_openai(
            OpenAI(), mode=instructor.Mode.RESPONSES_TOOLS,
        )
        return client, bare_model

    raise ValueError(
        f"Unsupported provider {provider!r} in model identifier {qualified_model!r}"
    )


def _extract_usage(raw_completion: Any) -> TokenUsage:
    """Pull token usage out of a raw completion object.

    Purpose:
        Instructor returns the underlying provider response object
        alongside the parsed Pydantic model; this helper normalizes the
        usage fields across providers that report them slightly differently.
        Reads ``prompt_tokens_details.cached_tokens`` and
        ``completion_tokens_details.reasoning_tokens`` when present (zero
        when not available).
    Args:
        raw_completion: Raw completion returned by
            `create_with_completion`.
    Output:
        Returns a populated `TokenUsage` with any missing field coerced to `0`.
    """

    usage = getattr(raw_completion, "usage", None)
    if usage is None:
        return TokenUsage()

    # Responses API uses input_tokens/output_tokens; Chat Completions uses
    # prompt_tokens/completion_tokens. Read either spelling.
    prompt = int(
        getattr(usage, "prompt_tokens", None)
        or getattr(usage, "input_tokens", 0)
        or 0
    )
    completion = int(
        getattr(usage, "completion_tokens", None)
        or getattr(usage, "output_tokens", 0)
        or 0
    )

    cached_input_tokens = 0
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    if prompt_details is not None:
        cached_input_tokens = int(getattr(prompt_details, "cached_tokens", 0) or 0)

    reasoning_tokens = 0
    completion_details = getattr(usage, "completion_tokens_details", None)
    if completion_details is not None:
        reasoning_tokens = int(
            getattr(completion_details, "reasoning_tokens", 0) or 0
        )

    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        cached_input_tokens=cached_input_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def _structured_call_sync(
    *,
    qualified_model: str,
    system_prompt: str,
    user_message: str,
    response_model: Type[T],
) -> LlmCallResult[T]:
    """Synchronous body of one structured Instructor call.

    Purpose:
        Encapsulate the common shape of every tailor/trim/reviewer call
        so the public async functions stay one-liners.
    Args:
        qualified_model: `provider/model` identifier.
        system_prompt: System-role instruction for the model.
        user_message: User-role payload (job posting, resume, etc.).
        response_model: Pydantic class the response must validate against.
    Output:
        Returns an `LlmCallResult[T]` carrying the parsed model and the
        token usage triple.
    Raises:
        RuntimeError: When the provider key is missing.
        ValidationError: When Instructor cannot recover a valid response
            after `INSTRUCTOR_MAX_RETRIES` attempts.
    """

    client, bare_model = _build_client(qualified_model)
    parsed, raw_completion = client.responses.create_with_completion(
        model=bare_model,
        response_model=response_model,
        max_retries=INSTRUCTOR_MAX_RETRIES,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    token_usage = _extract_usage(raw_completion)
    cost = _get_cost_provider().compute_cost(bare_model, token_usage)
    logger.debug(
        "LLM call: model={} prompt_tokens={} completion_tokens={} cost=${:.6f} ({})",
        qualified_model,
        token_usage.prompt_tokens,
        token_usage.completion_tokens,
        cost.total_cost_usd,
        cost.source,
    )
    return LlmCallResult(
        parsed=parsed,
        model=qualified_model,
        usage=token_usage,
        cost=cost,
        prompt_tokens=token_usage.prompt_tokens,
        completion_tokens=token_usage.completion_tokens,
        total_tokens=token_usage.prompt_tokens + token_usage.completion_tokens,
    )


async def _structured_call(
    *,
    qualified_model: str,
    system_prompt: str,
    user_message: str,
    response_model: Type[T],
) -> LlmCallResult[T]:
    """Async-safe wrapper that offloads the blocking call to a thread.

    Purpose:
        Instructor's synchronous client wraps the OpenAI HTTP client,
        which blocks. Running it directly inside the FastAPI / worker
        event loop would stall every other coroutine. `asyncio.to_thread`
        keeps the call off the main loop.
    Args:
        qualified_model: `provider/model` identifier.
        system_prompt: System-role instruction for the model.
        user_message: User-role payload.
        response_model: Pydantic class the response must validate against.
    Output:
        Returns an `LlmCallResult[T]`.
    """

    return await asyncio.to_thread(
        _structured_call_sync,
        qualified_model=qualified_model,
        system_prompt=system_prompt,
        user_message=user_message,
        response_model=response_model,
    )


async def call_tailor(user_message: str) -> LlmCallResult[TailorOutput]:
    """Run the tailor stage on one user message.

    Purpose:
        Produce the initial set of bullet edits proposed for the target
        job posting.
    Args:
        user_message: Fully assembled prompt body including job posting,
            candidate profile, and base resume.
    Output:
        Returns an `LlmCallResult[TailorOutput]`.
    """

    return await _structured_call(
        qualified_model=get_tailor_model_name(),
        system_prompt=TAILOR_INSTRUCTION,
        user_message=user_message,
        response_model=TailorOutput,
    )


async def call_trim(user_message: str) -> LlmCallResult[TailorOutput]:
    """Run the page-fit trim stage on one user message.

    Purpose:
        Shorten an overflowing tailored variant while preserving the
        strongest content.
    Args:
        user_message: Fully assembled prompt body including job posting,
            the overflowing resume, and the measured page count.
    Output:
        Returns an `LlmCallResult[TailorOutput]`.
    """

    return await _structured_call(
        qualified_model=get_tailor_model_name(),
        system_prompt=TRIM_INSTRUCTION,
        user_message=user_message,
        response_model=TailorOutput,
    )


async def call_reviewer(user_message: str) -> LlmCallResult[ReviewerOutput]:
    """Run the reviewer stage on one user message.

    Purpose:
        Score base + tailored variants and pick the strongest one for
        the target job. Supports both 2-way and 3-way comparisons via
        the assembled prompt content.
    Args:
        user_message: Fully assembled prompt body including job posting
            and each resume variant.
    Output:
        Returns an `LlmCallResult[ReviewerOutput]`.
    """

    return await _structured_call(
        qualified_model=get_reviewer_model_name(),
        system_prompt=REVIEWER_INSTRUCTION,
        user_message=user_message,
        response_model=ReviewerOutput,
    )
