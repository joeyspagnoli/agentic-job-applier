"""Agent and parser utilities for the root apply-decider package."""

from __future__ import annotations

import json
from typing import Any
from typing import Mapping

from google.adk.agents import Agent

from src.agents.shared import build_openai_litellm_model

from .prompts import ROOT_APPLY_DECIDER_INSTRUCTION
from .schemas import ApplyDecision
from .schemas import GateDebugInfo
from .schemas import GateRunResult

DECIDER_PROVIDER = "openai"
DECIDER_MODEL = "openai/gpt-5.1-codex-mini"


def _extract_decision(value: Any) -> ApplyDecision | None:
    """Normalize a raw value into `APPLY` or `SKIP`.

    Purpose:
        Accept common casing and spacing differences from model output while
        keeping persisted results constrained to the enum values.
    Args:
        value: Raw value from parsed JSON or text-recovery logic.
    Output:
        Returns an `ApplyDecision` when conversion succeeds, otherwise `None`.
    """

    if not isinstance(value, str):
        return None

    normalized = value.strip().upper()
    if normalized == ApplyDecision.APPLY.value:
        return ApplyDecision.APPLY
    if normalized == ApplyDecision.SKIP.value:
        return ApplyDecision.SKIP
    return None


def _extract_first_json_object(raw_response: str) -> dict[str, Any] | None:
    """Recover the first JSON object embedded in a model response.

    Purpose:
        Support parse recovery when providers return extra tokens before or
        after the JSON object that contains the decision payload.
    Args:
        raw_response: Full raw text emitted by the model.
    Output:
        Returns the first parsed JSON object, or `None` when not recoverable.
    """

    response_text = raw_response.strip()
    if not response_text:
        return None

    try:
        parsed = json.loads(response_text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for start_index, character in enumerate(response_text):
        if character != "{":
            continue

        try:
            parsed, _ = decoder.raw_decode(response_text[start_index:])
        except json.JSONDecodeError:
            continue

        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_debug_info(parsed_json: Mapping[str, Any]) -> GateDebugInfo:
    """Build optional debug fields from a recovered JSON payload.

    Purpose:
        Keep extra reasoning metadata when available while allowing decisions
        to persist even when optional fields are absent.
    Args:
        parsed_json: Parsed JSON object recovered from model output.
    Output:
        Returns a populated `GateDebugInfo` object.
    """

    return GateDebugInfo(
        confidence=parsed_json.get("confidence"),
        explanation=parsed_json.get("explanation"),
        preference_matches=list(parsed_json.get("preference_matches") or []),
        preference_conflicts=list(parsed_json.get("preference_conflicts") or []),
    )


def parse_gate_response(
    raw_response: str,
    *,
    provider: str,
    model: str,
) -> GateRunResult:
    """Parse raw model text into a durable gate run payload.

    Purpose:
        Parse a structured JSON decision payload and reject malformed text-only
        responses so final verdicts remain model-authored and schema-backed.
    Args:
        raw_response: Full raw text returned by the model.
        provider: Provider label to persist with the result metadata.
        model: Concrete model string to persist with the result metadata.
    Output:
        Returns a validated `GateRunResult` or raises `ValueError` when no
        APPLY/SKIP decision can be recovered.
    """

    parsed_json = _extract_first_json_object(raw_response)
    if parsed_json is None:
        raise ValueError(
            "Could not recover a JSON object containing `decision` from model response"
        )

    decision = _extract_decision(parsed_json.get("decision"))
    if decision is None:
        raise ValueError(
            "Recovered JSON response did not contain valid decision APPLY or SKIP"
        )

    return GateRunResult(
        decision=decision,
        debug=_extract_debug_info(parsed_json),
        raw_response=raw_response,
        provider=provider,
        model=model,
        parse_mode="json_recovered",
    )


def get_decider_provider() -> str:
    """Return the fixed provider used by the root apply-decider.

    Purpose:
        Keep one source of truth for provider metadata used in logs and stored
        run payloads.
    Args:
        None.
    Output:
        Returns the provider string `openai`.
    """

    return DECIDER_PROVIDER


def get_decider_model_name() -> str:
    """Return the fixed model used by the root apply-decider.

    Purpose:
        Keep one source of truth for the concrete model identifier used by the
        decider's model-construction and run metadata paths.
    Args:
        None.
    Output:
        Returns the fully qualified model string `openai/gpt-5.1-codex-mini`.
    """

    return DECIDER_MODEL


def get_decider_model() -> Any:
    """Build the configured model implementation for the decider.

    Purpose:
        Provide the ADK-compatible model object required by scripts while
        keeping credential checks and LiteLLM wiring centralized.
    Args:
        None.
    Output:
        Returns a configured model object compatible with ADK.
    """

    return build_openai_litellm_model(
        model_name=get_decider_model_name(),
    )


def build_root_agent(*, model: Any | None = None) -> Agent:
    """Build the single-purpose apply/skip gate agent.

    Purpose:
        Assemble the root decider with its fixed instruction and optionally
        injected model object for testing or runtime use.
    Args:
        model: Optional model implementation to attach to the ADK agent.
    Output:
        Returns a configured `google.adk.agents.Agent`.
    """

    effective_model = model if model is not None else ""
    return Agent(
        name="root_apply_decider",
        description="Decides whether to APPLY or SKIP a normalized job posting.",
        model=effective_model,
        instruction=ROOT_APPLY_DECIDER_INSTRUCTION,
    )
