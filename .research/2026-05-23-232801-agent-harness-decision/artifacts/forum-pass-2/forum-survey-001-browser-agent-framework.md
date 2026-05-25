# Forum Survey 001 — Best Agent Framework for Browser Automation

Date: 2026-05-24
Query: "best agent framework browser automation Python 2026 reddit production"
Source: firecrawl.dev/blog/best-browser-agents (fetched)

## Key Findings

### Framework Popularity
- **Playwright** remains most-used overall (45.1% adoption among QA professionals) but is not an agent framework — it's the browser layer
- **browser-use**: 89.1% WebVoyager success rate, 50k+ stars, fastest-growing AI project 2025-2026
- **Skyvern 2.0**: 85.85% WebVoyager, best on form-filling ("WRITE") tasks

### Production Pattern
"Most developers pair agent frameworks with managed infrastructure (Browserbase, Firecrawl) + human-in-the-loop checkpoints."

### Internal harnesses of surveyed tools:
- **browser-use**: Playwright + DOM distillation + LiteLLM for model agnosticism → **custom loop**
- **Stagehand**: act/extract/observe primitives on Playwright → TypeScript-first, **custom loop**
- **Skyvern**: planner-actor-validator loop → **custom loop**
- **Agent Browser (Vercel)**: Rust + accessibility tree → CLI-first, **custom loop**

### Key Quote
"Many production systems use Playwright for the 80% of steps that are predictable and Stagehand or Browser Use for the 20% that require AI understanding."

This directly matches our architecture: Playwright tools for deterministic form steps, LLM (via Google ADK) for the 20% that require reasoning.

## Framework-Specific Findings

### LangGraph (most enterprise production traction)
From channel.tel analysis: "Uber, Klarna, LinkedIn, JPMorgan, and 400+ companies run it in production." Klarna AI handles 85M users support.
BUT: This is for conversational/workflow agents, not browser automation specifically.

### browser-use internal model routing
Uses LiteLLM NOT in the core dep (examples only). Core uses direct SDKs (openai, anthropic, google-genai pinned). This suggests LiteLLM for routing is a preference but not mandatory.

## Production Concerns

1. **Reliability variability**: 30-89% success rate range across tools for browser tasks
2. **Non-determinism**: developers prefer script brittleness to LLM non-determinism for critical steps
3. **Security**: unmitigated agents fall for 24% of prompt injection attacks
4. **HITL is now standard**: human-in-the-loop validation considered essential for production

## Framework Gap

The article from channel.tel identifies: "the framework handles 30% of what you need for production. The other 70% is infrastructure outside the framework: tool management at scale (30+ tools), persistent memory, pre-deployment testing, production monitoring, prompt versioning."

This supports not over-investing in harness selection — the real work is in the 70% around it.
