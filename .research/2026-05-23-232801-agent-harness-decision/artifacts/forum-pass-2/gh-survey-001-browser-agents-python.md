# GH Survey 001 — Browser Agent Python Repos (by stars)

Date: 2026-05-24
Command: `gh search repos "browser agent" --language python --sort=stars --limit 20`

| Rank | Repo | Stars | Last Updated | Description |
|------|------|-------|--------------|-------------|
| 1 | browser-use/browser-use | 95,320 | 2026-05-24 | Make websites accessible for AI agents (Playwright-based custom loop) |
| 2 | browser-use/browser-harness | 13,630 | 2026-05-24 | Self-healing CDP harness — thin wrapper over Chrome DevTools Protocol |
| 3 | microsoft/magentic-ui | 9,852 | 2026-05-24 | Multi-agent human-centered browser interface (AutoGen-based) |
| 4 | PleasePrompto/notebooklm-skill | 6,626 | 2026-05-24 | Claude Code skill with browser automation |
| 5 | microsoft/fara | 5,239 | 2026-05-24 | Fara-7B: Efficient agentic model for computer use |
| 6 | gptme/gptme | 4,309 | 2026-05-24 | BYO loop — terminal agent with Playwright browser tool |
| 7 | StructuredLabs/preswald | 4,288 | 2026-05-24 | WASM Python data app (off-topic — browser = WASM not automation) |
| 8 | tiny-pilot/tinypilot | 3,455 | 2026-05-22 | Browser-based KVM (off-topic) |
| 9 | TurixAI/TuriX-CUA | 3,022 | 2026-05-24 | Computer-use agent |
| 10 | oxylabs/oxylabs-ai-studio-py | 2,904 | 2026-05-24 | Structured web scraping + AI (custom loop + Playwright) |
| 11 | lmnr-ai/index | 2,348 | 2026-05-22 | SOTA browser agent — **BYO custom async Python loop, no framework** |
| 12 | Planetary-Computers/autotab-starter | 1,015 | 2026-04-26 | Build browser agents for real world tasks |
| 13 | LvcidPsyche/auto-browser | 510 | 2026-05-24 | MCP-native browser agent — human in the loop |

## Notes on key repos examined:

### browser-use/browser-use (95k stars)
- **Harness**: Pure custom Python async loop (~4,131 lines in `service.py`)
- **Browser layer**: Playwright + custom DOM distillation, cdp-use
- **Models**: Multi-provider via direct SDKs (openai, anthropic, google-genai, groq, ollama all pinned as hard deps)
- **Key observation**: NO LangChain, NO OpenAI Agents SDK, NO Google ADK, NO Pydantic AI in core deps. They rolled their own `BaseChatModel` abstraction. LiteLLM NOT used in core (only in examples optional deps).
- **Agent loop**: `EventBus` (bubus) for events, Pydantic models for structured output, custom `MessageManager`

### browser-use/browser-harness (13.6k stars)
- **Philosophy**: "Delete the harness. Let the agent write what it needs."
- **Harness**: ~1k lines CDP direct — daemon + CDP WebSocket, NO framework
- **Browser layer**: cdp-use (their own lib), pure CDP
- **Models**: None bundled — caller provides model (designed for Claude Code / Codex to drive)
- **Key observation**: Explicitly anti-framework. Their blog "The Bitter Lesson of Agent Harnesses" argues all helpers are constraints.

### microsoft/magentic-ui (9.85k stars)
- **Harness**: Custom protocol (`SubAgentProtocol`) with streaming — NOT AutoGen despite the name. Pure Python protocols.
- **Browser layer**: Playwright + accessibility tree (not browser-use)
- **Models**: OpenAI (azure-identity in deps), FARA model
- **Key observation**: Microsoft rolled their own harness on top of Playwright despite previously shipping AutoGen.

### lmnr-ai/index (2.35k stars)
- **Harness**: BYO custom async loop — `Agent` class, `MessageManager`, `Controller` pattern
- **Browser layer**: Custom `Browser` class wrapping Playwright
- **Models**: OpenAI + Anthropic + Groq + Google GenAI
- **Key observation**: No framework. Custom loop with lmnr (Laminar) observability.
