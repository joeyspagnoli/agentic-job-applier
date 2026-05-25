# AWS Strands Hooks / Lifecycle Events — https://strandsagents.com/docs/user-guide/concepts/agents/hooks/

Fetched: 2026-05-24
Primary source: WebFetch of the hooks SDK documentation page

## Overview

Hooks are Strands' composable, type-safe extensibility mechanism. They allow subscribing to events at key points in the agent lifecycle. Multiple subscribers per event type are supported. The system is designed for monitoring, validation, guardrails, and behavior modification.

## Full Event Lifecycle (Single Agent)

Events fire in this order per invocation:

1. `BeforeInvocationEvent` — request initiated
2. `MessageAddedEvent` — initial message added to history
3. `BeforeModelCallEvent` — just before model inference
4. `AfterModelCallEvent` — after model responds (**reverse order** callbacks)
5. `BeforeToolCallEvent` — before each tool executes
6. `AfterToolCallEvent` — after each tool completes (**reverse order**)
7. `AfterInvocationEvent` — entire invocation complete (**reverse order**)

## Registration Methods

### Simple Callback

```python
from strands import Agent
from strands.hooks import BeforeToolCallEvent

agent = Agent()

def my_callback(event: BeforeToolCallEvent) -> None:
    print(f"About to call: {event.tool_use['name']}")

agent.add_hook(my_callback)  # type inferred from annotation
```

### Plugin Class (recommended for complex hooks)

```python
from strands.plugins import Plugin, hook
from strands.hooks import BeforeToolCallEvent, AfterToolCallEvent

class AuditPlugin(Plugin):
    name = "audit-plugin"

    @hook
    def before_tool(self, event: BeforeToolCallEvent) -> None:
        print(f"Calling: {event.tool_use['name']} with {event.tool_use['input']}")

    @hook
    def after_tool(self, event: AfterToolCallEvent) -> None:
        print(f"Completed: {event.tool_use['name']}")

agent = Agent(plugins=[AuditPlugin()])
```

## Mutable Event Properties — Behavior Control

The hooks system exposes mutable properties on events to influence agent behavior:

### BeforeToolCallEvent (most important for guardrails)

| Property | Type | Effect |
|----------|------|--------|
| `event.cancel_tool` | `str \| None` | Set to a string to cancel the tool call; string becomes the tool result message |
| `event.selected_tool` | `Callable \| None` | Replace the tool to be executed |
| `event.tool_use["input"]` | `dict` | Mutate tool arguments before execution |

### AfterToolCallEvent

| Property | Type | Effect |
|----------|------|--------|
| `event.result` | `dict` | Mutate the tool result seen by the model |
| `event.retry` | `bool` | Set True to retry the tool call |
| `event.exception` | `Exception \| None` | Read-only; original exception if tool failed |

### AfterModelCallEvent

| Property | Type | Effect |
|----------|------|--------|
| `event.retry` | `bool` | Request model re-invocation |

### AfterInvocationEvent

| Property | Type | Effect |
|----------|------|--------|
| `event.resume` | `str \| None` | Set to trigger a follow-up invocation automatically |

## "Never Submit" Guardrail Implementation

This is exactly what `BeforeToolCallEvent` + `cancel_tool` is designed for:

```python
from strands import Agent, tool
from strands.hooks import BeforeToolCallEvent

SUBMIT_TOOL_NAMES = {"click_submit", "submit_form", "final_submit"}

def block_submit(event: BeforeToolCallEvent) -> None:
    tool_name = event.tool_use["name"]
    if tool_name in SUBMIT_TOOL_NAMES:
        event.cancel_tool = (
            f"Policy violation: '{tool_name}' is blocked. "
            "Never click Submit — this is a dry-run only."
        )

agent = Agent(tools=[navigate, fill, click, read_page, screenshot, submit_form])
agent.add_hook(block_submit)

# submit_form will NEVER execute; agent receives the cancel message as tool result
result = agent("Fill out the application form and submit it")
```

The cancellation message is returned to the model as the tool result, allowing the model to reason about why the action was blocked (e.g., "I cannot submit this form due to policy restrictions").

## Limit Tool Call Count (Built-in Pattern)

```python
class LimitToolCounts:
    def __init__(self, max_counts: dict[str, int]):
        self.max_counts = max_counts
        self.counts: dict[str, int] = {}

    def register_hooks(self, registry):
        registry.add_callback(BeforeInvocationEvent, lambda e: self.counts.clear())
        registry.add_callback(BeforeToolCallEvent, self.check_limit)

    def check_limit(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use["name"]
        self.counts[name] = self.counts.get(name, 0) + 1
        limit = self.max_counts.get(name)
        if limit and self.counts[name] > limit:
            event.cancel_tool = f"'{name}' call limit ({limit}) exceeded"
```

## Callback Ordering

- **Before events** (BeforeToolCallEvent, etc.): callbacks execute in **registration order** (A→B→C)
- **After events** (AfterToolCallEvent, etc.): callbacks execute in **reverse registration order** (C→B→A)

Use `HookOrder` constants to position relative to SDK-internal hooks:
```python
from strands.hooks import HookOrder
registry.add_callback(BeforeToolCallEvent, my_cb, order=HookOrder.SDK_FIRST)
```

## Multi-Agent Hook Scope

Individual agent hooks apply only to that agent's tool calls. Orchestrator-level hooks (Graph/Swarm) have separate `BeforeNodeCallEvent` / `AfterNodeCallEvent` events.
