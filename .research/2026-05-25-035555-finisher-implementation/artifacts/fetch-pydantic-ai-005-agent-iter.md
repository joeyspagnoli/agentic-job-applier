# Pydantic AI — `agent.iter()` async iterator

**URL:** https://pydantic.dev/docs/ai/core-concepts/agent/ (redirected from https://ai.pydantic.dev/agent/)
**Fetched:** 2026-05-25
**Prompt:** Extract `agent.iter()` async iterator pattern, node types, usage per node.

## Core pattern

```python
async with agent.iter(user_prompt) as agent_run:
    async for node in agent_run:
        # Process each node
```

## Node types

The iterator yields different node types representing execution stages:

- **`UserPromptNode`** — user input and initial configuration
- **`ModelRequestNode`** — request being sent to the LLM
- **`CallToolsNode`** — model response and tool execution
- **`End`** — final result (terminates iteration)

## Accessing usage

Usage statistics are available throughout execution via `agent_run.usage`, which returns a
`RunUsage` object containing tokens, requests, and other metrics. Once an `End` node is reached,
the final result is accessible through `agent_run.result`.

## Example (verbatim)

```python
async with agent.iter('What is the capital of France?') as agent_run:
    async for node in agent_run:
        nodes.append(node)
print(agent_run.result.output)
```

## Why this matters for finisher

The `agent.run(...)` path is one-shot. The `agent.iter(...)` path is the **only** way to:

- Inspect token usage after each model request (subtract cumulative deltas to get per-turn cost)
- Implement a soft $0.05 cap that checks between turns
- Log per-turn artifacts (snapshot before, tool calls executed, snapshot after)
- Inject mid-run cancellation if `g_should_stop()` flips during the run
