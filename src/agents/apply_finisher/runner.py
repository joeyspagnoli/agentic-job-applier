"""Orchestrate one apply-finisher run via ``agent.iter()``.

``run_finisher`` is the single entry point the apply worker calls
once Simplify autofill has settled. It owns:

- Building ``FinisherDeps`` (page, profile YAML, defer rules, cache).
- Driving the Pydantic AI agent loop with ``UsageLimits``.
- Accumulating per-turn USD cost from ``RunUsage`` deltas using
  ``litellm.cost_per_token`` (same pricing path the provider uses).
- Synthesizing the final ``FinisherResult`` even on usage-limit /
  runtime-error outcomes so the worker always gets a structured
  payload to persist into ``finisher_diagnostics_json``.

The runner does NOT click submit, does NOT navigate, and does NOT
mutate the candidate profile or answer cache. Those are worker
responsibilities (the worker may call ``cache.append_entry`` after
the human approves a Tier-2 draft).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal

from loguru import logger
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import RunUsage, UsageLimits

FinisherOutcome = Literal[
    "COMPLETE", "AGENT_GAVE_UP", "USAGE_LIMIT_HIT", "RUNTIME_ERROR"
]

from src.agents.apply_finisher.agent import FINISHER_MODEL_NAME, build_finisher_agent
from src.agents.apply_finisher.schemas import (
    FinisherDeps,
    FinisherResult,
    SupportedAts,
)
from src.providers.types import CompletionResponse, CostBreakdown, TokenUsage

if TYPE_CHECKING:  # pragma: no cover - type-only imports
    from playwright.async_api import Page

    from src.agents.apply_finisher.answer_cache import AnswerCache
    from src.agents.apply_finisher.defer_rules import DeferRules

# Hard turn cap on requests + tool calls. Pydantic AI #1987 confirms
# both must be on the ``iter()`` call (passing to ``Agent()`` is a
# silent no-op). Tool-call cap is set higher so a single defer doesn't
# eat a request budget.
_REQUEST_LIMIT: int = 25
_TOOL_CALL_LIMIT: int = 100

# Soft cap; logged only. Sub-agent D's analysis shows the realistic
# cost band is $0.10-$0.20/apply — aborting at $0.05 (the user's
# earlier number) would interrupt every single run. The worker can
# tighten or relax via a future env knob if needed.
_SOFT_COST_CAP_USD: float = 0.20

# Form-root selectors per ATS. Greenhouse renders the application
# under ``#application-form`` on job-boards.greenhouse.io (the current
# React UI). The legacy ``boards.greenhouse.io`` used ``#application_form``
# (underscore) — both are accepted via a comma-joined selector so the
# finisher works against either host without an ATS sub-dispatch.
# Ashby renders one form on the page.
_FORM_ROOT_BY_ATS: Mapping[SupportedAts, str] = {
    "greenhouse": "#application-form, #application_form",
    "ashby": "form",
}


def _build_initial_prompt(
    *,
    target_company: str,
    target_role: str,
    profile_yaml: str,
    job_description_excerpt: str,
) -> str:
    """Assemble the user-role prompt that kicks off the finisher loop.

    Args:
        target_company: Company name extracted from the job posting.
        target_role: Role / title from the posting.
        profile_yaml: Pre-serialized candidate profile YAML.
        job_description_excerpt: Trimmed JD body (≤ ~1500 tokens).
    Returns:
        The user-role message to pass to ``agent.iter()``.
    """

    return (
        f"You are filling the application form for {target_role!r} at "
        f"{target_company!r}. Begin with get_snapshot() to see the form, "
        "then iterate through unfilled required fields per the tier model "
        "in the system prompt. End with complete_apply.\n\n"
        "## Candidate profile (YAML)\n```yaml\n"
        f"{profile_yaml}\n```\n\n"
        "## Job description (excerpt)\n"
        f"{job_description_excerpt}"
    )


def _token_usage_from_run_usage(usage: RunUsage) -> TokenUsage:
    """Convert a Pydantic AI ``RunUsage`` into the canonical ``TokenUsage``.

    Args:
        usage: Cumulative usage snapshot from ``agent_run.usage``.
    Returns:
        Token counts in the project's standard ``TokenUsage`` shape so
        the central cost recorder receives the same payload providers
        emit. Reasoning tokens stay at zero because ``RunUsage`` does
        not surface them as a separate field.
    """

    return TokenUsage(
        prompt_tokens=max(int(usage.input_tokens or 0), 0),
        completion_tokens=max(int(usage.output_tokens or 0), 0),
        cached_input_tokens=max(int(usage.cache_read_tokens or 0), 0),
    )


def _compute_cost_breakdown(usage: TokenUsage, model: str) -> CostBreakdown:
    """Compute the full ``CostBreakdown`` from token counts.

    Mirrors ``OpenAIProvider.compute_cost`` so the recorder receives the
    same input/output/cached split that the gate, tailor, and reviewer
    stages emit. Uses ``litellm.cost_per_token`` which honors the
    authoritative per-model prices registered in
    ``src/utils/llm_pricing.py`` at app startup.

    Args:
        usage: Token counts already split into prompt / completion /
            cached buckets.
        model: Bare model identifier (e.g. ``"gpt-5.4-mini"``).
    Returns:
        Populated ``CostBreakdown`` with ``source="computed"`` on
        success, or ``source="unknown"`` (all zeros) when pricing for
        the model is unavailable.
    """

    try:
        from litellm import cost_per_token
    except ImportError:  # pragma: no cover - litellm is a pinned dep
        return CostBreakdown(source="unknown")

    billable_prompt = max(usage.prompt_tokens - usage.cached_input_tokens, 0)

    try:
        prompt_cost, completion_cost = cost_per_token(
            model=model,
            prompt_tokens=billable_prompt,
            completion_tokens=usage.completion_tokens,
        )
    except Exception as exc:  # pragma: no cover - unknown-model fallback
        logger.debug("cost_per_token failed for {}: {}", model, exc)
        return CostBreakdown(source="unknown")

    cached_cost = 0.0
    if usage.cached_input_tokens > 0:
        try:
            cached_prompt_cost, _ = cost_per_token(
                model=model,
                prompt_tokens=usage.cached_input_tokens,
                completion_tokens=0,
            )
            # OpenAI bills cached input at 50% of the standard prompt rate.
            cached_cost = float(cached_prompt_cost) * 0.5
        except Exception:  # pragma: no cover
            cached_cost = 0.0

    input_cost = float(prompt_cost)
    output_cost = float(completion_cost)
    return CostBreakdown(
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        cached_input_cost_usd=cached_cost,
        total_cost_usd=input_cost + output_cost + cached_cost,
        source="computed",
    )


def _accumulated_cost_usd(usage: RunUsage, model: str) -> float:
    """Compute cumulative USD cost from a ``RunUsage`` snapshot.

    Thin wrapper over :func:`_compute_cost_breakdown` kept for the
    in-loop soft-cap path which only needs the total. Tests
    monkeypatch this symbol to inject deterministic per-turn costs.

    Args:
        usage: Cumulative usage snapshot from ``agent_run.usage``.
        model: Bare model identifier (e.g. ``"gpt-5.4-mini"``).
    Returns:
        Total USD cost so far in the run. Returns ``0.0`` when
        pricing data is unavailable.
    """

    return _compute_cost_breakdown(
        _token_usage_from_run_usage(usage), model
    ).total_cost_usd


async def _record_finisher_cost(
    *,
    apply_run_id: int,
    final_usage: RunUsage,
    model: str,
    finisher_outcome: FinisherOutcome,
) -> None:
    """Persist one ``cost_events`` row for this finisher run.

    Purpose:
        Close the cost-tracking gap that left the Monthly Budget widget
        and ``/api/costs/by-stage`` underreporting apply spend by 100%.
        Opens its own short-lived ``DatabaseManager`` so the runner stays
        decoupled from whichever connection the worker holds. Best-effort:
        cost recording is observational and must never fail an apply run.
    Args:
        apply_run_id: ``apply_runs.id`` for this run; serialized to the
            ``cost_events.run_id`` column.
        final_usage: Cumulative ``RunUsage`` from the completed (or
            aborted) agent loop.
        model: Bare model identifier passed to litellm.
        finisher_outcome: Terminal outcome recorded into the cost-event
            metadata for analytics.
    Returns:
        ``None`` after writing the cost event (or swallowing any error).
    """

    # Late imports keep the test path that monkeypatches the runner
    # symbols off the import-time critical path.
    from src.database.db_manager import DatabaseManager  # noqa: PLC0415
    from src.utils.cost_tracking import (  # noqa: PLC0415
        PIPELINE_STAGE_APPLY,
        record_llm_call_cost,
    )
    from src.utils.paths import resolve_database_path  # noqa: PLC0415

    try:
        token_usage = _token_usage_from_run_usage(final_usage)
        cost_breakdown = _compute_cost_breakdown(token_usage, model)
        response = CompletionResponse(
            content="",
            model=model,
            provider="openai",
            usage=token_usage,
            cost=cost_breakdown,
        )

        db_path = str(resolve_database_path())
        async with DatabaseManager(db_path) as db:
            await db.create_tables()
            await record_llm_call_cost(
                db=db,
                stage=PIPELINE_STAGE_APPLY,
                run_id=str(apply_run_id),
                phase="finisher",
                response=response,
                extra_metadata={"finisher_outcome": finisher_outcome},
            )
    except Exception as exc:
        logger.warning(
            "finisher cost recording failed for apply_run_id={}: {}",
            apply_run_id,
            exc,
        )


def _materialize_result(
    *,
    base: FinisherResult | None,
    deps: FinisherDeps,
    turns_used: int,
    cost_usd: float,
    fallback_outcome: FinisherOutcome,
) -> FinisherResult:
    """Stamp the finisher result with runner-owned bookkeeping.

    Purpose:
        The model emits ``base`` via the ``complete_apply`` output
        tool. The runner overlays accumulators that live outside the
        model's view (turns, cost, the deferral / draft lists). When
        the model never reaches ``complete_apply`` (usage cap hit,
        runtime error) ``base`` is ``None`` and we synthesize a
        result from the deps directly.
    Args:
        base: Model-emitted result, or ``None`` on non-COMPLETE exits.
        deps: Finisher deps with ``recorded_deferrals`` /
            ``drafted_fields`` accumulators.
        turns_used: Request count from ``RunUsage``.
        cost_usd: Cumulative USD cost.
        fallback_outcome: Outcome to stamp when ``base is None``.
    Returns:
        Fully populated ``FinisherResult``.
    """

    deferrals = list(deps.recorded_deferrals)
    drafts = list(deps.drafted_fields)
    has_tier3 = bool(deferrals)
    has_tier2 = bool(drafts)

    if base is None:
        return FinisherResult(
            turns_used=turns_used,
            cost_usd=cost_usd,
            fields_filled=deps.fields_filled_count,
            fields_deferred=len(deferrals),
            deferred_questions=deferrals,
            drafted_fields_flagged_for_verify=drafts,
            outcome=fallback_outcome,
            all_required_filled=False,
            has_tier3_deferred=has_tier3,
            has_tier2_pending=has_tier2,
            simplify_no_op=False,
        )

    return base.model_copy(
        update={
            "turns_used": turns_used,
            "cost_usd": cost_usd,
            "fields_filled": deps.fields_filled_count or base.fields_filled,
            "fields_deferred": len(deferrals),
            "deferred_questions": deferrals,
            "drafted_fields_flagged_for_verify": drafts,
            "has_tier3_deferred": has_tier3,
            "has_tier2_pending": has_tier2,
        }
    )


async def run_finisher(
    *,
    page: "Page",
    ats: SupportedAts,
    target_company: str,
    target_role: str,
    profile_yaml: str,
    job_description_excerpt: str,
    defer_rules: "DeferRules",
    cache: "AnswerCache",
    apply_run_id: int | None = None,
) -> FinisherResult:
    """Drive one full finisher run end-to-end.

    Purpose:
        Single function the apply worker awaits after Simplify
        autofill settles. Owns the agent loop, cost accumulation,
        usage-limit handling, and final result synthesis.
    Args:
        page: Playwright async ``Page`` attached to the open form.
        ats: ``"greenhouse"`` or ``"ashby"``.
        target_company: Company name (used for ``$COMPANY`` substitution).
        target_role: Role title displayed in the kickoff prompt.
        profile_yaml: Pre-serialized candidate profile YAML.
        job_description_excerpt: Trimmed JD body (≤ 1500 tokens).
        defer_rules: Loaded defer-rule classifier.
        cache: Loaded answer cache.
        apply_run_id: ``apply_runs.id`` for this run. When provided, the
            runner persists a ``cost_events`` row tagged
            ``stage=APPLY, phase=finisher`` so dashboard analytics
            attribute finisher spend correctly. Passing ``None`` (the
            default) is the test / standalone-script path.
    Returns:
        Populated ``FinisherResult``. ``outcome="COMPLETE"`` is the
        only state in which the gate may auto-submit.
    """

    deps = FinisherDeps(
        page=page,
        ats=ats,
        target_company=target_company,
        defer_rules=defer_rules,
        cache=cache,
        profile_yaml=profile_yaml,
        form_root_selector=_FORM_ROOT_BY_ATS[ats],
    )

    agent = build_finisher_agent(ats)
    user_prompt = _build_initial_prompt(
        target_company=target_company,
        target_role=target_role,
        profile_yaml=profile_yaml,
        job_description_excerpt=job_description_excerpt,
    )
    usage_limits = UsageLimits(
        request_limit=_REQUEST_LIMIT,
        tool_calls_limit=_TOOL_CALL_LIMIT,
    )

    # Strip "openai:" prefix for litellm; it expects the bare model name.
    bare_model_for_pricing = FINISHER_MODEL_NAME.split(":", 1)[-1]

    accumulated_cost: float = 0.0
    soft_cap_logged: bool = False
    turns_used: int = 0
    output_result: FinisherResult | None = None
    fallback_outcome: FinisherOutcome = "RUNTIME_ERROR"
    final_usage: RunUsage = RunUsage()

    try:
        async with agent.iter(
            user_prompt,
            deps=deps,
            usage_limits=usage_limits,
        ) as agent_run:
            async for _node in agent_run:
                usage = agent_run.usage
                turns_used = int(usage.requests or 0)
                final_usage = usage
                accumulated_cost = _accumulated_cost_usd(usage, bare_model_for_pricing)
                if (
                    accumulated_cost > _SOFT_COST_CAP_USD
                    and not soft_cap_logged
                ):
                    logger.warning(
                        "finisher soft cost cap exceeded: ${:.4f} > ${:.4f} "
                        "(continuing — cap is log-only)",
                        accumulated_cost,
                        _SOFT_COST_CAP_USD,
                    )
                    soft_cap_logged = True

            run_output = agent_run.result.output if agent_run.result else None
            if isinstance(run_output, FinisherResult):
                output_result = run_output
                fallback_outcome = "COMPLETE"
    except UsageLimitExceeded as exc:
        logger.warning(
            "finisher hit usage limit after {} turns: {}",
            turns_used,
            exc,
        )
        fallback_outcome = "USAGE_LIMIT_HIT"
    except Exception as exc:
        logger.exception("finisher runtime error after {} turns: {}", turns_used, exc)
        fallback_outcome = "RUNTIME_ERROR"

    if apply_run_id is not None:
        await _record_finisher_cost(
            apply_run_id=apply_run_id,
            final_usage=final_usage,
            model=bare_model_for_pricing,
            finisher_outcome=fallback_outcome,
        )

    return _materialize_result(
        base=output_result,
        deps=deps,
        turns_used=turns_used,
        cost_usd=accumulated_cost,
        fallback_outcome=fallback_outcome,
    )


__all__ = ["run_finisher"]
