# Claude Agent SDK vs Vercel AI SDK: Head-to-Head for Python Apply-Worker
## Comparative Analysis

**Date:** 2026-05-24  
**Repo:** agentic-job-applier

---

## The Core Comparison

Both SDKs bring Anthropic models to the table. The decisive differences are language, guardrail architecture, and ecosystem fit.

| Dimension | Claude Agent SDK | Vercel AI SDK |
|-----------|-----------------|---------------|
| Language | Python + TypeScript | TypeScript only |
| Install | `pip install claude-agent-sdk` | `npm install ai` |
| Loop primitive | `query()` async generator | `generateText()` / `ToolLoopAgent` |
| Pre-tool interception | `PreToolUse` hook (central, before execution) | Inside tool `execute` (per-tool, after model decides) |
| Provider lock-in | Claude only | OpenAI, Anthropic, Google, Bedrock, 50+ others |
| Interop cost for Python worker | Zero | 3-6 weeks rewrite or 1-2 weeks sidecar |

---

## Why Claude Agent SDK Over Vercel AI SDK (For This Project)

**1. Python-native.** The apply-worker is Python. Claude Agent SDK ships a first-class Python package. Vercel AI SDK is TypeScript-only with no Python port.

**2. Guardrail architecture is superior.** `PreToolUse` hooks intercept any tool call before execution via a single registered callback. No per-tool patching required. The `permissionDecision: "deny"` + `permissionDecisionReason` pattern gives Claude explicit feedback so it doesn't retry fruitlessly.

**3. CDP integration stays in-process.** All 6 browser tools are Python functions wrapping CDP/Playwright. With Claude Agent SDK, they register as an in-process MCP server and run in the same event loop. With Vercel AI SDK, they'd need to be exposed over a cross-process boundary.

---

## Why Claude Agent SDK Over OpenAI Agents SDK

**1. Anthropic computer-use ergonomics.** Claude is trained for browser task completion; Anthropic publishes computer-use as a first-class beta feature (`computer-use-2025-11-24` header). OpenAI Agents SDK uses the Responses API but has weaker native computer-use ergonomics.

**2. Claude tool-calling strength.** Claude Sonnet and Opus are consistently top performers on tool-use benchmarks. For a 6-tool, 5-25 turn apply loop, model quality directly determines success rate and cost (fewer wasted turns = lower $/apply).

**3. Hook parity.** OpenAI Agents SDK has `Runner.with_hooks()` / guardrail callbacks, but Claude Agent SDK's `PreToolUse` hook is more expressive: it returns structured `permissionDecision` and `permissionDecisionReason` that Claude sees as tool feedback, not just a hard exception.

**4. No vendor switch.** The repo already has `anthropic==0.96.0`. Claude Agent SDK is the natural evolution path — same API key, same model IDs, same provider.

---

## Why Claude Agent SDK Over Google ADK

**1. Python quality, not just presence.** Google ADK is Python but its loop control and hook system are less ergonomic for a tight tool-calling loop than Claude Agent SDK's `PreToolUse` / `PostToolUse` pattern.

**2. Claude models outperform Gemini for form-filling tasks.** Computer-use and structured web navigation benchmarks consistently show Claude ahead.

**3. No Anthropic-specific ergonomics.** ADK calls Gemini models by default. Using it with Claude requires a wrapper adapter — adding friction vs Claude Agent SDK which is designed for Claude natively.

---

## Verdict

**Claude Agent SDK displaces both OpenAI Agents SDK and Google ADK as the recommended harness.** Vercel AI SDK is effectively out due to language mismatch.

The winning combination for this project: **Claude Agent SDK (Python) + custom in-process MCP browser tools + `PreToolUse` hook for submit guardrail**.

---

## Sources

- analysis-004-claude-agent-sdk.md
- analysis-006-vercel-ai-sdk.md
- fetch-002-claude-agent-sdk-custom-tools.md
- fetch-003-claude-agent-sdk-hooks.md
- fetch-004-claude-agent-sdk-permissions.md
- fetch-005-claude-agent-sdk-sessions.md
- fetch-006-anthropic-computer-use.md
