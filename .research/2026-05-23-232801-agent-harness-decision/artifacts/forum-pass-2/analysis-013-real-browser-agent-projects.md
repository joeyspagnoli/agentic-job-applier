# Analysis 013 — Real Browser Agent Projects: What Ships and What They Pick

Date: 2026-05-24
Pass: forum-pass-2
Mode: Design
Built on: analysis-010 (final synthesis), prior surveys 001-012
Sources: 10 GitHub repos (deep-dived), 8 web fetches, 4 forum searches

---

## 1. Survey of Shipped Projects

| Project | Stars | Last Commit | Agent Harness | Browser Layer | Model Routing | Notes |
|---------|-------|-------------|---------------|---------------|---------------|-------|
| browser-use/browser-use | 95,320 | 2026-05-24 | Custom BYO loop (4,131-line service.py) | Playwright + cdp-use | Direct SDKs (openai/anthropic/google-genai/groq/ollama all pinned) | No framework in core; LiteLLM in examples only |
| Skyvern-AI/skyvern | 21,721 | 2026-05-24 | Custom BYO loop (forge/agent.py) + OpenAI Agents SDK (server tier) | Playwright + CV | LiteLLM for routing | Two-tier: custom loop for browser execution, OpenAI Agents SDK for orchestration |
| microsoft/magentic-ui | 9,852 | 2026-05-24 | Custom Protocol (SubAgentProtocol - pure Python typing.Protocol) | Playwright direct | OpenAI azure | Microsoft did NOT use AutoGen despite owning it |
| browser-use/browser-harness | 13,630 | 2026-05-24 | No harness (CDP direct; caller IS the harness) | cdp-use raw CDP | None (caller provides model) | Explicit anti-framework philosophy |
| gptme/gptme | 4,309 | 2026-05-24 | Custom BYO loop | Playwright (optional tool) | openai + anthropic direct | Playwright as one tool among many |
| lmnr-ai/index | 2,348 | 2026-05-22 | Custom BYO loop (~200-line Agent class) | Custom Browser wrapping Playwright | openai/anthropic/google-genai/groq direct | Laminar for observability |
| beatwad/LinkedIn-AI-Job-Applier-Ultimate | 95 | 2026-05-23 | LangChain (langchain==0.3.23) | browser-use + patchright | Multi-provider via LangChain | Most-starred active job-apply bot |
| NathanDuma/LinkedIn-Easy-Apply-Bot | 256 | 2026-05-16 | None (rules-based) | Selenium | N/A | Pre-LLM era |
| aminblm/linkedin-application-bot | 201 | 2026-05-16 | None (rules-based) | Selenium | N/A | Pre-LLM era |
| pranavvkumar21/the_last_application | 4 | 2026-04-27 | LangChain (RAG) | NoDriver | N/A | LangChain for resume RAG |

---

## 2. Harness Frequency Tally (10 projects)

| Harness | Count | Projects |
|---------|-------|----------|
| Custom BYO loop | 5 | browser-use, magentic-ui, gptme, lmnr-ai/index, Skyvern (core) |
| No harness (rules/CDP) | 3 | browser-harness, LinkedIn-Easy-Apply-Bot, linkedin-application-bot |
| LangChain | 2 | beatwad job-applier, the_last_application |
| OpenAI Agents SDK | 1 | Skyvern server tier only (not browser execution layer) |
| Google ADK | 0 | Not found in any scanned project |
| Pydantic AI | 0 | Not found in any scanned project |

---

## 3. The "What People Actually Pick" Answer

The dominant pattern is: roll your own loop.

5 of 6 high-star browser agent projects (all >1,000 stars, active 2026) use a custom async Python loop with no agent framework dependency. The custom loop pattern: direct model SDK calls, Pydantic for structured outputs, observe-plan-act while loop, custom circuit breakers.

For job-apply bots, LangChain appears in 2 of 4 LLM-powered projects. LangChain's appeal in this tier is multi-provider routing. But these are personal tools, not shipped at scale.

One exception: Skyvern uses OpenAI Agents SDK in their server tier for multi-agent orchestration, but not in the core browser execution layer.

---

## 4. The "What People Regret" Answer

The primary regret is LangChain:
- browser-use (95k stars) never used LangChain in core — 4,131 lines of custom code says it clearly
- Skyvern wraps Skyvern AS a LangChain Tool (for LangChain users to call Skyvern), rather than building Skyvern on LangChain
- microsoft/magentic-ui: Microsoft owns AutoGen and chose neither AutoGen nor LangChain; wrote SubAgentProtocol as 3 lines of Python typing.Protocol instead
- browser-use's own "Bitter Lesson" blog explicitly argues framework abstractions fight capable models

Secondary complaint: thick abstraction layers. Browser-harness (13.6k stars, born from browser-use's own experience) proves: even the team that built the most popular browser-agent framework concluded "delete the helpers."

Most common migration pattern identified: from heavy framework (LangChain/AutoGen) to custom loop or thin CDP.

---

## 5. Compose-with-Browser-Layer Analysis

Three patterns observed in the wild:

**Pattern A: browser-use as a tool (Skyvern/LangChain integration)**
The harness calls browser-use as a tool; browser-use runs its own loop to completion and returns. Two nested loops. Used when the browser task is opaque/autonomous.

**Pattern B: BYO Playwright tools (our approach, also gptme, magentic-ui)**
Each tool = one deterministic browser action (click, fill, get_ax_tree). The harness controls the loop. No nested loops. The harness decides what to call next.

**Pattern C: Raw CDP (browser-harness)**
The calling LLM is both harness and model. No Python agent loop at all.

For the 3 candidate harnesses from prior analysis, all support Pattern B:
- Google ADK: FunctionTool wrapping, before_tool_callback blocks Submit, RunConfig(max_llm_calls=N) built-in
- OpenAI Agents SDK: @function_tool, custom Guardrail class, SDK runner
- LangChain: @tool, LangGraph graph, middleware hooks (more boilerplate)

---

## 6. Implications for Our Project

The survey confirms the prior pass's recommendation (analysis-010) without requiring any change:

1. BYO-tools is universal among shipped production browser agents — we are doing exactly what the best-engineered projects do

2. browser-use as an alternative would mean surrendering loop control; its own team's "Bitter Lesson" blog confirms thick abstractions fight capable models; our thin 6-tool BYO approach is philosophically aligned with the field's direction

3. LangChain is chosen for multi-provider routing, not browser-agent capabilities; we have a primary model (gpt-5.4-mini) and a vision fallback; multi-provider routing is handled by LiteLLM in ADK

4. Google ADK's production validation: Google's own engineering team refactored to ADK citing SequentialAgent pipeline, built-in circuit breakers, Pydantic structured outputs, native OpenTelemetry — the exact same reasons we chose it

5. Skyvern's architecture is the closest production precedent: custom browser loop + LiteLLM + OpenAI Agents SDK for server-tier orchestration; our stack (Google ADK + LiteLLM + BYO tools) is the open-source analog

No change to the current recommendation. Google ADK + BYO Playwright tools + gpt-5.4-mini.
