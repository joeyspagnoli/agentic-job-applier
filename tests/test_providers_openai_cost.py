"""Behavioral tests for cost math on the OpenAI provider.

Verifies the contract laid out in :mod:`src.providers.types`: provider
``compute_cost`` returns a populated :class:`CostBreakdown`, applies the
50% cached-input discount, falls back to ``source="unknown"`` when the
litellm pricing table doesn't know the model, and round-trips through
:class:`CompletionResponse` without losing accounting fields.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.providers.openai_provider import (
    OPENAI_CACHED_INPUT_DISCOUNT,
    OpenAIProvider,
)
from src.providers.types import (
    CompletionResponse,
    CostBreakdown,
    ProviderType,
    TokenUsage,
)


# ---------------------------------------------------------------------------
# compute_cost — happy path with mocked litellm
# ---------------------------------------------------------------------------


def _make_provider() -> OpenAIProvider:
    """Build a provider with a stub API key (no live calls)."""

    return OpenAIProvider(api_key="sk-stub", provider_type=ProviderType.OPENAI)


def test_compute_cost_produces_non_zero_total_for_priced_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A known model name produces non-zero ``total_cost_usd`` and source='computed'."""

    def fake_cost_per_token(
        *, model: str, prompt_tokens: int, completion_tokens: int
    ) -> tuple[float, float]:
        _ = model
        return prompt_tokens * 1.0e-6, completion_tokens * 2.0e-6

    monkeypatch.setattr("litellm.cost_per_token", fake_cost_per_token, raising=True)

    provider = _make_provider()
    usage = TokenUsage(prompt_tokens=1000, completion_tokens=500)

    cost = provider.compute_cost("gpt-5.4-mini", usage)

    assert cost.source == "computed"
    assert cost.total_cost_usd == pytest.approx(1000 * 1.0e-6 + 500 * 2.0e-6)
    assert cost.input_cost_usd == pytest.approx(1000 * 1.0e-6)
    assert cost.output_cost_usd == pytest.approx(500 * 2.0e-6)
    assert cost.cached_input_cost_usd == 0.0


def test_compute_cost_applies_cached_input_discount(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cached input tokens are billed at 50% of the per-token rate."""

    def fake_cost_per_token(
        *, model: str, prompt_tokens: int, completion_tokens: int
    ) -> tuple[float, float]:
        _ = model
        return prompt_tokens * 1.0e-6, completion_tokens * 2.0e-6

    monkeypatch.setattr("litellm.cost_per_token", fake_cost_per_token, raising=True)

    provider = _make_provider()
    usage = TokenUsage(prompt_tokens=1000, completion_tokens=200, cached_input_tokens=400)

    cost = provider.compute_cost("gpt-5.4-mini", usage)

    # billable prompt = 600 tokens → 6e-4
    # completion = 200 tokens → 4e-4
    # cached = 400 tokens at 50% → 400 * 1e-6 * 0.5 = 2e-4
    expected = (600 * 1.0e-6) + (200 * 2.0e-6) + (400 * 1.0e-6 * OPENAI_CACHED_INPUT_DISCOUNT)
    assert cost.total_cost_usd == pytest.approx(expected)
    assert cost.cached_input_cost_usd == pytest.approx(
        400 * 1.0e-6 * OPENAI_CACHED_INPUT_DISCOUNT
    )


def test_compute_cost_falls_back_to_unknown_when_litellm_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A litellm BadRequest yields ``source='unknown'`` with zero totals."""

    def raise_bad_request(
        *, model: str, prompt_tokens: int, completion_tokens: int
    ) -> tuple[float, float]:
        _ = (model, prompt_tokens, completion_tokens)
        raise RuntimeError("BadRequestError: model not in cost map")

    monkeypatch.setattr("litellm.cost_per_token", raise_bad_request, raising=True)

    provider = _make_provider()
    usage = TokenUsage(prompt_tokens=100, completion_tokens=50)

    cost = provider.compute_cost("unknown-model", usage)

    assert cost.source == "unknown"
    assert cost.total_cost_usd == 0.0
    assert cost.input_cost_usd == 0.0
    assert cost.output_cost_usd == 0.0


def test_compute_cost_zero_when_litellm_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """If litellm cannot be imported, compute_cost returns a zero unknown breakdown."""

    import builtins

    real_import = builtins.__import__

    def deny_litellm(name: str, *args: Any, **kwargs: Any) -> object:
        if name.startswith("litellm"):
            raise ImportError("litellm intentionally disabled for this test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny_litellm)

    provider = _make_provider()
    usage = TokenUsage(prompt_tokens=10, completion_tokens=5)

    cost = provider.compute_cost("gpt-5.4-mini", usage)

    assert cost.source == "unknown"
    assert cost.total_cost_usd == 0.0


# ---------------------------------------------------------------------------
# CompletionResponse round-trip through pydantic
# ---------------------------------------------------------------------------


def test_completion_response_round_trips_usage_and_cost() -> None:
    """``model_dump`` → ``model_validate`` preserves token + cost detail."""

    response = CompletionResponse(
        content="hello",
        model="gpt-5.4-mini",
        provider="openai",
        usage=TokenUsage(
            prompt_tokens=120,
            completion_tokens=40,
            cached_input_tokens=20,
            reasoning_tokens=8,
        ),
        cost=CostBreakdown(
            input_cost_usd=0.001,
            output_cost_usd=0.002,
            cached_input_cost_usd=0.0005,
            total_cost_usd=0.0035,
            source="computed",
        ),
    )

    dumped = response.model_dump()
    restored = CompletionResponse.model_validate(dumped)

    assert restored.usage.prompt_tokens == 120
    assert restored.usage.cached_input_tokens == 20
    assert restored.usage.reasoning_tokens == 8
    assert restored.cost.source == "computed"
    assert restored.cost.total_cost_usd == pytest.approx(0.0035)


def test_completion_response_defaults_to_unknown_cost_source() -> None:
    """A response built without an explicit cost defaults to source='unknown'."""

    response = CompletionResponse(
        content="hi",
        model="m",
        provider="p",
        usage=TokenUsage(),
    )

    assert response.cost.source == "unknown"
    assert response.cost.total_cost_usd == 0.0
    assert response.usage.prompt_tokens == 0


# ---------------------------------------------------------------------------
# TokenUsage parsing (used by complete()) — values are non-negative
# ---------------------------------------------------------------------------


def test_token_usage_rejects_negative_counts() -> None:
    """Pydantic constraints forbid negative token counts on every field."""

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TokenUsage(prompt_tokens=-1)
    with pytest.raises(ValidationError):
        TokenUsage(cached_input_tokens=-5)
