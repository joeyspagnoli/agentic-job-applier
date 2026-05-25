# AWS Strands Agent Loop — https://strandsagents.com/docs/user-guide/concepts/agents/agent-loop/

Fetched: 2026-05-24

## Core Loop Mechanism

The Strands agent loop is a simple iterative cycle:

1. **Model Reasoning** — the LLM receives current conversation context and reasons about the request
2. **Tool Selection** — the model decides whether to call a tool or respond directly
3. **Tool Execution** — if tool_use stop reason, execute the requested tool(s)
4. **Context Accumulation** — tool results are appended to conversation history
5. **Repeat** — return to step 1 with updated context

Loop terminates when the model produces a response without requesting any tool call.

In pseudocode:
```python
while True:
    response = model.invoke(conversation_history)
    if response.stop_reason == "end_turn":
        return response
    elif response.stop_reason == "tool_use":
        for tool_call in response.tool_calls:
            result = execute_tool(tool_call)
            conversation_history.append(result)
    else:
        # max_tokens, cancelled, content_filtered, guardrail_intervention
        raise appropriate_exception(response.stop_reason)
```

## Stop Reasons (7 Conditions)

| Stop Reason | Loop Action |
|-------------|-------------|
| `end_turn` | Normal completion — return response |
| `tool_use` | Execute tools, continue loop |
| `cancelled` | External cancellation via `agent.cancel()` |
| `max_tokens` | Response truncated — **unrecoverable** |
| `stop_sequence` | Configured stop sequence hit |
| `content_filtered` | Safety filter blocked response |
| `guardrail_intervention` | Policy stopped generation |

## Context Accumulation — Why It Enables Reasoning

Each loop iteration accumulates history: the model sees every prior tool call AND its result. This is what enables multi-step reasoning — a codebase analysis example showed the model progressively requesting file listings, code reads, and searches as understanding deepened.

## Max Iterations

There is no single `max_iterations` parameter documented. Context exhaustion is the primary limit:
- When the conversation history exceeds the model's context window, a `MaxTokensReachedException` is raised
- Mitigation: use `SlidingWindowConversationManager` or `SummarizingConversationManager` to keep context bounded

```python
from strands.agent.conversation_manager import SlidingWindowConversationManager

agent = Agent(
    tools=[...],
    conversation_manager=SlidingWindowConversationManager(window_size=40),
)
```

## Human Interrupt / Cancellation

```python
import asyncio

agent = Agent(tools=[...])

async def run():
    task = asyncio.create_task(agent.invoke_async("Do something long"))
    await asyncio.sleep(5)
    agent.cancel()  # interrupt the running loop
    result = await task
```

## Concurrency Model

The agent loop is **synchronous by default** (`agent("prompt")`). Async is available via:
- `agent.invoke_async("prompt")` — async coroutine
- `agent.stream_async("prompt")` — async generator for streaming

Multiple agents can run concurrently in separate async tasks.
