"""Tests for the finisher runner — cost accounting, gate signals, and exits.

Exercises three layers without spinning up a live LLM:

* The pure pricing helper (``_accumulated_cost_usd``) against a stubbed
  ``litellm.cost_per_token`` so the per-turn delta math is locked in.
* The result-synthesis helper (``_materialize_result``) so every public
  field on :class:`FinisherResult` is populated correctly for both the
  COMPLETE and fallback-outcome branches.
* The full :func:`run_finisher` entry point with a Pydantic AI
  ``FunctionModel`` driving the loop deterministically. This catches
  regressions in how the runner builds the prompt, attaches the
  ``UsageLimits``, and pulls the final ``FinisherResult`` out of
  ``agent_run.result.output``.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.output import ToolOutput
from pydantic_ai.usage import RunUsage

from src.agents.apply_finisher.answer_cache import AnswerCache
from src.agents.apply_finisher.defer_rules import DeferRules
from src.agents.apply_finisher.runner import (
    _accumulated_cost_usd,
    _build_initial_prompt,
    _materialize_result,
    run_finisher,
)
from src.agents.apply_finisher.schemas import (
    DeferredQuestion,
    DraftedField,
    FinisherDeps,
    FinisherResult,
)
from tests.helpers.fake_finisher_page import FakeFinisherPage


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_deps() -> FinisherDeps:
    """Build a minimal :class:`FinisherDeps` with empty cache / rules."""

    cache = AnswerCache(_path=__import__("pathlib").Path("/tmp/_runner_cache.yaml"))
    rules = DeferRules(
        _always_defer_patterns=(),
        _draft_and_flag_patterns=(),
        bypass_field_types=frozenset(),
        never_defer_overrides=(),
    )
    return FinisherDeps(
        page=FakeFinisherPage(),  # type: ignore[arg-type]
        ats="greenhouse",
        target_company="Stripe",
        defer_rules=rules,
        cache=cache,
        profile_yaml="profile: {}\n",
        form_root_selector="#application_form",
    )


# ---------------------------------------------------------------------------
# _build_initial_prompt
# ---------------------------------------------------------------------------


def test_build_initial_prompt_embeds_target_company_and_jd_excerpt() -> None:
    """The user-role prompt carries the company, role, profile, and JD excerpt."""

    prompt = _build_initial_prompt(
        target_company="Notion",
        target_role="BDR",
        profile_yaml="profile:\n  name: x\n",
        job_description_excerpt="A short JD body.",
    )

    assert "Notion" in prompt
    assert "BDR" in prompt
    assert "profile:" in prompt
    assert "A short JD body." in prompt


# ---------------------------------------------------------------------------
# _accumulated_cost_usd
# ---------------------------------------------------------------------------


def test_accumulated_cost_combines_prompt_completion_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """The helper sums billable input + completion + cached-discount cost."""

    captured_calls: list[tuple[int, int]] = []

    def fake_cost_per_token(
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> tuple[float, float]:
        """Return deterministic per-call cost for assertions."""

        _ = model
        captured_calls.append((prompt_tokens, completion_tokens))
        # 1 USD per token, predictable.
        return float(prompt_tokens), float(completion_tokens)

    monkeypatch.setitem(__import__("sys").modules, "litellm_stub", MagicMock())
    monkeypatch.setattr(
        "litellm.cost_per_token", fake_cost_per_token, raising=True
    )

    usage = RunUsage(input_tokens=200, output_tokens=50, cache_read_tokens=40)
    total = _accumulated_cost_usd(usage, "gpt-5.4-mini")

    # billable prompt = 200 - 40 = 160, completion = 50, cached = 40 * 0.5 = 20
    assert total == pytest.approx(160.0 + 50.0 + 20.0)
    # Two cost_per_token calls: one for billable+completion, one for cached.
    assert captured_calls == [(160, 50), (40, 0)]


def test_accumulated_cost_returns_zero_on_unknown_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """A litellm BadRequest / unknown-model raise leaves cost at 0.0."""

    def raise_unknown(
        *, model: str, prompt_tokens: int, completion_tokens: int
    ) -> tuple[float, float]:
        _ = (model, prompt_tokens, completion_tokens)
        raise RuntimeError("Model not found")

    monkeypatch.setattr("litellm.cost_per_token", raise_unknown, raising=True)

    usage = RunUsage(input_tokens=100, output_tokens=50)
    total = _accumulated_cost_usd(usage, "unknown-model")

    assert total == 0.0


# ---------------------------------------------------------------------------
# _materialize_result
# ---------------------------------------------------------------------------


def test_materialize_result_falls_back_when_base_is_none() -> None:
    """A ``None`` base produces a synthesized FinisherResult with deferrals."""

    deps = _make_deps()
    deps.recorded_deferrals.append(
        DeferredQuestion(
            field_id="e1", label="Sponsorship?", field_type="select",
            category="sponsorship", reason="Tier 3.",
        )
    )
    deps.fields_filled_count = 3

    result = _materialize_result(
        base=None, deps=deps, turns_used=8, cost_usd=0.123,
        fallback_outcome="USAGE_LIMIT_HIT",
    )

    assert result.outcome == "USAGE_LIMIT_HIT"
    assert result.turns_used == 8
    assert result.cost_usd == pytest.approx(0.123)
    assert result.fields_filled == 3
    assert result.fields_deferred == 1
    assert result.has_tier3_deferred is True
    assert result.has_tier2_pending is False
    assert result.all_required_filled is False


def test_materialize_result_overlays_bookkeeping_on_complete_base() -> None:
    """A model-emitted COMPLETE base gets cost/turns/lists stamped from deps."""

    deps = _make_deps()
    deps.fields_filled_count = 7
    deps.drafted_fields.append(
        DraftedField(
            field_id="e2", label="Why?", drafted_value="...", confidence=0.9,
            reasoning="ok",
        )
    )
    base = FinisherResult(
        outcome="COMPLETE",
        all_required_filled=True,
        fields_filled=5,  # base reported fewer than deps actually saw
    )

    result = _materialize_result(
        base=base, deps=deps, turns_used=12, cost_usd=0.18,
        fallback_outcome="COMPLETE",
    )

    assert result.outcome == "COMPLETE"
    assert result.fields_filled == 7  # deps wins when non-zero
    assert result.turns_used == 12
    assert result.cost_usd == pytest.approx(0.18)
    assert result.has_tier2_pending is True
    assert result.drafted_fields_flagged_for_verify[0].confidence == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# End-to-end run_finisher via FunctionModel
# ---------------------------------------------------------------------------


def _build_test_agent(model: FunctionModel) -> Agent[FinisherDeps, FinisherResult]:
    """Construct an agent identical in shape to ``build_finisher_agent`` but
    using a deterministic :class:`FunctionModel` instead of OpenAI.

    Args:
        model: The deterministic model the test wants to drive the loop.
    Returns:
        An ``Agent`` whose output tool is the same ``complete_apply``
        ``ToolOutput(FinisherResult)``.
    """

    return Agent(
        model,
        deps_type=FinisherDeps,
        output_type=ToolOutput(
            FinisherResult,
            name="complete_apply",
            description="Call once to terminate the run.",
        ),
        system_prompt="test",
        retries=1,
    )


def _finisher_result_args(**overrides: Any) -> dict[str, Any]:
    """Build the arg dict the model emits for ``complete_apply``."""

    base = {
        "turns_used": 0,
        "cost_usd": 0.0,
        "fields_filled": 0,
        "fields_deferred": 0,
        "deferred_questions": [],
        "drafted_fields_flagged_for_verify": [],
        "outcome": "COMPLETE",
        "all_required_filled": True,
        "has_tier3_deferred": False,
        "has_tier2_pending": False,
        "simplify_no_op": False,
    }
    base.update(overrides)
    return base


def test_run_finisher_completes_when_model_emits_complete_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single-turn model that calls complete_apply lands outcome=COMPLETE."""

    def driver(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        _ = (messages, info)
        return ModelResponse(parts=[
            ToolCallPart(
                tool_name="complete_apply",
                args=_finisher_result_args(fields_filled=4),
            )
        ])

    model = FunctionModel(driver, model_name="test-finisher")

    test_agent = _build_test_agent(model)
    monkeypatch.setattr(
        "src.agents.apply_finisher.runner.build_finisher_agent",
        lambda ats: test_agent,
    )
    # Stub the pricing helper so the test doesn't depend on litellm data.
    monkeypatch.setattr(
        "src.agents.apply_finisher.runner._accumulated_cost_usd",
        lambda usage, model: 0.0123,
    )

    result = asyncio.run(
        run_finisher(
            page=FakeFinisherPage(),  # type: ignore[arg-type]
            ats="greenhouse",
            target_company="Stripe",
            target_role="SWE",
            profile_yaml="profile: {}\n",
            job_description_excerpt="A JD.",
            defer_rules=DeferRules(
                _always_defer_patterns=(),
                _draft_and_flag_patterns=(),
                bypass_field_types=frozenset(),
                never_defer_overrides=(),
            ),
            cache=AnswerCache(_path=__import__("pathlib").Path("/tmp/_t.yaml")),
        )
    )

    assert result.outcome == "COMPLETE"
    assert result.cost_usd == pytest.approx(0.0123)
    assert result.all_required_filled is True


def test_run_finisher_returns_runtime_error_when_model_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that raises mid-loop yields outcome=RUNTIME_ERROR."""

    def driver(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        _ = (messages, info)
        raise RuntimeError("boom")

    model = FunctionModel(driver, model_name="raising-model")
    test_agent = _build_test_agent(model)
    monkeypatch.setattr(
        "src.agents.apply_finisher.runner.build_finisher_agent",
        lambda ats: test_agent,
    )
    monkeypatch.setattr(
        "src.agents.apply_finisher.runner._accumulated_cost_usd",
        lambda usage, model: 0.0,
    )

    result = asyncio.run(
        run_finisher(
            page=FakeFinisherPage(),  # type: ignore[arg-type]
            ats="greenhouse",
            target_company="Stripe",
            target_role="SWE",
            profile_yaml="profile: {}\n",
            job_description_excerpt="A JD.",
            defer_rules=DeferRules(
                _always_defer_patterns=(),
                _draft_and_flag_patterns=(),
                bypass_field_types=frozenset(),
                never_defer_overrides=(),
            ),
            cache=AnswerCache(_path=__import__("pathlib").Path("/tmp/_t.yaml")),
        )
    )

    assert result.outcome == "RUNTIME_ERROR"
    assert result.all_required_filled is False


def test_run_finisher_logs_soft_cap_warning_when_cost_exceeds_threshold(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Crossing the $0.20 soft cap emits exactly one warning, then continues."""

    def driver(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        _ = (messages, info)
        return ModelResponse(parts=[
            ToolCallPart(tool_name="complete_apply", args=_finisher_result_args())
        ])

    model = FunctionModel(driver, model_name="cost-cap")
    test_agent = _build_test_agent(model)
    monkeypatch.setattr(
        "src.agents.apply_finisher.runner.build_finisher_agent",
        lambda ats: test_agent,
    )
    # Force cost above the $0.20 soft cap.
    monkeypatch.setattr(
        "src.agents.apply_finisher.runner._accumulated_cost_usd",
        lambda usage, model: 0.50,
    )

    # Configure loguru to propagate to caplog.
    import logging

    from loguru import logger

    class _PropagateHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
            logging.getLogger(record.name).handle(record)

    handler_id = logger.add(_PropagateHandler(), level="WARNING", format="{message}")
    caplog.set_level("WARNING")
    try:
        result = asyncio.run(
            run_finisher(
                page=FakeFinisherPage(),  # type: ignore[arg-type]
                ats="greenhouse",
                target_company="Stripe",
                target_role="SWE",
                profile_yaml="profile: {}\n",
                job_description_excerpt="A JD.",
                defer_rules=DeferRules(
                    _always_defer_patterns=(),
                    _draft_and_flag_patterns=(),
                    bypass_field_types=frozenset(),
                    never_defer_overrides=(),
                ),
                cache=AnswerCache(_path=__import__("pathlib").Path("/tmp/_t.yaml")),
            )
        )
    finally:
        logger.remove(handler_id)

    assert result.outcome == "COMPLETE"
    assert result.cost_usd == pytest.approx(0.50)
    # The runner should have logged the soft-cap warning at least once.
    matching = [r for r in caplog.records if "soft cost cap" in r.getMessage()]
    assert len(matching) >= 1


def test_run_finisher_usage_limit_exceeded_returns_outcome_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ``UsageLimitExceeded`` raised by Pydantic AI lands outcome=USAGE_LIMIT_HIT."""

    # Drive endless requests — never emit complete_apply — so the run
    # hits the runner's request_limit=25 and raises UsageLimitExceeded.
    async def fake_get_snapshot(ctx: RunContext[FinisherDeps]) -> str:
        """A tool that matches the registered name; returns a stub snapshot."""

        _ = ctx
        return "tree"

    def driver(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        _ = (messages, info)
        return ModelResponse(parts=[ToolCallPart(tool_name="fake_get_snapshot", args={})])

    model = FunctionModel(driver, model_name="loop")

    test_agent = Agent(
        model,
        deps_type=FinisherDeps,
        output_type=ToolOutput(
            FinisherResult,
            name="complete_apply",
            description="end the run",
        ),
        system_prompt="test",
        tools=[fake_get_snapshot],
        retries=0,
    )

    monkeypatch.setattr(
        "src.agents.apply_finisher.runner.build_finisher_agent",
        lambda ats: test_agent,
    )
    monkeypatch.setattr(
        "src.agents.apply_finisher.runner._accumulated_cost_usd",
        lambda usage, model: 0.0,
    )

    result = asyncio.run(
        run_finisher(
            page=FakeFinisherPage(),  # type: ignore[arg-type]
            ats="greenhouse",
            target_company="Stripe",
            target_role="SWE",
            profile_yaml="profile: {}\n",
            job_description_excerpt="A JD.",
            defer_rules=DeferRules(
                _always_defer_patterns=(),
                _draft_and_flag_patterns=(),
                bypass_field_types=frozenset(),
                never_defer_overrides=(),
            ),
            cache=AnswerCache(_path=__import__("pathlib").Path("/tmp/_t.yaml")),
        )
    )

    assert result.outcome == "USAGE_LIMIT_HIT"
    assert result.all_required_filled is False
