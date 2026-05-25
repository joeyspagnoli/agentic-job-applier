# Project Deep Dive — Skyvern-AI/skyvern

URL: https://github.com/Skyvern-AI/skyvern
Stars: 21,721 (as of 2026-05-24)
Last commit: 2026-05-24 (active daily — major engineering team)
Language: Python
Version: 1.0.36

## Agent Harness

**CUSTOM BYO LOOP + OpenAI Agents SDK (in server tier).**

Skyvern's architecture is layered:
1. **Core forge** (`skyvern/forge/agent.py`): Custom BYO Python loop. Uses `structlog`, `openai.types.responses.response`, raw `playwright.async_api.Page`. No LangChain in core.
2. **Server tier** (`pyproject.toml [server]` deps): `openai-agents>=0.10.5,<0.15` — **OpenAI Agents SDK is used in the server/hosted product** for orchestrating multi-step workflows.
3. **Integrations** (first-class, separate packages): `integrations/langchain/`, `integrations/llama_index/`, `integrations/make/`, `integrations/mcp/`, `integrations/n8n/`

### Key observation on openai-agents in Skyvern:
```
# From pyproject.toml comment:
# Plain pip sees LiteLLM's exact openai pin and therefore resolves this
# range to openai-agents 0.10.x. Cloud/source installs include the cloud
# group below, where uv overrides let the newer 0.14.x SDK resolve.
"openai-agents>=0.10.5,<0.15",
```
The OpenAI Agents SDK was **added to the server tier** (not local/embedded tier). This is a significant signal: Skyvern migrated their hosted product to use OpenAI Agents SDK for orchestration while keeping the core browser execution loop as pure custom code.

## Browser Layer

Playwright (direct). CDP access for performance. Computer vision + LLM for element targeting.

**Architecture**: "planner-actor-validator loop"
1. Planner: decomposes goal into steps
2. Actor: executes via Playwright
3. Validator: LLM + CV checks result

## Model

LiteLLM (`litellm==1.83.14`) for model routing — supports OpenAI, Anthropic, Google Vertex, Azure.

## LangChain Integration (as a tool wrapper)

`integrations/langchain/skyvern_langchain/agent.py`:
```python
class RunTask(SkyvernTaskBaseTool):
    name: str = "run-skyvern-agent-task"
    # Wraps Skyvern as a LangChain Tool
    async def _arun(self, user_prompt: str, url: str | None = None) -> TaskRunResponse:
        return await self.agent.run_task(...)
```

Skyvern is used AS a LangChain tool — meaning LangChain users can call Skyvern tasks from their LangChain agent. The harness is the caller's LangChain code; Skyvern is the browser execution engine.

## LlamaIndex Integration (similar pattern)

`integrations/llama_index/skyvern_llamaindex/agent.py`: FunctionTool wrapping Skyvern calls.

## Recent Commits (2026-05-24)

Focus areas:
- SKY-10130: nullable TurnOutcome JSON column (structured outputs)
- SKY-10307: Copilot missing-context fallback (HITL feature)
- SKY-10124: Copilot unexpected errors recoverable
- CDP header protocol alignment (performance work)
- Parallelize artifact persistence (performance)

No migration commit messages found — team has been consistent on their architecture.

## What This Means

Skyvern = **the template for mature browser agent architecture**:
- Custom execution loop for browser tasks (performance + control)
- LiteLLM for model routing (provider flexibility)
- OpenAI Agents SDK in server tier (multi-agent orchestration)
- LangChain as a first-class integration path (not the harness itself)
- LlamaIndex as second integration path
- MCP as the newest integration path
