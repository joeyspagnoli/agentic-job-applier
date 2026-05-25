# Forum Survey 002 — Pydantic AI vs OpenAI Agents SDK for Browser

Date: 2026-05-24
Query: "pydantic ai vs openai agents sdk browser automation Python 2026"
Sources: uvik.net, alexcloudstar.com, channel.tel, fast.io, oreateai.com

## Key Findings

### Pydantic AI (pydantic/pydantic-ai)
- "Laser-focused on the output format of an LLM call — structural integrity over flow control"
- "Type safety and structured outputs — brings the same discipline that Pydantic brings to data validation"
- Supports virtually every model: OpenAI, Anthropic, Gemini, DeepSeek, Grok, Cohere, Mistral, Perplexity
- Recommended for: "a Python service that does one well-scoped agent task with strong typing"

### OpenAI Agents SDK
- "Makes it incredibly easy to build production-ready agents with minimal code"
- Automatic agent loops, tool calls, result parsing without manual management
- Strongest features (Responses API, hosted tools, realtime voice) are tightly coupled to OpenAI's platform
- Works with 100+ non-OpenAI models via Chat Completions API
- Recommended when: "committed to OpenAI's platform, want hosted tools, or doing handoff-style multi-agent work"

### For Browser Automation Specifically
**No source provided specific guidance on browser automation for either framework.** Both are generic agent harnesses — browser automation is a use-case layered on top via tools.

### OpenAI Agents SDK 0.14 (May 2026)
New "Model-Native Harness": "a dedicated memory and filesystem orchestrator that holds credentials safely while the model makes decisions." A compute-aware control plane for files and tools.

From Skyvern's pyproject.toml: Skyvern uses `openai-agents>=0.10.5,<0.15` in their server tier — confirming production adoption of OpenAI Agents SDK for browser-adjacent orchestration.

## Complementary Use Pattern

"You could use Pydantic AI within an agent built with the OpenAI Agent SDK to ensure structured outputs." The two aren't mutually exclusive.

In practice, the most common combination seen in browser agents:
- Pydantic for data models (action schemas, state) — used by browser-use, Skyvern, lmnr-ai/index
- Custom loop or a harness for the agent loop
- Direct model SDKs (not going through pydantic-ai's runner for the loop)

## Implication for our project

Neither Pydantic AI nor OpenAI Agents SDK shows up as the dominant harness in browser agents. The dominant pattern remains:
1. Custom loop (browser-use, lmnr-ai/index, gptme, magentic-ui)
2. Google ADK (one strong production case: Google's own blog post migration)
3. OpenAI Agents SDK (Skyvern server tier — for orchestration, not browser execution)

Pydantic (models, not the full pydantic-ai harness) is universal as a data layer.
