"""Pydantic AI agent factory for the apply finisher.

Wires the model, system prompt, tool catalog, and the
``ToolOutput(FinisherResult)`` output tool. The runner drives the
agent loop via ``agent.iter()`` so it can accumulate per-turn cost
without relying on ``Agent.run()``.

Two settings are load-bearing for gpt-5.4-mini, per the research in
``.research/gpt-5.4-mini-prompting/findings.md``:

- ``openai_reasoning_effort="high"`` — gpt-5.4-mini inherits gpt-5.2's
  ``"none"`` default (zero deliberation), which OpenAI's own
  troubleshooting guide identifies as the canonical cause of
  verification skipping and pattern collapse. ``"high"`` is the
  single biggest expected win.
- ``parallel_tool_calls=False`` — the DOM mutates after every browser
  interaction, so any plan the model builds against an old snapshot
  is invalid by the second concurrent call. The CLI lock in
  ``browser_cli.py`` is a runtime backstop; this setting eliminates
  the failure mode at the source by limiting the model to one tool
  call per assistant turn.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModelSettings
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
FINISHER_MODEL_NAME: str = "openai:gpt-5.4-mini"

# Retries inside individual tool calls. ``ModelRetry`` raised from a
# tool body counts against this budget.
FINISHER_AGENT_RETRIES: int = 2


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
    settings = OpenAIChatModelSettings(
        openai_reasoning_effort="high",
        parallel_tool_calls=False,
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


__all__ = ["FINISHER_AGENT_RETRIES", "FINISHER_MODEL_NAME", "build_finisher_agent"]
