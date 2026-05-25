# fetch-retry-006-strands.md
# Sources: https://strandsagents.com/docs/user-guide/concepts/agents/hooks/ + https://strandsagents.com/docs/api/python/strands.hooks.events/
# Fetched: 2026-05-24
# Prompt: AfterToolCallEvent retry, cancel_tool, tool error hooks, code examples

## AfterToolCallEvent.retry Property

**Type:** `bool`
**Default:** `False`

"Whether to retry the tool invocation. Can be set by hook callbacks to trigger a retry. When True, the current result is discarded and the tool is called again."

When `retry=True`:
- Tool executor discards current result
- Tool invoked again with same `tool_use_id`
- Intermediate streaming events from discarded attempts already emitted (idempotency concern)
- Only the final attempt's `ToolResultEvent` is added to conversation history

## BeforeToolCallEvent.cancel_tool Property

**Type:** `Union[str, bool, None]`

"A user defined message that when set, will cancel the tool call. The message will be placed into a tool result with an error status."

```python
@hook(BeforeToolCallEvent)
def validate_element_ref(event: BeforeToolCallEvent):
    args = event.tool_use.get("input", {})
    if not args.get("ref"):
        event.cancel_tool = "ref cannot be empty — provide a valid @eN ref from the snapshot"
```

## Full Retry-on-Error Hook (22 lines)

```python
class RetryOnToolError(HookProvider):
    def __init__(self, max_retries: int = 1):
        self.max_retries = max_retries
        self._attempt_counts: dict[str, int] = {}

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(AfterToolCallEvent, self.handle_retry)

    def handle_retry(self, event: AfterToolCallEvent) -> None:
        tool_use_id = str(event.tool_use.get("toolUseId", ""))
        attempt = self._attempt_counts.get(tool_use_id, 0) + 1
        self._attempt_counts[tool_use_id] = attempt

        if event.result.get("status") == "error" and attempt <= self.max_retries:
            event.retry = True
        elif event.result.get("status") != "error":
            self._attempt_counts.pop(tool_use_id, None)
```

## AfterToolCallEvent.exception Property

**Type:** read-only

"When a tool raises an exception, the agent converts it to an error result and returns it to the model, allowing the model to adjust its approach and retry."

The exception is accessible via `event.exception`. Pattern for distinguishing expected vs unexpected errors:

```python
class PropagateUnexpectedExceptions(HookProvider):
    def _check_exception(self, event: AfterToolCallEvent) -> None:
        if event.exception is None:
            return
        if isinstance(event.exception, self.allowed_exceptions):
            return  # let model see it and retry
        raise event.exception  # propagate unexpected errors
```

## Default Behavior Without Hooks

When a tool raises an exception, Strands converts it to an error result AND RETURNS IT TO THE MODEL automatically — no hooks needed. The model sees the error and decides whether to retry.

This is the key difference: Strands' default is model-visible errors. You add hooks for MECHANICAL retry (force re-run without involving model) or for CANCELLATION (block tool before it runs).

## Hook Status

As of May 2025 launch, hooks were marked experimental. GitHub Issue #667: "Release tool and model hooks as non-experimental" — filed July 2025, status: open.

## Production Context

Strands launched May 2025. "What We Learned from One Year of Building Production Agents" (blog, 2026): Steering Hooks providing 100% accuracy pass rate vs. 80.8% for graph-based workflows. Focus on validation before tool execution rather than retry after.
