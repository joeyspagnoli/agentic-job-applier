# LangGraph Build Agent — https://langchain-ai.github.io/langgraph/agents/agents/

Fetched: 2026-05-24 (original URL redirected; content synthesized from reference docs and how-to guides)

## create_react_agent — The Prebuilt Loop Primitive

LangGraph ships a prebuilt ReAct agent via `langgraph.prebuilt.create_react_agent`. This is the primary "one-liner" entry point for a tool-calling loop.

```python
from langgraph.prebuilt import create_react_agent

def check_weather(location: str) -> str:
    """Return the weather forecast for the specified location."""
    return f"It's always sunny in {location}"

graph = create_react_agent(
    "anthropic:claude-3-7-sonnet-latest",  # or any LangChain model object
    tools=[check_weather],
    prompt="You are a helpful assistant",
)

inputs = {"messages": [{"role": "user", "content": "what is the weather in sf"}]}
for chunk in graph.stream(inputs, stream_mode="updates"):
    print(chunk)
```

## How the ReAct Loop Works

`create_react_agent` compiles a `StateGraph` with two nodes:
1. **model node**: calls the LLM with current message history + tool schemas
2. **tools node**: executes all tool calls the model requested (parallel execution if multiple)

Edge logic:
- If model output contains tool calls → route to tools node
- If model output has no tool calls → route to END

This continues until the model produces a final response without tool calls. The loop is the standard ReAct ("Reasoning + Acting") pattern.

## Tool Definition

Tools are plain Python functions with type hints and docstrings. LangChain's `@tool` decorator is optional but adds schema control:

```python
from langchain_core.tools import tool

@tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b
```

Without the decorator, `create_react_agent` accepts plain callables and infers schemas from type annotations.

## Parallel Tool Calls

If the model requests multiple tool calls in one response, they execute in parallel within the tools node.

## Key Parameters of create_react_agent

| Parameter | Purpose |
|-----------|---------|
| `model` | LangChain chat model instance or string ID |
| `tools` | List of callables or LangChain Tool objects |
| `prompt` | System prompt string or prompt template |
| `checkpointer` | Persistence backend for state (enables HITL) |
| `interrupt_before` | List of node names to pause before |
| `interrupt_after` | List of node names to pause after |

## Invoke vs Stream

```python
# Blocking invocation
result = graph.invoke({"messages": [("user", "hello")]})

# Streaming (yields state updates per node)
for chunk in graph.stream(inputs, stream_mode="updates"):
    print(chunk)

# Async
result = await graph.ainvoke(...)
```

## Under the Hood: The Full Graph

For more control, developers skip `create_react_agent` and build the graph manually:

```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

tools = [check_weather]
tool_node = ToolNode(tools)

def call_model(state):
    response = model.bind_tools(tools).invoke(state["messages"])
    return {"messages": [response]}

def should_continue(state):
    last = state["messages"][-1]
    if last.tool_calls:
        return "tools"
    return END

graph = StateGraph(MessagesState)
graph.add_node("agent", call_model)
graph.add_node("tools", tool_node)
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, ["tools", END])
graph.add_edge("tools", "agent")
compiled = graph.compile()
```

This pattern is essentially what `create_react_agent` generates internally but allows full customization of nodes, edges, and state schema.
