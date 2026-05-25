# fetch-retry-003-claude.md
# Source: https://code.claude.com/docs/en/agent-sdk/custom-tools
# Fetched: 2026-05-24
# Prompt: tool error handling, isError, how errors reach model, retry

## Built-in Retry Mechanism

The Claude Agent SDK does NOT have a declarative `retries=N` parameter for tools. Retry relies entirely on the model's own behavior when it sees an `isError: true` result.

## isError Flag — The Core Pattern

The SDK's single mechanism for model-visible tool failure:

```python
# 12 lines — the FULL error-returning pattern
@tool("fetch_data", "Fetch data from an API", {"endpoint": str})
async def fetch_data(args: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(args["endpoint"])
            if response.status_code != 200:
                return {
                    "content": [{"type": "text", "text": f"API error: {response.status_code}"}],
                    "is_error": True,
                }
        data = response.json()
        return {"content": [{"type": "text", "text": json.dumps(data)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Failed: {str(e)}"}], "is_error": True}
```

**Key distinction from the docs:**
| What happens | Result |
|---|---|
| Handler throws uncaught exception | Agent loop STOPS. Claude never sees error. `query()` call fails. |
| Returns `is_error: True` | Agent loop CONTINUES. Claude sees error as data and can retry. |

## Feedback to Model

The error message in the `content` array is what Claude receives. The `is_error: True` flag signals it was a tool failure vs. normal output. Claude then self-corrects on the next turn.

## Validation Error on Malformed Args

Not documented. The SDK does not specify whether malformed tool args (bad JSON, wrong types) trigger automatic retry vs. loop crash.

## Hooks System

The SDK has a hooks system with `PreToolUse`, `PostToolUse`, `PostToolUseFailure` event types. These are event handlers for logging/interception, not retry controllers.

## Production Caveat

From community reports: "Automatic retries on a looped agent multiply cost. Either require user-initiated resume, or route to human-in-the-loop review queue."

Rate limits: SDK treats 429 errors as fatal exceptions rather than backing off — known issue, GitHub #812.

## No Native Retry Budget

Zero built-in retry count management. Retry loops are entirely the responsibility of the application developer or depend on Claude's own judgment to re-call the tool.
