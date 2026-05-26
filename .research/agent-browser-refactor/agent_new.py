"""Pydantic AI agent factory for the apply finisher (agent-browser edition).

Identical construction pattern to the current agent.py — Agent(...) with
tools=list(FINISHER_TOOLS) and ToolOutput(FinisherResult) as the output
tool. The only diff: FINISHER_TOOLS now points at the CLI-backed tools.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.output import ToolOutput

from src.agents.apply_finisher.prompts import build_system_prompt
from src.agents.apply_finisher.schemas import (
    FinisherDeps,
    FinisherResult,
    SupportedAts,
)
from src.agents.apply_finisher.tools import FINISHER_TOOLS

FINISHER_MODEL_NAME: str = "openai:gpt-5.4-mini"
FINISHER_AGENT_RETRIES: int = 2


def build_finisher_agent(ats: SupportedAts) -> Agent[FinisherDeps, FinisherResult]:
    """Build a finisher agent specialized for one ATS dialect.

    Args:
        ats: One of ``"greenhouse"`` or ``"ashby"``.
    Returns:
        Configured ``Agent`` with CLI-backed tools registered and
        ``complete_apply`` as the output tool.
    """

    system_prompt = build_system_prompt(ats)

    return Agent(
        FINISHER_MODEL_NAME,
        deps_type=FinisherDeps,
        output_type=ToolOutput(
            FinisherResult,
            name="complete_apply",
            description=(
                "Call exactly once when every required field is filled or "
                "deferred. Terminates the run with the final FinisherResult."
            ),
        ),
        system_prompt=system_prompt,
        tools=list(FINISHER_TOOLS),
        retries=FINISHER_AGENT_RETRIES,
    )


__all__ = ["FINISHER_AGENT_RETRIES", "FINISHER_MODEL_NAME", "build_finisher_agent"]
