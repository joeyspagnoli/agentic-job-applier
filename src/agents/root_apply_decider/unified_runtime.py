"""Unified provider runtime for the gate decider.

Replaces the ADK-specific runtime with the provider-agnostic abstraction.
All pipeline stages can now use any configured provider (Codex, OpenAI,
Anthropic, Gemini) through the same interface.
"""

from __future__ import annotations

from collections.abc import Mapping

from loguru import logger

from src.providers.types import AIProvider, CompletionMessage, CompletionRequest

from .agent import parse_gate_response
from .prompts import ROOT_APPLY_DECIDER_INSTRUCTION, build_gate_payload
from .schemas import ApplyDecision, GateRunResult


def map_decision_to_status(decision: ApplyDecision) -> str:
    """Translate an agent decision into the stored workflow status.

    Args:
        decision: Apply/skip decision returned by the gate.

    Returns:
        'QUALIFIED' for apply decisions, 'FILTERED' for skip decisions.
    """
    return "QUALIFIED" if decision == ApplyDecision.APPLY else "FILTERED"


async def run_gate_with_provider(
    *,
    provider: AIProvider,
    job: Mapping[str, object],
) -> GateRunResult:
    """Run the gate decision using the unified AI provider.

    Sends the system instruction and job payload as a chat completion
    request through whatever provider the user has configured.

    Args:
        provider: Configured AI provider instance.
        job: Database row representing the job being evaluated.

    Returns:
        A validated GateRunResult with the decision and metadata.

    Raises:
        ValueError: When the model response cannot be parsed into a decision.
        ProviderError: When the AI provider call fails.
    """
    payload_text = build_gate_payload(job)

    request = CompletionRequest(
        messages=[
            CompletionMessage(role="system", content=ROOT_APPLY_DECIDER_INSTRUCTION),
            CompletionMessage(role="user", content=payload_text),
        ],
        temperature=0.1,
        max_tokens=1024,
        response_format="json",
    )

    response = await provider.complete(request)

    logger.debug(
        "Gate completion: provider={} model={} tokens={}+{}",
        response.provider,
        response.model,
        response.usage_prompt_tokens,
        response.usage_completion_tokens,
    )

    return parse_gate_response(
        response.content,
        provider=response.provider,
        model=response.model,
    )
