# Source: https://adk.dev/agents/ + https://adk.dev/agents/llm-agents/

Fetched 2026-05-23.

## Agent types

The `/agents/` page describes ADK agents as "self-contained execution units designed to act autonomously to achieve specific goals." Categories:

- **Simple agents** — `LlmAgent` (also aliased as `Agent`). Single LLM with instruction + tools.
- **Template workflow agents** — `SequentialAgent`, `LoopAgent`, `ParallelAgent` (pre-built BaseAgent subclasses).
- **Custom agents** — extend `BaseAgent` directly.

Each agent can be extended with:
- Multiple AI model options (Gemini, Gemma, Claude, etc. via LiteLlm or model registry)
- Pre-built tools and custom tools
- Artifacts for persistent outputs
- Skills and plugins
- **Callbacks for lifecycle event hooks** (the hook system covered in fetch-006)

The module layout from `gh api repos/google/adk-python/contents/src/google/adk/agents` confirms the available types in code:

```
base_agent.py
base_agent_config.py
llm_agent.py             <-- 36 KB, the main class
llm_agent_config.py
loop_agent.py
loop_agent_config.py
parallel_agent.py
parallel_agent_config.py
sequential_agent.py
sequential_agent_config.py
remote_a2a_agent.py      <-- A2A protocol over HTTP
langgraph_agent.py       <-- ADK can wrap a LangGraph graph as an agent
mcp_instruction_provider.py
context.py / invocation_context.py / callback_context.py
```

Notable: `langgraph_agent.py` exists — so ADK can host a LangGraph graph as a sub-agent if needed. They're not mutually exclusive frameworks.

## `LlmAgent` constructor parameters (from `/agents/llm-agents/`)

**Required:**
- `name` — unique string identifier
- `model` — LLM identifier (a string for Gemini, or an `LiteLlm(...)` object for non-Gemini)

**Core optional:**
- `description` — summary used for delegation/routing decisions in multi-agent setups
- `instruction` — system prompt; supports `{var}` template syntax that gets filled from session state
- `tools` — list of callables, `FunctionTool` instances, or sub-agents wrapped as `AgentTool`
- `input_schema` — Pydantic schema for expected input
- `output_schema` — Pydantic schema enforcing the final response shape
- `output_key` — string key under which the final response gets written into session state

**Advanced optional:**
- `generate_content_config` — temperature, max_output_tokens, safety settings
- `include_contents` — `'default'` or `'none'` to suppress history
- `planner` — `BasePlanner` instance (`BuiltInPlanner` or `PlanReActPlanner`)
- `code_executor` — `BaseCodeExecutor`
- `before_agent_callback` / `after_agent_callback`
- `before_model_callback` / `after_model_callback`
- `before_tool_callback` / `after_tool_callback`
- `sub_agents` — child agents for delegation

## Tool calling loop

> The agent receives instructions, evaluates tool availability, and dynamically decides whether to invoke tools based on context and its instructions. The LLM uses function names, descriptions, and parameter schemas to determine appropriate actions.

i.e. the standard ReAct/function-calling loop, identical in shape to `langgraph.prebuilt.create_react_agent` or OpenAI's function-calling.

## Code example (Python, capital-city pattern from the docs)

```python
from google.adk.agents import LlmAgent

agent = LlmAgent(
    name="capital_agent",
    model="gemini-2.5-flash",
    instruction="Answer questions about capital cities.",
    tools=[get_capital],
)
```

All 5 language implementations follow the same pattern.
