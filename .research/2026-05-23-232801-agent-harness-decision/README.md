# Pass: 2026-05-23-232801 — Agent harness, browser harness, and model selection for Layer-3

**Date:** 2026-05-23 → 2026-05-24  
**Mode:** Design  
**Built on:** `2026-05-22-204703-autonomous-apply-north-star/` (corrects analysis-005 of that pass)

## Why this pass exists

User feedback (verbatim, 2026-05-23): *"you seem to have a hard time understanding what an agent harness is"*. The prior pass jumped to OpenAI Agents SDK without rigorously surveying the landscape or grounding in primary-source agent fundamentals. This pass re-grounds, surveys all 6 frameworks the user named (LangChain, Google ADK, OpenAI Agents SDK, Claude Agent SDK, Vercel AI SDK, AWS Strands+AgentCore), separately surveys the browser-harness layer, and locks the model choice.

## The locked picks

| Layer | Pick |
|---|---|
| Agent harness | **Google ADK + LiteLLM** (already in repo at `google-adk==1.23.0`; `root_apply_decider` is the live template) |
| Browser harness | **BYO 6 Python tools over Playwright Page + CDP `Accessibility.getFullAXTree`** (already-paid `playwright==1.58.0`; ~250 LOC; AX-tree ≈ 300 tok vs. ~2,635 tok for a screenshot) |
| Primary model | **`openai/gpt-5.4-mini`** (τ2-bench 93.4% vs. gpt-5-mini's 74.1%; ~$0.007/typical apply) |
| Vision fallback | **`claude-haiku-4-5-20251001`** only on empty AX-tree |

## Read order

1. **`artifacts/analysis-010-final-synthesis.md`** — the centerpiece. Cross-references everything else.
2. **`artifacts/analysis-001-what-is-an-agent.md`** — the agent/harness/SDK definitions and re-grounding.
3. **`artifacts/local-001-current-apply-pipeline.md`** — what the codebase actually does today; constraints binding the choice.
4. Per-harness deep dives: `analysis-002` (LangChain), `analysis-003` (OpenAI Agents SDK), `analysis-004` (Claude Agent SDK), `analysis-005` (Google ADK), `analysis-006` (Vercel AI SDK), `analysis-007` (AWS Strands + AgentCore).
5. Head-to-heads: `analysis-002a` (LangChain vs. Strands), `analysis-004a` (Claude vs. Vercel), `analysis-005a` (ADK vs. OpenAI Agents SDK).
6. **`artifacts/analysis-008-browser-harness-landscape.md`** — why BYO over Playwright+CDP wins; Playwright MCP as the deferred upgrade.
7. **`artifacts/analysis-009-model-choice.md`** — pricing table, τ2-bench numbers, cost math, circuit-breaker $.
8. Raw evidence in `fetch-*.md` (72 files), `gh-*.md` (2 files).

## Source count

11 analysis docs + 72 primary-source web fetches + 2 GitHub-code surveys + 1 codebase-context artifact = 86 files in `artifacts/`.

## Decision delta from prior pass

- **Prior pass picked OpenAI Agents SDK in-process.** This pass picks **Google ADK** instead — because the prior pass missed that ADK is already in `pyproject.toml` and already proven at `src/agents/root_apply_decider/`. Inertia + zero-new-deps + an already-templated `Runner + InMemorySessionService` pattern beat OpenAI Agents SDK's marginally cleaner ergonomics.
- **Model goes from `gpt-5-mini` to `gpt-5.4-mini`** because τ2-bench shows a 19-point reliability gain on tool calling at 3× the input cost (still 14× under the $0.10 ceiling).
- **Browser layer is unchanged in direction** (BYO over Playwright + CDP) but now confirmed against primary-source browser-use / Stagehand / Steel / Browserbase / Computer-Use / Playwright-MCP docs.
