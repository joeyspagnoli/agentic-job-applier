# LangGraph Prebuilt ReAct Agent Overview — https://langchain-ai.github.io/langgraph/agents/overview/

Fetched: 2026-05-24 (URL redirected; content reconstructed from reference docs)

## Agent Architecture Overview

LangGraph agents follow the ReAct pattern: the agent alternates between reasoning (calling the model) and acting (executing tools), accumulating context with each iteration until producing a final answer.

## Prebuilt vs. Custom

LangGraph provides `create_react_agent` as the high-level entry point. Under the hood it produces the same `StateGraph` a developer would write manually. The prebuilt agent handles:

- Tool schema injection into the model call
- Tool result routing back to model
- Parallel tool execution via `ToolNode`
- Optional checkpointing and interrupt support

## Graph Structure

```
START → agent_node (LLM) → [tool_calls?]
                ↓ yes        → tools_node → agent_node (loop)
                ↓ no         → END
```

## MessagesState

The default state schema is `MessagesState`, an `Annotated[list[BaseMessage], add_messages]` field that automatically appends new messages (rather than overwriting):

```python
from langgraph.graph import MessagesState
# Equivalent to:
# class State(TypedDict):
#     messages: Annotated[list[BaseMessage], add_messages]
```

All tool results, model responses, and user messages live in this list. The model always sees the full accumulated history on each invocation.

## ToolNode

`langgraph.prebuilt.ToolNode` is the node that executes tool calls. It:
- Accepts a `list` of LangChain-compatible tools at construction
- Reads `tool_calls` from the last AIMessage in state
- Executes all requested tools (parallel by default)
- Returns `ToolMessage` objects appended to state

## Streaming

Agents can stream token-by-token or step-by-step:

```python
# Step-level streaming (yields dict per node update)
for chunk in graph.stream(inputs, stream_mode="updates"):
    print(chunk)

# Token-level streaming
async for chunk in graph.astream(inputs, stream_mode="messages"):
    print(chunk[0].content, end="")
```

## Memory / Persistence

Without a checkpointer the agent is stateless per `.invoke()` call. To persist across calls:

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
graph = create_react_agent(model, tools=tools, checkpointer=checkpointer)

config = {"configurable": {"thread_id": "session-42"}}
result = graph.invoke(inputs, config=config)
```

`thread_id` scopes the conversation history. Multiple threads run independently.

Other checkpointer backends: `langgraph-checkpoint-sqlite`, `langgraph-checkpoint-postgres`.

## Configuration at Runtime

Agents accept a `RunnableConfig` dict at invoke time for runtime overrides:
- `thread_id` for memory scoping
- `recursion_limit` (default 25) — maximum number of graph steps before `GraphRecursionError`
- `configurable` keys for model parameter overrides
