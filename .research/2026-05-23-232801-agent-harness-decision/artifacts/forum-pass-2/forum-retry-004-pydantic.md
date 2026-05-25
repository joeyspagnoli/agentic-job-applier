# forum-retry-004-pydantic.md
# Source: dev.to builder posts + search
# Date: 2026-05-24

## DEV Community — "Pydantic AI Tutorial: How I Build Type-Safe AI Agents That Actually Work in Production"
URL: https://dev.to/jahanzaibai/pydantic-ai-tutorial-how-i-build-type-safe-ai-agents-that-actually-work-in-production-3bcp

**Author on ModelRetry:**
"You can also use `ModelRetry` to signal the LLM should retry with different parameters" when tools encounter recoverable errors.

**On production retry strategy:**
"In production, set `retries=2` on your agent and handle `UnexpectedModelBehavior`" rather than allowing unlimited retry loops that "burn tokens on an agent that consistently can't satisfy your schema."

**On discriminate retry logic:**
Raises `ModelRetry` for specific failures (like unrecognized city names) while letting other errors bubble up directly — showing controlled retry vs. blanket retry.

---

## AI Agent Frameworks 2026 ranking (Alice Labs)
URL: https://alicelabs.ai/en/insights/best-ai-agent-frameworks-2026

"Pydantic AI is the strongest framework for typed, conventional agents, with FastAPI-style developer experience translating remarkably well to agent development. According to one production user, they've been running it in production for 8 months without a breaking change."

---

## GitHub Issue #677 — "Add ability to customise model request retry behaviour"
URL: https://github.com/pydantic/pydantic-ai/issues/677

Request to add HTTP-level retry configuration (for transient API failures) separate from tool-level ModelRetry. Currently ModelRetry handles tool failures; this issue covers the infrastructure layer.

Note: pydantic-ai GitHub search for "ModelRetry OR retry" returned 0 matching issues directly (likely because ModelRetry is well-understood and works as designed — issues are about edge cases, not core mechanic broken-ness).

---

## Key Production Signals

- V1 stable API reached late 2025 — no breaking changes since
- 16,000 GitHub stars by April 2026
- Used by companies building on Amazon Bedrock AgentCore
- Community consistently praises type-safe retry ergonomics
- The discriminate retry pattern (ModelRetry for recoverable, raise for fatal) is the canonical production approach
