# fetch-retry-004-adk.md
# Sources: https://adk.dev/integrations/reflect-and-retry/ + https://adk.dev/callbacks/types-of-callbacks/
# Fetched: 2026-05-24
# Prompt: before_tool_callback, after_tool_callback, on_tool_error, Reflect and Retry plugin

## Callback Types for Tools

### before_tool_callback
- **Trigger:** Just before a tool is invoked
- **Return None:** Normal execution proceeds
- **Return a value:** Tool is SKIPPED, the returned value is used as the result
- **Use case:** Validate args, block dangerous tools, use cached results

### after_tool_callback
- **Trigger:** After a tool completes successfully
- **Return None:** Original result passes through
- **Return a value:** Replaces the tool result
- **Use case:** Post-process, validate output, augment response

### on_tool_error (Plugin hook, not standard callback)
- **Trigger:** When tool execution fails (exception raised)
- **Behavior:** If returns a dict, `after_tool_callback` is triggered normally
- **Use case:** Handle failures, implement retry logic, return fallback

**CRITICAL NOTE:** Parameter names must match exactly — `tool`, `args`, `tool_context` for before; add `tool_response` for after. ADK passes by keyword — renaming causes `TypeError` at runtime.

## Reflect and Retry Plugin (Official)

Introduced in ADK 1.16 (October 2025). A first-class plugin that automates retry with LLM reflection.

**Basic setup (10 lines Python):**
```python
from google.adk.plugins import ReflectAndRetryToolPlugin

app = App(
    name="my-agent",
    agent=my_agent,
    plugins=[
        ReflectAndRetryToolPlugin(max_retries=3)
    ]
)
```

**Configuration options:**
| Setting | Purpose | Default |
|---|---|---|
| `max_retries` | Additional retry attempts | 3 |
| `throw_exception_if_retry_exceeded` | Raise on final failure | True |
| `tracking_scope` | INVOCATION or GLOBAL | INVOCATION |

**Mechanism:** Plugin captures tool error responses → feeds structured guidance to LLM → model reflects on what went wrong → retries up to `max_retries` times.

**Custom error extraction (10 lines Python):**
```python
class MyPlugin(ReflectAndRetryToolPlugin):
    def extract_error_from_result(self, result):
        if result.get("status") == "error":
            return result["message"]
        return None
```

## How Errors Reach the Model

1. Tool raises exception → `on_tool_error` callback fires
2. Plugin captures the error details
3. Plugin synthesizes reflection guidance (structured prompt with error context)
4. Guidance injected into model's next turn
5. Model generates corrected tool call

## Raw Callback Retry Pattern (Without Plugin)

```python
def before_tool_callback(tool, args, tool_context):
    if args.get("element_ref") == "":
        return {"error": "element_ref cannot be empty — provide a valid @eN ref"}
    return None  # proceed normally
```
This returns a fake "result" to the model without even calling the tool — a 4-line guard.

## Known Issues

GitHub Discussion #2756: "Is there any way to retry the last tool call or task when LLM call throws error?" — Community workaround: wrap in before_tool_callback to validate args first.

GitHub Discussion #795: "Tool Failure Crashes Entire ADK Multi-Agent Workflow" — Plugins needed for resilience.

MALFORMED_FUNCTION_CALL issue (#1521, 29 comments): Random Gemini errors with complex tool arguments. Workaround: retry at Python level + argument simplification.
