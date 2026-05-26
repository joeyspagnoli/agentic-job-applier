"""Pydantic AI agent factory for the apply finisher.

Wires the model, system prompt, tool catalog, and the
``ToolOutput(FinisherResult)`` output tool. The runner drives the
agent loop via ``agent.iter()`` so it can accumulate per-turn cost
without relying on ``Agent.run()``.

Four settings are load-bearing for gpt-5.4:

- ``openai_reasoning_effort="medium"`` — the fill_combobox helper
  collapses each combobox to ONE tool call, and previous_response_id
  chaining removes the per-turn message-history payload, so each turn
  has room for ~1K reasoning tokens without re-tripping the 200K TPM
  ceiling that "high" used to hit. "low" was tried in an earlier
  iteration to stay under TPM but proved insufficient: gpt-5.4 needs
  enough deliberation to actually run the verify-after-pick rule
  rather than skipping it.
- ``parallel_tool_calls=False`` — the DOM mutates after every browser
  interaction, so any plan the model builds against an old snapshot
  is invalid by the second concurrent call. The CLI lock in
  ``browser_cli.py`` is a runtime backstop; this setting eliminates
  the failure mode at the source by limiting the model to one tool
  call per assistant turn.
- ``openai_previous_response_id="auto"`` — by default Pydantic AI
  resends the full accumulated message history every turn. On a
  ~40-turn form that grows quadratically and is the single biggest
  contributor to TPM exhaustion. ``"auto"`` makes Pydantic AI chain
  via the Responses API's stored ``previous_response_id`` so each turn
  sends only the new tool result; prior context is reconstructed
  server-side. Requires ``openai_store=True`` (the OpenAI default).
- ``openai_prompt_cache_key="apply_finisher_vN"`` — marks the system
  prompt + tool catalog as a stable cache prefix for OpenAI's
  automatic prefix caching. Even with response-id chaining the first
  turn of every run replays the full prompt; caching makes that
  cheap. Bump the suffix when the prompt or tool catalog changes
  materially so a stale cache prefix isn't reused.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai.output import ToolOutput

from src.agents.apply_finisher.prompts import build_system_prompt
from src.agents.apply_finisher.schemas import (
    FinisherDeps,
    FinisherResult,
    SupportedAts,
)
from src.agents.apply_finisher.tools import FINISHER_TOOLS

# Pin the finisher model. gpt-5.4-mini outscores gpt-5-mini by ~1.7x
# on OSWorld-Verified (72.1 vs 42.0); the cost delta is small enough
# to absorb inside the per-apply soft cap.
#
# The ``openai-responses:`` prefix is REQUIRED — gpt-5.4-mini rejects
# function tools combined with reasoning_effort on /v1/chat/completions
# with: "Function tools with reasoning_effort are not supported for
# gpt-5.4-mini in /v1/chat/completions. Please use /v1/responses
# instead." The bare ``openai:`` prefix still routes to Chat
# Completions in pydantic-ai 1.x.
FINISHER_MODEL_NAME: str = "openai-responses:gpt-5.4"

# Retries inside individual tool calls. ``ModelRetry`` raised from a
# tool body counts against this budget.
FINISHER_AGENT_RETRIES: int = 2

# Stable identifier passed to OpenAI's prompt_cache_key so the system
# prompt + tool catalog prefix is reused across runs. Bump the suffix
# when the prompt or tool catalog changes materially — a stale cache
# prefix would otherwise be reused against an incompatible new prompt.
FINISHER_PROMPT_CACHE_KEY: str = "apply_finisher_v4"


def build_finisher_agent(ats: SupportedAts) -> Agent[FinisherDeps, FinisherResult]:
    """Build a finisher agent specialized for one ATS dialect.

    Purpose:
        Centralize agent assembly so the runner stays orthogonal to
        per-ATS prompt swaps. The agent is stateless between runs;
        callers should build one per ``apply_run`` to avoid leaking
        ``FinisherDeps`` across applications.
    Args:
        ats: One of ``"greenhouse"`` or ``"ashby"``.
    Returns:
        Configured ``Agent`` with the narrow tools registered and
        ``complete_apply`` as the output tool.
    """

    system_prompt = build_system_prompt(ats)
    # See module docstring for the rationale on each setting. The two
    # token-discipline knobs (previous_response_id + prompt_cache_key)
    # are what keep a ~40-turn run inside the 200K TPM ceiling on
    # gpt-5.4.
    settings = OpenAIResponsesModelSettings(
        openai_reasoning_effort="medium",
        parallel_tool_calls=False,
        openai_previous_response_id="auto",
        openai_prompt_cache_key=FINISHER_PROMPT_CACHE_KEY,
    )

    return Agent(
        FINISHER_MODEL_NAME,
        deps_type=FinisherDeps,
        output_type=ToolOutput(
            FinisherResult,
            name="complete_apply",
            description=(
                "Call exactly once when every required field is verified "
                "filled-or-deferred. Terminates the run with the final "
                "FinisherResult."
            ),
        ),
        system_prompt=system_prompt,
        tools=list(FINISHER_TOOLS),
        retries=FINISHER_AGENT_RETRIES,
        model_settings=settings,
    )


__all__ = [
    "FINISHER_AGENT_RETRIES",
    "FINISHER_MODEL_NAME",
    "FINISHER_PROMPT_CACHE_KEY",
    "build_finisher_agent",
]
