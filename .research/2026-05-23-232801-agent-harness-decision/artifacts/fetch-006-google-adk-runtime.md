# Source: https://adk.dev/runtime/ + repo source (google/adk-python)
# Fetched: 2026-05-24

## Overview

The ADK runtime handles the event loop that drives an agent through a multi-turn
conversation: it feeds user messages in, calls the LLM, dispatches tool calls, and
streams events back to the caller. The primary entry point is the `Runner` class.

## Four Ways to Run Agents

1. **Web UI** — `adk web` — browser-based interactive testing.
2. **CLI** — `adk run` — terminal REPL.
3. **REST API server** — `adk api_server` — HTTP endpoint.
4. **In-process (programmatic)** — `Runner` + `run_async` — production path for
   embedded agents like our apply-worker.

## Runner Class

```python
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

runner = Runner(
    agent=my_agent,
    app_name="my_app",
    session_service=session_service,  # InMemorySessionService or DatabaseService
)
```

`Runner` accepts three required parameters:
- `agent` — a `BaseAgent` (or any subclass).
- `app_name` — a string namespace; required to scope sessions.
- `session_service` — an `InMemorySessionService` or other session backend.

## Session Lifecycle

Each logical unit of work (one job application) should get its own session:

```python
from google.adk.sessions import InMemorySessionService
import uuid

session_service = InMemorySessionService()  # type: ignore[no-untyped-call]
app_name = "job_apply_decider"
user_id  = "worker"
session_id = str(uuid.uuid4())

await session_service.create_session(
    app_name=app_name,
    user_id=user_id,
    session_id=session_id,
    state={},  # initial session state dict
)
```

`InMemorySessionService` is in-process and zero-dependency. For persistent state
across worker restarts use `DatabaseSessionService` (wraps any SQLAlchemy URL).

## run_async — Event Streaming

```python
from google.genai import types

new_message = types.Content(
    role="user",
    parts=[types.Part(text="your prompt here")],
)

async for event in runner.run_async(
    user_id=user_id,
    session_id=session_id,
    new_message=new_message,
):
    # event is an ADK Event object
    content = getattr(event, "content", None)
    if content:
        for part in content.parts or []:
            if part.text:
                print(part.text)
    if hasattr(event, "is_final_response") and event.is_final_response():
        break
```

`run_async` is an **async generator**; it yields `Event` objects as the agent
thinks, calls tools, and produces output. Callers iterate with `async for`.

## Event Types

Events carry:
- `content` — a `google.genai.types.Content` with `parts` (text, function call,
  function response, etc.)
- `partial` — `True` when this is a streaming chunk, not a complete message.
- `is_final_response()` — method returning `True` on the last model turn.
- `author` — the agent or tool that produced the event.

## Runner Cleanup

```python
finally:
    await runner.close()  # type: ignore[no-untyped-call]
```

Always call `runner.close()` in a `finally` block — it flushes session state and
closes any internal gRPC or HTTP channels opened by LiteLLM or Google backends.

## Existing Pattern in This Repo

`src/agents/root_apply_decider/runtime.py` shows the complete production pattern:

```python
session_service = InMemorySessionService()
await session_service.create_session(
    app_name="job_apply_decider",
    user_id="worker",
    session_id=str(uuid.uuid4()),
    state={},
)
runner = Runner(agent=agent, app_name="job_apply_decider",
                session_service=session_service)
try:
    async for event in runner.run_async(
        user_id="worker", session_id=session_id, new_message=new_message
    ):
        event_text = extract_event_text(event)
        if event_text and event.is_final_response():
            final_response_text = event_text
finally:
    await runner.close()
```

This pattern is proven in production for `root_apply_decider` (the existing
APPLY/SKIP gate).

## Session State

Session state is a plain `dict` stored on the session object. Agents can read and
write it through `callback_context.state` or `tool_context.state`. For the
browser-finisher use case, state can track:
- `current_step` — which field the agent is filling.
- `filled_fields` — list of already-completed fields.
- `form_url` — the ATS page URL.

## RunConfig

`Runner.run_async` accepts an optional `RunConfig` parameter:

```python
from google.adk.runners import RunConfig

run_config = RunConfig(
    max_llm_calls=30,        # hard cap on LLM invocations per run
    streaming_mode=...,      # NONE, SSE, BIDI
)
```

`max_llm_calls` provides a hard ceiling on LLM API calls per apply — critical for
cost control. At our expected 5–25 turns, setting `max_llm_calls=40` gives a 60%
safety margin without risking runaway loops.

## ADK v2 Notes

ADK 2.0 (released 2026-05-19) adds `Workflow` and `Task` primitives on top of the
same `Runner` + `InMemorySessionService` core. Our pinned version `1.23.0` predates
2.0 but uses the same programmatic API; no breaking changes to `Runner.run_async` or
`InMemorySessionService` are documented for the 1.x → 2.x transition on the
in-process path.
