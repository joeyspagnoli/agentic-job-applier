# fetch-retry-002-openai.md
# Sources: https://openai.github.io/openai-agents-python/tools/ + https://openai.github.io/openai-agents-python/ref/agent/
# Fetched: 2026-05-24
# Prompt: tool error handling, failure_error_function, retry, model feedback

## Built-in Retry Mechanism

The SDK has NO declarative `retries=N` parameter for tools. Tool errors are handled by `failure_error_function`.

## failure_error_function

When a function tool crashes, default behavior calls `default_tool_error_function` which converts the exception to an LLM-visible message. The model can then retry.

**Custom error function (10-17 lines):**
```python
def my_custom_error_function(context: RunContextWrapper[Any], error: Exception) -> str:
    print(f"A tool call failed: {error}")
    return "An internal server error occurred. Please try again later."

@function_tool(failure_error_function=my_custom_error_function)
def get_user_profile(user_id: str) -> str:
    if user_id == "user_123":
        return "User profile retrieved."
    else:
        raise ValueError(f"Could not retrieve profile for user_id: {user_id}")
```

**Options:**
- Default (unset): uses `default_tool_error_function` — error text goes to LLM
- Custom function: provide your own error formatter
- `None`: exceptions re-raise (fail-fast semantics)

## MCP Tools

`failure_error_function` also applies to MCP tool failures: "Optional function to convert MCP tool failures into model-visible messages."

## Validation Error on Malformed Args

When the model emits bad JSON / wrong types for tool args, `ModelBehaviorError` is raised. The SDK does NOT automatically retry this — it crashes the agent run (see GitHub Issue #325). This is a known production pain point.

## Explicit Retry — Not Native

No `retry=True` flag or `retries=N` on tools. Users must wrap Runner.run() in a tenacity/retry decorator or handle the exception themselves. ModelBehaviorError from tool-not-found still crashes entire runs.

## max_turns

`max_turns` limits total iterations of the loop — not a per-tool retry budget. Combined with `failure_error_function`, this gives bounded execution but not structured retry logic.

## From the Docs

> "If you explicitly pass `None`, then any tool call errors will be re-raised for you to handle."

No explicit retry loop or retry configuration appears in the tools documentation.
