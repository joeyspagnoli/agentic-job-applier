# Claude Agent SDK — Sessions (Full Documentation)

**Source:** https://code.claude.com/docs/en/agent-sdk/sessions  
**Fetched:** 2026-05-24

---

A session is the conversation history the SDK accumulates while your agent works: your prompt, every tool call, every tool result, every response. The SDK writes it to disk automatically.

**Important:** Sessions persist the **conversation**, not the filesystem. File changes are real and irreversible without separate file checkpointing.

Session files location: `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`  
Where `<encoded-cwd>` = absolute working directory with every non-alphanumeric char replaced by `-`.

---

## When to Use Sessions

| Scenario | What to Use |
|----------|-------------|
| One-shot task: single prompt, no follow-up | Nothing extra — one `query()` call |
| Multi-turn chat in one process | `ClaudeSDKClient` (Python) or `continue: true` (TypeScript) |
| Resume after process restart | `continue_conversation=True` (Python) / `continue: true` (TypeScript) |
| Resume a specific past session | Capture session ID → pass to `resume` |
| Try alternative approach without losing original | Fork the session |
| Stateless task, no disk writes (TypeScript only) | `persistSession: false` |

---

## Continue vs Resume vs Fork

- **Continue:** finds the most recent session in current directory — no ID needed
- **Resume:** takes a specific session ID — required for multi-user apps or non-latest sessions
- **Fork:** creates a new session starting from a copy of original's history; original unchanged; both get their own IDs

---

## Python: `ClaudeSDKClient` (Automatic Session Management)

```python
import asyncio
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

async def main():
    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Edit", "Glob", "Grep"],
    )

    async with ClaudeSDKClient(options=options) as client:
        # First query
        await client.query("Analyze the auth module")
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(block.text)

        # Second query: automatically continues the same session
        await client.query("Now refactor it to use JWT")
        async for message in client.receive_response():
            if isinstance(message, ResultMessage):
                print(f"[done: {message.subtype}, cost: ${message.total_cost_usd:.4f}]")

asyncio.run(main())
```

---

## Capture Session ID

```python
session_id = None

async for message in query(
    prompt="Analyze the auth module",
    options=ClaudeAgentOptions(allowed_tools=["Read", "Glob", "Grep"]),
):
    if isinstance(message, ResultMessage):
        session_id = message.session_id
        if message.subtype == "success":
            print(message.result)
```

---

## Resume by ID

```python
async for message in query(
    prompt="Now implement the refactoring you suggested",
    options=ClaudeAgentOptions(
        resume=session_id,
        allowed_tools=["Read", "Edit", "Write", "Glob", "Grep"],
    ),
):
    if isinstance(message, ResultMessage) and message.subtype == "success":
        print(message.result)
```

Common reasons to resume:
- Follow up on completed task (agent already has prior analysis in context)
- Recover from `error_max_turns` or `error_max_budget_usd` with a higher limit
- Restart your process (captured ID before shutdown)

**Gotcha:** If `resume` returns a fresh session, the most common cause is mismatched `cwd`. Session files live under `~/.claude/projects/<encoded-cwd>/*.jsonl` — must match the CWD used when session was created.

---

## Fork Session

```python
forked_id = None
async for message in query(
    prompt="Instead of JWT, implement OAuth2 for the auth module",
    options=ClaudeAgentOptions(
        resume=session_id,
        fork_session=True,
    ),
):
    if isinstance(message, ResultMessage):
        forked_id = message.session_id  # New ID, distinct from session_id

# Original session unchanged; resuming it continues the JWT thread
async for message in query(
    prompt="Continue with the JWT approach",
    options=ClaudeAgentOptions(resume=session_id),
):
    ...
```

**Note:** Forking branches conversation history, not filesystem. File changes are still real on disk.

---

## Session Utilities

```python
from claude_agent_sdk import list_sessions, get_session_messages, get_session_info, tag_session

# List sessions
sessions = await list_sessions()

# Get messages from a session
messages = await get_session_messages(session_id)

# Get session metadata
info = await get_session_info(session_id)

# Tag a session
await tag_session(session_id, ["production", "auth-refactor"])
```

---

## Resume Across Hosts / Serverless

Sessions are local to the machine that created them. Options:

1. **Move the file:** copy `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` to same path on new host before calling `resume`
2. **Don't rely on resume:** capture results as application state and pass into a fresh session's prompt (more robust)

Both SDKs provide `SessionStore` adapter interfaces for mirroring transcripts to shared storage.

---

## Your Apply-Worker Pattern

```python
async def apply_to_job(job_url: str) -> str:
    async with ClaudeSDKClient(options=options) as client:
        await client.query(f"Start job application workflow for {job_url}")
        
        result_text = None
        async for message in client.receive_response():
            if isinstance(message, ResultMessage):
                if message.subtype == "success":
                    result_text = message.result
                elif message.subtype == "error_max_turns":
                    # Resume with more turns
                    session_id = message.session_id
                    # ... resume logic
        
        return result_text
```

---

## Related Resources

- Agent loop: https://code.claude.com/docs/en/agent-sdk/agent-loop
- File checkpointing: https://code.claude.com/docs/en/agent-sdk/file-checkpointing
- Python ClaudeAgentOptions: https://code.claude.com/docs/en/agent-sdk/python#claudeagentoptions
- Session storage adapters: https://code.claude.com/docs/en/agent-sdk/session-storage
