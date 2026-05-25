# Project Deep Dive — browser-use/browser-use

URL: https://github.com/browser-use/browser-use
Stars: 95,320 (as of 2026-05-24)
Last commit: 2026-05-24 (active daily)
Language: Python
Version: 0.12.8

## Agent Harness

**CUSTOM BYO LOOP — no framework dependency.**

The `browser_use/agent/service.py` (4,131 lines) is a pure-Python async class `Agent(Generic[Context, AgentStructuredOutput])` that implements:
- Custom `MessageManager` for history compaction
- Custom `BaseChatModel` abstraction (their own, not LangChain's)
- `EventBus` (bubus library) for step events
- Pydantic models for all structured outputs

### Key imports (what they DON'T import):
- NO `langchain`
- NO `openai_agents`
- NO `google.adk`
- NO `pydantic_ai`
- NO `autogen`

### Key imports (what they DO use):
```python
from bubus import EventBus          # event bus
from pydantic import BaseModel      # structured outputs
from browser_use.llm.base import BaseChatModel  # their OWN abstraction
```

### Dependencies (pyproject.toml pinned):
- `openai==2.16.0` — direct OpenAI SDK
- `anthropic==0.76.0` — direct Anthropic SDK
- `google-genai==1.65.0` — direct Google SDK
- `groq==1.0.0` — direct Groq SDK
- `ollama==0.6.1` — direct Ollama
- `cdp-use==1.4.5` — their own CDP lib
- `browser-use-sdk==3.4.2` — their cloud SDK

LiteLLM appears only in `[project.optional-dependencies] examples` — NOT in core.

## Browser Layer

Playwright + cdp-use (their own CDP library for raw Chrome DevTools Protocol access).

## Model

Multi-model. Default in examples: GPT-4o / claude-3-5-sonnet. Supports any model through their `BaseChatModel` adapter pattern.

## Agent Loop Architecture

`service.py` implements a classic observe→decide→act loop:
1. `update_state()` → capture page AX tree / screenshot
2. `_generate_action()` → call LLM with structured output schema
3. Execute action via `controller`
4. Repeat until done or max_steps

The loop has circuit breakers: `max_steps`, `max_failures`, and a judge mechanism (`construct_judge_messages`) for evaluating whether the task is complete.

## What They Say About Their Stack

From recent commits and blog post "The Bitter Lesson of Agent Harnesses":
- "Every helper function is a constraint the RL'd model has to fight around"
- They built their OWN model abstraction rather than using LangChain/LiteLLM in the core
- Recent 0.12.x commits focus on prompt caching (Gemini, cache_control)
- Active feature: message compaction for long sessions

## Migration History

No migration from any framework — they started from scratch. The `examples/` dir has a `langchain-openai` optional dep, meaning they support LangChain as an integration path but do not depend on it.

## Harness Integrations

browser-use can be wrapped by:
- LangChain (via optional `langchain-openai` in examples)
- LlamaIndex
- OpenAI Agents SDK (as a tool)
- Any custom loop

This positions browser-use as a **browser-layer component**, not a harness — consistent with our architecture.
