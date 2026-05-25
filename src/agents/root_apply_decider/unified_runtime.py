"""Unified provider runtime for the gate decider.

Replaces the ADK-specific runtime with the provider-agnostic abstraction.
All pipeline stages can now use any configured provider (Codex, OpenAI,
Anthropic, Gemini) through the same interface.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from loguru import logger

from src.providers.types import AIProvider, CompletionMessage, CompletionRequest, CompletionResponse

from .agent import parse_gate_response
from .prompts import ROOT_APPLY_DECIDER_INSTRUCTION, build_gate_payload
from .schemas import ApplyDecision, GateRunResult


@dataclass(frozen=True)
class GateRunOutcome:
    """Bundle the gate result with the raw provider response for cost recording.

    Attributes:
        result: Parsed gate decision and metadata.
        response: Raw completion response carrying token usage and cost
            breakdown so the caller can persist via `record_llm_call_cost`
            without a second provider round-trip.
    """

    result: GateRunResult
    response: CompletionResponse


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
) -> GateRunOutcome:
    """Run the gate decision using the unified AI provider.

    Sends the system instruction and job payload as a chat completion
    request through whatever provider the user has configured.

    Args:
        provider: Configured AI provider instance.
        job: Database row representing the job being evaluated.

    Returns:
        A `GateRunOutcome` bundling the parsed `GateRunResult` with the
        raw `CompletionResponse` so callers can write accurate cost rows
        via `record_llm_call_cost` without an extra provider round-trip.

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
        "Gate completion: provider={} model={} tokens={}+{} cost=${:.6f}",
        response.provider,
        response.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
        response.cost.total_cost_usd,
    )

    gate_result = parse_gate_response(
        response.content,
        provider=response.provider,
        model=response.model,
    )
    return GateRunOutcome(result=gate_result, response=response)
