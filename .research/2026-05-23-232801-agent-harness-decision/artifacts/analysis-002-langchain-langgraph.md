# Analysis: LangChain / LangGraph as Apply-Worker Agent Harness

**Date:** 2026-05-24  
**Use Case:** Python apply-worker, 6 browser tools, 5-25 turns/apply, $0.01-0.10/apply, "never submit" guardrail, CDP-attached Chromium, self-hosted dist/ for non-technical Windows users.  
**Repo context:** Already has `google-adk==1.23.0` in production. Adding another harness needs strong justification.

---

## 1. What It Is — Two Packages, One Ecosystem

**LangChain** (`langchain`, `langchain-core`, `langchain-openai`, etc.) is an LLM abstraction and integration library. It standardizes prompt templates, chat model interfaces, tool definitions, retrievers, and output parsers across providers. It is not a loop runner.

**LangGraph** (`langgraph`) is the loop/state-machine runtime. It models agent execution as a directed graph of nodes (processing steps) and edges (transitions). LangGraph compiles graphs into runnable objects that manage state, checkpointing, streaming, and human-in-the-loop interrupts. It runs on top of LangChain but does not strictly require it.

In practice, nearly all LangGraph examples import from `langchain-core` for tool definitions and model abstractions. They are functionally coupled even if technically separable.

---

## 2. Loop Primitive — create_react_agent and the Underlying Graph

The standard entry point for a tool-calling agent is `langgraph.prebuilt.create_react_agent`:

```python
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

agent = create_react_agent(
    ChatOpenAI(model="gpt-4o"),
    tools=[navigate_to, read_page, fill_field, click, screenshot, submit_form],
    prompt="You are a job application assistant. Never click submit.",
)

result = agent.invoke({"messages": [("user", "Fill out this application")]})
```

Under the hood this compiles a two-node StateGraph:
- **agent node**: calls the model with the current MessagesState + tool schemas
- **tools node**: ToolNode executes all requested tool calls in parallel

Routing: if last AIMessage has tool_calls -> route to tools node; otherwise -> END. This repeats until the model stops requesting tools. The loop is controlled by recursion_limit (default: 25 graph steps = roughly 12 agent turns for a 2-node graph).

For more control, developers build the graph manually in ~30-40 lines. The prebuilt agent is equivalent but less customizable.

---

## 3. Hooks, Interrupts, and Human-in-the-Loop

LangGraph has no hooks in the Strands/ADK sense (no BeforeToolCallEvent callbacks). Instead it provides two HITL mechanisms:

**Compile-time interrupts** — pause execution at a named node:

```python
graph = create_react_agent(
    model, tools=tools,
    checkpointer=MemorySaver(),
    interrupt_before=["tools"],   # pause before ANY tool execution
)
config = {"configurable": {"thread_id": "apply-001"}}
result = graph.invoke(inputs, config=config)
# execution paused; human reviews pending tool calls
result = graph.invoke(None, config=config)  # resume
```

**Dynamic interrupt** (functional API) — call `interrupt()` from inside a node to pause conditionally.

**For "never submit" enforcement**, LangGraph does not offer a pre-execution hook on tool arguments. Options are:

1. Wrap the submit tool to raise before executing:
   ```python
   @tool
   def submit_form(confirm: bool = False) -> str:
       """Submit the application form."""
       raise PermissionError("Submit is blocked in dry-run mode")
   ```

2. Add a conditional edge that inspects tool_calls names before routing to the tools node.

Neither approach is as clean as Strands' event.cancel_tool or ADK's before_tool_call_callback. The tool-wrapping approach works reliably but couples the guardrail into the tool definition rather than a separate policy layer.

---

## 4. State and Checkpointers

All state flows through MessagesState — an append-only list of BaseMessage objects. Every node receives the full message history and returns incremental updates.

**Checkpointers** persist state between graph steps, enabling resume-after-failure and HITL. Available backends:

| Backend | Package | Notes |
|---------|---------|-------|
| MemorySaver | Built-in | In-process dict; no persistence across restarts |
| SQLite | langgraph-checkpoint-sqlite | File-based; single-process only |
| PostgreSQL | langgraph-checkpoint-postgres | Multi-worker, production-grade |

