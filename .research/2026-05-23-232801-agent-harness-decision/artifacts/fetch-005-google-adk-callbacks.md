# Source: https://adk.dev/callbacks/
# Fetched: 2026-05-24

## Overview

The ADK callback system provides "standard functions you define" that the framework
calls automatically at predefined execution points. These enable observation,
customization, and control of agent behavior without modifying core framework code.

## Six Core Callback Points

1. **`before_agent_callback`** — Executes before the agent's main processing logic
   begins for a request.
2. **`after_agent_callback`** — Executes after the agent completes all processing
   steps but before returning results.
3. **`before_model_callback`** — Triggers prior to any LLM API call.
4. **`after_model_callback`** — Triggers after receiving an LLM response.
5. **`before_tool_callback`** — Executes before a tool is invoked.
6. **`after_tool_callback`** — Executes after a tool completes.

## Return Value Control Mechanism

The callback's return value is the *core mechanism* for interception:

| Callback | Return `None` | Return a value |
|---|---|---|
| `before_agent` | Proceed normally | Skip agent; returned `Content` becomes final output |
| `after_agent` | Proceed normally | Replace agent output with returned `Content` |
| `before_model` | Make LLM call | Skip LLM call; returned `LlmResponse` used as-is |
| `after_model` | Proceed normally | Replace LLM response with returned `LlmResponse` |
| `before_tool` | Execute tool | Skip tool execution; returned `dict` becomes tool result |
| `after_tool` | Proceed normally | Replace tool result with returned `dict` |

Returning `None` always means "let ADK proceed as normal."

## Python Signatures

```python
from typing import Optional
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools import BaseTool, ToolContext

# before_model_callback
def my_before_model(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    # Return None → allow call; return LlmResponse → skip call
    return None

# after_model_callback
def my_after_model(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    return None

# before_tool_callback — KEY for guardrails
def my_before_tool(
    tool: BaseTool,
    args: dict,
    tool_context: ToolContext,
) -> Optional[dict]:
    # Return None → let tool execute
    # Return a dict → skip execution, that dict IS the tool result
    return None

# after_tool_callback
def my_after_tool(
    tool: BaseTool,
    args: dict,
    tool_context: ToolContext,
    tool_response: dict,
) -> Optional[dict]:
    return None
```

## Registration

Callbacks register as named parameters on `LlmAgent` (or `Agent`):

```python
from google.adk.agents import LlmAgent

agent = LlmAgent(
    name="MyCallbackAgent",
    model="gemini-2.0-flash",
    instruction="Be helpful.",
    before_model_callback=my_before_model,
    before_tool_callback=my_before_tool,
    after_tool_callback=my_after_tool,
)
```

## "Never Submit" Guardrail Pattern

`before_tool_callback` is the right hook for a hard "never click Submit" rule:

```python
BLOCKED_TOOLS = {"click_submit", "submit_form", "press_enter_on_submit"}

def block_submit(
    tool: BaseTool,
    args: dict,
    tool_context: ToolContext,
) -> Optional[dict]:
    if tool.name in BLOCKED_TOOLS:
        return {"error": "SUBMIT_BLOCKED", "message": "Submit is disabled by policy."}
    return None  # all other tools proceed normally
```

Returning a non-None dict means the tool call is skipped entirely — the LLM sees
that dict as the tool result, no actual execution occurs.

## Common Use Cases

- **Observation / Debugging**: Log tool args and responses at each step.
- **Guardrails**: Enforce safety rules (e.g., block `submit_form`), validate inputs.
- **State Management**: Read or update `callback_context.state` (session state dict).
- **Caching**: Check a cache before making a real tool call via `before_tool_callback`.
- **Mutation**: Rewrite LLM requests before they go out (prompt injection defense, etc.).

## Key Distinction from Plugins

The docs note that for "security guardrails and policies, use ADK Plugins for better
modularity and flexibility than Callbacks, though callbacks remain powerful for
lower-level control." For a single-agent finisher, callbacks are simpler.
