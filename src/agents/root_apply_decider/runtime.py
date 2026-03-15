"""Runtime helpers for executing and persisting gate decisions."""

from __future__ import annotations

import uuid
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agent import get_decider_model_name
from .agent import get_decider_provider
from .agent import parse_gate_response
from .prompts import build_gate_payload
from .schemas import ApplyDecision
from .schemas import GateRunResult


def extract_event_text(event: Any) -> str:
    """Pull plain text content out of an ADK event when text is present.

    Purpose:
        Capture the model's final raw response text so the gate can parse and
        persist it locally without depending on ADK structured-output storage.
    Args:
        event: ADK event object yielded by the runner.
    Output:
        Returns the concatenated text content from the event, or an empty
        string when the event carries no plain text parts.
    """

    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None)
    if not parts:
        return ""

    text_parts: list[str] = []
    for part in parts:
        part_text = getattr(part, "text", None)
        if part_text:
            text_parts.append(part_text)
    return "".join(text_parts)


def map_decision_to_status(decision: ApplyDecision) -> str:
    """Translate an agent decision into the stored workflow status.

    Purpose:
        Keep the mapping from gate output to database workflow status in one
        place so CLI scripts persist consistent status values.
    Args:
        decision: Apply/skip decision returned by the gate.
    Output:
        Returns `QUALIFIED` for apply decisions and `FILTERED` for skip decisions.
    """

    return "QUALIFIED" if decision == ApplyDecision.APPLY else "FILTERED"


async def run_decider_for_job(
    *,
    agent: Any,
    job: dict[str, Any],
) -> GateRunResult:
    """Run the ADK decider for one job and parse its raw response locally.

    Purpose:
        Execute one isolated ADK session, capture the model's final text
        response, and turn it into a durable gate result payload.
    Args:
        agent: Configured ADK agent instance to run.
        job: Database row representing the job being evaluated.
    Output:
        Returns a validated `GateRunResult`, or raises an error when the
        decision cannot be recovered from the model response.
    """

    session_service = InMemorySessionService()
    app_name = "job_apply_decider"
    user_id = "worker"
    session_id = str(uuid.uuid4())

    # Each job gets a fresh session so there is no carry-over state from the
    # previous decision in the batch loop.
    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state={},
    )

    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
    final_response_text = ""
    streamed_text_fragments: list[str] = []

    try:
        new_message = types.Content(
            role="user",
            parts=[types.Part(text=build_gate_payload(job))],
        )

        # The loop captures the last full text event when available and falls
        # back to concatenated stream fragments otherwise.
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message,
        ):
            event_text = extract_event_text(event)
            if not event_text:
                continue

            streamed_text_fragments.append(event_text)
            if getattr(event, "partial", False):
                continue

            if hasattr(event, "is_final_response") and event.is_final_response():
                final_response_text = event_text
    finally:
        await runner.close()

    raw_response = final_response_text or "".join(streamed_text_fragments).strip()
    if not raw_response:
        raise RuntimeError("Model returned no text response for gate decision")

    return parse_gate_response(
        raw_response,
        provider=get_decider_provider(),
        model=get_decider_model_name(),
    )