For the apply-worker (single process, one job at a time), MemorySaver is sufficient if HITL is needed. If persistence is not needed, skip the checkpointer entirely.

thread_id scopes conversation history. Multiple concurrent applications use different thread_id values.

---

## 5. Provider Portability

LangGraph is model-agnostic via LangChain model abstractions. Provider switching requires only a model object swap — no graph changes.

Our repo has openai==2.26.0 and anthropic==0.96.0. Both langchain-openai and langchain-anthropic wrap these SDKs. **Version conflict risk is real**: langchain-openai may require a different openai version than the pinned 2.26.0. Dependency resolution must be verified before adoption.

---

## 6. License, Maturity, and Criticisms

**License:** MIT (langchain-core, langgraph)
**Maturity:** LangGraph 1.1.6 (April 2026). Pre-1.0 had significant breaking changes.
**GitHub stars:** 40,000+ — most widely adopted agent framework.

**Criticisms (sourced from developer experience reports):**

- *3x boilerplate multiplier*: "A simple ReAct agent takes 40 lines in Smolagents and 120 in LangGraph." (pooya.blog, 2026)
- *Abstraction debugging friction*: "debugging requires digging through 5+ layers of abstraction" (GitHub community #182015)
- *Bloat*: LangChain described as "slower, bloated, and has bugs that are known but still have not been fixed"
- *Over-engineering trap*: "The most common mistake in agent development is over-engineering the orchestration layer before validating that the underlying model can handle the task at all"
- *High TCO*: Gartner Peer Insights (2026): "incredibly powerful but with high TCO"
- *Consensus*: LangGraph pays off only for multi-agent orchestration, strict durability, or compliance/auditability

The framework's rapid pre-1.0 evolution is a maintenance risk for a distributed application where users cannot easily upgrade.

---

## 7. Deploy Footprint and Dependency Size

Minimum viable install:
- langgraph (~200 kB)
- langchain-core (~920 kB) — required
- langchain-openai (~100 kB) — for OpenAI integration
- openai (already pinned at 2.26.0)

Additional transitive: pydantic, httpx, tenacity, orjson, jsonpatch. Total new footprint: ~5-8 packages, ~2-4 MB. The risk is not size — it is **version conflict**. langchain-openai and langchain-anthropic have their own version floors that may conflict with strict == pins.

---

## 8. Browser-Agent Fit (BYO Tools)

LangGraph is entirely BYO-tools. All 6 CDP tools wrap as plain Python functions decorated with LangChain's @tool or passed as plain callables. No special integration work is needed:

```python
from langchain_core.tools import tool

@tool
def navigate_to(url: str) -> str:
    """Navigate to a URL. Returns page title."""
    return cdp_navigate(url)
```

Tool definitions are structurally identical to what would be written for ADK or OpenAI Agents SDK.

---

## 9. Verdict: WEAK — Do Not Adopt

LangGraph is the right framework for teams building multi-agent orchestration systems with strict durability, audit, and HITL requirements. It is not the right framework for a single-agent, 6-tool, stateless-within-session apply loop.

**Specific reasons it loses against the status quo (ADK already in production):**

1. **No hook-based guardrail primitive.** The "never submit" guardrail must be implemented by wrapping the tool or mutating graph routing — both are more fragile than ADK's before_tool_call_callback or Strands' event.cancel_tool.

2. **3x boilerplate for the same outcome.** The apply loop is two nodes (agent + tools) and one routing edge. Every simpler framework already provides this with less code.

3. **Dependency conflict risk.** langchain-openai and langchain-anthropic version floors may conflict with openai==2.26.0 and anthropic==0.96.0.

4. **Adding a fourth harness has no benefit.** The repo already has ADK (production), OpenAI Agents SDK, and anthropic direct. LangGraph adds a fourth harness with no capability the existing stack lacks.

5. **Ecosystem churn and debugging overhead.** For a distributed app maintained by one person, LangChain abstraction layers are a debugging liability, not an asset.

**When LangGraph would be reconsidered:** If the apply-worker evolved into a multi-agent system (planner -> researcher -> form-filler -> verifier) with strict per-step audit logging, resume-after-failure, and multi-worker concurrency — then LangGraph's graph primitives and checkpoint system would be genuinely valuable. At that point the complexity pays for itself.
