# forum-retry-005-claude.md
# Source: Web search + official docs
# Date: 2026-05-24

## From team400.ai — "Handling Tool Calls in the Claude Agent SDK"
URL: https://team400.ai/blog/2026-04-claude-agent-sdk-handle-tool-calls

"When a handler returns isError: True, the agent loop continues. Claude sees the error as data and can retry or adapt. Always catch exceptions and return isError: True for recoverable failures."

"The isError: True return is the single most important pattern in custom tool development."

---

## From digitalapplied.com — "Claude Agent SDK: Complete Production Patterns Guide 2026"
URL: https://www.digitalapplied.com/blog/claude-agent-sdk-production-patterns-guide

"Automatic retries on a looped agent multiply cost. Either require a user-initiated resume, or route trips to a human-in-the-loop review queue before continuing."

---

## GitHub Issue #812 — "Agent SDK should handle 429 rate limits gracefully instead of crashing"
URL: https://github.com/anthropics/claude-agent-sdk-python/issues/812

SDK treats rate limit errors as fatal exceptions rather than backing off and retrying. This can "destroy multi-turn autonomous agent sessions that accumulate work." Key production pain point for long-running agents.

---

## Medium — "Claude Agent SDK Deep Dive: What It Means to Use Claude Code as a Library"
URL: https://medium.com/@shivanshmay2019/claude-agent-sdk-deep-dive-what-it-means-to-use-claude-code-as-a-library-773aea121787

SDK is relatively new (renamed from Claude Code SDK late 2025). v0.1.48 Python, v0.2.71 TypeScript as of March 2026. Production patterns still emerging.

---

## Key Signals

- No HackerNews threads specifically about Claude Agent SDK retry experience found (SDK is too new for deep community discussion)
- Core retry mechanism is simple (isError: True) but relies entirely on Claude's judgment — no retry budget or backoff built in
- Rate limit crashes are a known unresolved production pain point
- The SDK requires external infrastructure for "durable execution, multi-agent coordination, and retry logic" per documentation
