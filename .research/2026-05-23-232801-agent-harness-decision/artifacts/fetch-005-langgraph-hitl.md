# LangGraph Human-in-the-Loop — https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/

Fetched: 2026-05-24 (original URL redirected; content reconstructed from available docs)

## Overview

LangGraph's human-in-the-loop (HITL) capability is built on two primitives:

1. **Interrupts** — pause graph execution at a specified node
2. **Checkpointers** — persist state so execution can be resumed after human review

Without a checkpointer, interrupts cannot function (there is nowhere to save paused state).

## Interrupt Mechanism

Interrupts are declared at graph compile time:

```python
graph = create_react_agent(
    model,
    tools=tools,
    checkpointer=MemorySaver(),
    interrupt_before=["tools"],   # pause before any tool execution
    # OR:
    interrupt_after=["agent"],    # pause after model call, before tool execution
)
```

When execution reaches an interrupted node, the graph raises an `Interrupt` (or returns with `__interrupt__` in the state), preserving all state in the checkpointer. Execution is suspended at that node.

## Resuming After Interrupt

```python
config = {"configurable": {"thread_id": "my-thread"}}

# First call — will pause before "tools" node
result = graph.invoke(inputs, config=config)
# result["__interrupt__"] contains the pending tool calls

# Human reviews, approves...

# Resume — pass None to continue from where we left off
result = graph.invoke(None, config=config)
```

Passing `None` as input tells LangGraph to resume from the saved checkpoint rather than starting fresh.

## Modifying State Before Resume

Humans can edit the pending state before resuming:

```python
# Update a specific field in the graph state before resuming
graph.update_state(
    config=config,
    values={"messages": [corrected_message]},
)
result = graph.invoke(None, config=config)
```

This allows humans to correct model outputs, modify tool arguments, or inject new messages.

## Programmatic Approval Pattern (for "never submit" guardrails)

Rather than using `interrupt_before` globally, a custom conditional edge can check tool call intent:

```python
def approve_tools(state: MessagesState):
    last = state["messages"][-1]
    for tc in last.tool_calls:
        if tc["name"] == "click_submit":
            raise ValueError("Submit action requires human approval")
    return "tools"

graph.add_conditional_edges("agent", approve_tools, {"tools": "tools", END: END})
```

Alternatively, implement a tool wrapper that raises before executing:

```python
@tool
def click(selector: str) -> str:
    """Click a UI element."""
    if "submit" in selector.lower():
        raise PermissionError("Submit clicks are blocked by policy")
    return do_click(selector)
```

## Dynamic Interrupts (Functional API)

LangGraph's functional API allows calling `interrupt()` from inside a node function directly:

```python
from langgraph.types import interrupt

def review_node(state):
    decision = interrupt({"pending": state["messages"][-1].tool_calls})
    if decision == "approve":
        return state
    raise ValueError("Rejected by human")
```

## Checkpointer Backends

| Backend | Package | Use Case |
|---------|---------|---------|
| `MemorySaver` | `langgraph` (built-in) | In-process, single run, testing |
| SQLite | `langgraph-checkpoint-sqlite` | Single-process persistence |
| PostgreSQL | `langgraph-checkpoint-postgres` | Multi-worker, production |
| Custom | Implement `BaseCheckpointSaver` | Any storage |

For our single-process apply-worker, `MemorySaver` is sufficient for within-session HITL. `MemorySaver` stores everything in a dict in-process — no external DB needed.

## Key Limitation

**Checkpointers add state serialization overhead on every graph step.** For a 20-turn apply loop with `MemorySaver`, the cost is negligible (in-memory dict). For `PostgreSQL`, every step incurs a DB write.
