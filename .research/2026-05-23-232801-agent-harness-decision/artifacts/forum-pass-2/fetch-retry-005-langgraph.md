# fetch-retry-005-langgraph.md
# Sources: https://reference.langchain.com/python/langgraph/types/RetryPolicy + forum discussions
# Fetched: 2026-05-24
# Prompt: RetryPolicy, ToolNode, how errors reach model, boilerplate

## RetryPolicy

Declarative retry configuration for graph NODES (not individual tools):

```python
from langgraph.types import RetryPolicy

builder.add_node(
    "tool_caller",
    tool_calling_function,
    retry_policy=RetryPolicy(
        initial_interval=0.5,
        backoff_factor=2,
        max_interval=30.0,
        max_attempts=3,
        jitter=True,
        retry_on=lambda exc: isinstance(exc, (ConnectionError, TimeoutError))
    )
)
```

**Fields:**
- `initial_interval`: delay before first retry
- `backoff_factor`: exponential backoff multiplier
- `max_interval`: max delay between retries (seconds)
- `max_attempts`: total attempts including first
- `jitter`: randomize interval to prevent thundering herd
- `retry_on`: callable or exception type to determine which errors retry

**Added in version 0.2.24.**

## Critical Limitation: RetryPolicy Re-Runs the Node

RetryPolicy re-executes the ENTIRE NODE, not a model turn. If a node runs an LLM call that fails, the LLM gets to try again from scratch. But:
- The error message from the failed attempt is NOT automatically fed back to the model
- The model starts fresh without knowing what went wrong
- This is infrastructure-level retry, not model-level self-correction

## ToolNode and handle_tool_errors

The prebuilt `ToolNode` has `handle_tool_errors=True` (must be explicitly set in LangGraph 1.0.2+):

```python
from langgraph.prebuilt import ToolNode

tool_node = ToolNode([my_tool], handle_tool_errors=True)
```

When `handle_tool_errors=True`:
- Tool exceptions are caught
- Converted to a `ToolMessage` with the error text
- Added to the state messages list
- The model DOES see the error on its next turn

When `handle_tool_errors=False` (default after 1.0.1 breaking change):
- Exceptions propagate up
- Agent loop crashes

## Error Handling After Retries Exhausted

```python
builder.add_node(
    "risky_node",
    risky_function,
    retry_policy=RetryPolicy(max_attempts=3),
    error_handler=recovery_function  # runs after all retries fail
)
```

`error_handler` receives current state + `NodeError` with failure context, can route via `Command`.

## Known Issue: ValidationError Not Retried

GitHub Issue #6027: "Node Retry Policies are not respected when a node fails with Pydantic ValidationError" — ValidationError is not in the default retry list, so malformed model output silently fails instead of retrying.

## Boilerplate Assessment

To express "model sees error and retries" in LangGraph:
1. Define state graph with `MessagesState`
2. Add LLM node
3. Add tool node with `handle_tool_errors=True`
4. Add conditional edges (tools → agent → tools loop)
5. Compile graph

That's 20-40 lines for what other frameworks do with 1-3 lines.

## LangGraph Issue #7138 — ToolNode Missing Metadata

Open issue: ToolNode doesn't surface model output metadata (stop_reason, token_counts) in error messages. Model retried 249 times without knowing output was truncated due to max_tokens. PR #7381 submitted but open as of research date.
