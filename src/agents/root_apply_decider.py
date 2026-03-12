"""ADK agent that decides whether to apply for a job.

The agent is designed to be importable without any model credentials.
Consumers should either:
- Inject a configured ADK model via :func:`build_root_agent`, or
- Implement :func:`get_decider_model`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from google.adk.agents import Agent
from pydantic import BaseModel, Field


class ApplyDecision(str, Enum):
    APPLY = "APPLY"
    SKIP = "SKIP"


class RootApplyDeciderOutput(BaseModel):
    """Structured output from the root apply decider agent."""

    decision: ApplyDecision = Field(
        description="Whether the candidate should apply or skip this job.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score from 0 to 1.",
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Short, concrete reasons for the decision.",
    )
    matched_skills: list[str] = Field(
        default_factory=list,
        description="Skills/keywords present in both profile and job.",
    )
    missing_skills: list[str] = Field(
        default_factory=list,
        description="Important job requirements missing from the profile.",
    )


DECIDER_OUTPUT_KEY = "root_apply_decider"


def get_decider_model() -> Any:
    """Return a configured ADK model.

    This is intentionally a stub to avoid hardcoding credentials.

    Suggested wiring pattern:
    - Copy the approach in `refs/test_architect/models.py` (LiteLlm or Gemini)
    - Read provider keys from environment variables
    - Return an instance of `google.adk.models.base_llm.BaseLlm`
    """

    raise RuntimeError(
        "Decider model not configured. "
        "Inject a model via build_root_agent(model=...) or implement "
        "src.agents.root_apply_decider.get_decider_model(). "
        "See refs/test_architect/models.py for an example of wiring LiteLlm/Gemini "
        "from environment variables."
    )


def build_root_agent(*, model: Any | None = None) -> Agent:
    """Create the RootApplyDecider agent with an optional injected model."""

    effective_model = model if model is not None else ""

    return Agent(
        name="root_apply_decider",
        description="Decides whether to APPLY or SKIP a job posting for a candidate.",
        model=effective_model,
        instruction=(
            "You are a job application decider.\n"
            "Compare the job posting against the candidate profile.\n\n"
            "Rules:\n"
            "- Decide APPLY only if the candidate matches the role well.\n"
            "- Decide SKIP if the role is clearly misaligned or requirements are missing.\n"
            "- Extract matched skills/keywords and missing requirements.\n"
            "- Be conservative: prefer SKIP when uncertain.\n\n"
            "IMPORTANT: Respond with ONLY valid JSON matching this schema:\n"
            "{\n"
            '  "decision": "APPLY" | "SKIP",\n'
            '  "confidence": 0.0,\n'
            '  "reasons": ["..."],\n'
            '  "matched_skills": ["..."],\n'
            '  "missing_skills": ["..."]\n'
            "}\n"
            "No extra text."
        ),
        output_schema=RootApplyDeciderOutput,
        output_key=DECIDER_OUTPUT_KEY,
    )


# Intentionally do not export a default Agent instance.
# Without an actual model wired, exporting a global `root_agent` encourages
# consumers to accidentally run an unusable agent.
