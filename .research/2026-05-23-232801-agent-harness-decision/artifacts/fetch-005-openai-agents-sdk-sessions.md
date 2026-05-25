# Source: https://openai.github.io/openai-agents-python/sessions/
# Fetched: 2026-05-24

## Overview

Sessions provide automatic conversation history management across multiple agent
runs, eliminating the need to manually handle `.to_input_list()` between turns.

Before each run: stored history is prepended to new input.
After each run: all generated items (user input, responses, tool calls) are
persisted automatically.

## Session Implementations

| Implementation | Use Case |
|---|---|
| `SQLiteSession` | Local dev; file-based or in-memory SQLite |
| `AsyncSQLiteSession` | Async SQLite with `aiosqlite` driver |
| `RedisSession` | Distributed systems, shared low-latency memory |
| `SQLAlchemySession` | Production with existing SQLAlchemy DBs |
| `MongoDBSession` | Multi-process, horizontally-scalable |
| `DaprSession` | Cloud-native with Dapr sidecars |
| `OpenAIConversationsSession` | Server-managed via OpenAI Conversations API |
| `OpenAIResponsesCompactionSession` | Long conversations with auto compaction |
| `AdvancedSQLiteSession` | SQLite with branching + analytics |
| `EncryptedSession` | Transparent encryption wrapper around any backend |

## Quick Start

```python
from agents import Agent, Runner, SQLiteSession

agent = Agent(name="Assistant", instructions="Reply very concisely.")

session = SQLiteSession("conversation_123")  # in-memory SQLite; pass a file path for persistence

# First turn
result = await Runner.run(agent, "What city is the Golden Gate Bridge in?", session=session)
print(result.final_output)  # "San Francisco"

# Second turn — context automatically maintained
result = await Runner.run(agent, "What state is it in?", session=session)
print(result.final_output)  # "California"
```

## In-Memory vs. File-Based

```python
# In-memory (wiped when process exits — right for single-apply use)
session = SQLiteSession("user_id")

# File-based (survives restarts)
session = SQLiteSession("user_id", "conversations.db")
```

## Session Operations

```python
# Retrieve all stored items
items = await session.get_items()

# Append items manually
await session.add_items([
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"},
])

# Remove last item (for retry/backtrack)
last_item = await session.pop_item()

# Clear the entire session
await session.clear_session()
```

## Custom History Merging

```python
def keep_recent_history(history, new_input):
    return history[-10:] + new_input

result = await Runner.run(
    agent,
    "Continue from the latest updates only.",
    session=session,
    run_config=RunConfig(session_input_callback=keep_recent_history),
)
```

Or limit items via `SessionSettings`:

```python
result = await Runner.run(
    agent, "Summarize our recent discussion.",
    session=session,
    run_config=RunConfig(session_settings=SessionSettings(limit=50)),
)
```

## Resuming After Interruptions

```python
result = await Runner.run(agent, "Delete files", session=session)

if result.interruptions:
    state = result.to_state()
    for interruption in result.interruptions:
        state.approve(interruption)
    result = await Runner.run(agent, state, session=session)
```

## Key Constraint

Sessions cannot coexist with `conversation_id`, `previous_response_id`, or
`auto_previous_response_id`. Choose either client-side session management OR
OpenAI server-managed continuation — not both.

## For the Browser-Finisher Use Case

Each apply run needs isolated state. The simplest choice is:
```python
session = SQLiteSession(f"apply_{job_id}")  # in-memory, new per job
```
No file path = in-memory SQLite = zero disk I/O, zero setup, one session per job.
This mirrors ADK's `InMemorySessionService` fresh-per-job pattern.
