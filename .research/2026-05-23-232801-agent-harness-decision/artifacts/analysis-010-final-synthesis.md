# analysis-010 — Final synthesis: harness + browser + model combo for the Layer-3 long-tail finisher

**Date:** 2026-05-24  
**Pass:** 2026-05-23-232801-agent-harness-decision  
**Mode:** Design  
**Built on:** 11 deep-dive analyses + 72 primary-source fetches + 2 GitHub-code surveys + 1 codebase-context artifact in this same pass.  
**Supersedes:** `2026-05-22-204703-autonomous-apply-north-star/analysis-005-codebase-context-correction.md` recommendation of "OpenAI Agents SDK in-process".

---

## 0. TL;DR — the three locked decisions

| Layer | Pick | Why (one line) |
|---|---|---|
| **Agent harness** | **Google ADK + LiteLLM** (already pinned `google-adk==1.23.0`) | Zero new deps, `root_apply_decider` is the live template, `before_tool_callback` blocks Submit at the Python layer, `RunConfig(max_llm_calls=N)` is a built-in circuit breaker |
| **Browser harness** | **BYO 6 thin Python tools over Playwright `Page` + raw CDP `Accessibility.getFullAXTree`** | AX-tree ≈ 300 input tokens vs. ≈ 2,635 for a screenshot — 6.7× cheaper per turn; CDP pierces Simplify's open shadow root for free; no new dep |
| **Model** | **`openai/gpt-5.4-mini` primary**, Claude Haiku 4.5 vision fallback only when AX-tree returns empty | τ2-bench **93.4%** vs. gpt-5-mini's 74.1%; ≈ $0.007/typical (15-turn) apply; vision branch costs ~$0.002 extra and only fires on shadow-DOM edge cases |

The full Layer-3 finisher lives in **`src/agents/apply_finisher/`** and is wired into `_run_application_flow` at one site — between the existing Simplify-autofill step and the existing field-scan step in `src/agents/apply_worker/browser.py:347-376`.

---

## 1. Re-grounding: what an "agent harness" actually is

(The single most important conceptual clarification of this pass — see `analysis-001-what-is-an-agent.md`.)

There are **three distinct layers**, and the prior pass conflated them:

1. **LLM SDK** — the HTTP client. `anthropic`, `openai`, `google-genai`. One call per invocation. Returns a single response. Examples in this repo: `openai==2.26.0`, `anthropic==0.96.0`.
2. **Agent harness** — the **loop runner**. Wraps the SDK in a while-loop that: (a) sends conversation + tool definitions, (b) parses tool-call requests from the response, (c) dispatches to registered tool functions, (d) appends tool results to the conversation, (e) loops until the model stops calling tools or a stop condition fires. Adds: hooks (pre/post tool), state, abort/timeout, structured output, observability. Examples surveyed: **Google ADK** (already in repo), OpenAI Agents SDK, Claude Agent SDK, LangChain/LangGraph, AWS Strands SDK, Vercel AI SDK.
3. **Browser harness** — the **tool implementation layer**. Provides the functions the agent harness's tool registry actually calls. None of the agent harnesses ship browser tools that match our use case. Examples surveyed: Playwright (already in repo), browser-use, Stagehand, Steel, Browserbase, Anthropic Computer Use, Microsoft Playwright MCP, vercel-labs/agent-browser.

**Anthropic's "Building Effective Agents" (Dec 2024) explicitly recommends starting WITHOUT a framework** when the task is well-bounded. The reason a framework still wins here is not the loop primitive (we could hand-roll it in ~150 lines) but the **hook system** — specifically the ability to *deny a tool call at the Python layer*, which is the only enforceable form of the "no Submit" rule. Layer-3 doesn't need a multi-agent orchestrator, persistence service, or graph runtime. It needs a one-agent, 6-tool, 5-25-turn loop with a denial hook.

That single feature — denial hooks — is why every harness we surveyed has one. The question collapses to: which harness's denial hook is best for us, accounting for the deps already paid and the models we want to use?

---

## 2. The agent-harness decision tree

### 2a. The candidates and their fates

| Harness | Verdict | Reason (one line) |
|---|---|---|
| **Google ADK** | **PICK** | Already pinned; `root_apply_decider/runtime.py` is the live template; `before_tool_callback` is a clean Python-layer denier; `RunConfig(max_llm_calls=N)` caps loops. |
| OpenAI Agents SDK | Acceptable but doesn't win | Cleaner ergonomics (one `await Runner.run()`) but ADK is already paid + already proven. Two harnesses in one process for no functional gain. (`analysis-005a-adk-vs-openai-sdk.md`) |
| Claude Agent SDK | Strong if we wanted Claude models | `PreToolUse` is the most expressive denier (returns structured `permissionDecisionReason` the model can use). But it's Claude-flavored — running it against OpenAI via MCP transport loses its distinctive features. (`analysis-004a-claude-vs-vercel.md`) |
| LangChain / LangGraph | Reject | 3× boilerplate over ADK for the same 2-node loop; no native pre-execution hook (must wrap the tool); large transitive dep tree conflicts with pinned `openai==2.26.0`. Earns its complexity at multi-agent orchestration scale, not at our single-loop scale. (`analysis-002-langchain-langgraph.md`) |
| AWS Strands SDK | Reject | Has the cleanest denier of all (`event.cancel_tool` on `BeforeToolCallEvent`) but adds `boto3`/`botocore` to core deps for no Bedrock usage; would be a third harness alongside ADK + bare `openai`. Marginal UX win, not worth onboarding a 1-year-old framework. (`analysis-002a-langchain-vs-strands.md`, `analysis-007-aws-strands-and-agentcore.md`) |
| Vercel AI SDK | Reject | TypeScript-only. Python interop = 3-6 week rewrite OR 1-2 week Node sidecar — no functional gain. (`analysis-006-vercel-ai-sdk.md`) |
| AWS Bedrock AgentCore Browser | Reject outright | Cloud-only, mandatory AWS account, per-session $, user data transits AWS — directly contradicts the `dist/`-to-Windows-users distribution model. (`analysis-007`) |

### 2b. Resolving the ADK-vs-Claude-Agent-SDK tension

Two of the deep-dives reached different verdicts:

- `analysis-005a` (ADK vs. OpenAI Agents SDK) → ADK wins on inertia.
- `analysis-004a` (Claude Agent SDK vs. Vercel) → Claude Agent SDK displaces *everything else*.

**These look contradictory but aren't, once you tie the harness to the model.** Claude Agent SDK's distinctive features — `PreToolUse` hooks, Anthropic computer-use ergonomics, structured `permissionDecisionReason` feedback the model interprets natively — are *Claude-flavored*. You can run it against OpenAI via the MCP-tool transport, but you lose the native ergonomics that made it win the head-to-head.

The model survey (`analysis-009-model-choice.md`) decisively picks `openai/gpt-5.4-mini` as primary by τ2-bench (93.4% vs. estimated 70-80% for Claude Haiku). Once that's locked, ADK + LiteLLM (the live-in-repo path to OpenAI) beats Claude Agent SDK + MCP-shim-to-OpenAI on every axis except hook expressiveness — and the hook expressiveness gap is small in practice for our single rule ("name starts with Submit → deny").

### 2c. What would FLIP the harness choice

The decision is hinge-pinned on the model choice. Flip the model and the harness flips:

- **If empirical tool-call reliability on real Greenhouse/Workday forms shows Claude Haiku 4.5 ≥ gpt-5.4-mini** (because τ2-bench is a proxy, not the actual task), → re-evaluate Claude Agent SDK with native Claude provider as the winner. The cost delta is ~3× input ($1.00 vs. $0.25 per MTok) but still well inside our $0.10/apply ceiling.
- **If browser-fill turns out to need image inputs in the primary loop** (not just the rare AX-tree-empty fallback), → Anthropic computer-use ergonomics matter much more, and Claude Agent SDK wins.

Build an eval harness *first*. Don't switch on speculation.

---

## 3. The browser-harness decision (boring but decisive)

From `analysis-008-browser-harness-landscape.md`:

### 3a. Why every off-the-shelf browser harness loses

| Harness | Disqualifier |
|---|---|
| browser-use (Python) | Does support `BrowserProfile(cdp_url=...)` (confirmed in `fetch-017`), but wraps it in an opinionated full agent loop with `cdp-use` dep and DOM+AX hybrid context exceeding our token budget. Owning the loop is the whole point of choosing ADK; deferring it to browser-use means two agent loops in the same process. |
| Stagehand | TypeScript-only. |
| Steel / Browserbase | Cloud-only, monthly $, breaks `dist/` distribution. |
| Anthropic Computer Use | Image-token cost (~2,635 tok per 1024×768) crushes the $0.10 ceiling. Designed to OWN a Linux VM screen — does not attach to an existing CDP browser with an extension. Confirmed in `fetch-014`. |
| Microsoft Playwright MCP | Confirmed `--cdp-endpoint http://localhost:9222` support and AX-tree-only snapshots (`fetch-015`). **The one real contender** — adopt later if/when we move to a pure MCP-tool-calling architecture. Blocked today by: (a) mandatory Node runtime on Windows `dist/`, (b) session-ownership fork with the existing Python apply-worker. |
| vercel-labs/agent-browser | Rust binary with subprocess-per-LLM-call overhead; the *pattern* (AX-tree snapshot with `@eN` refs) is what we want to steal, not the dep. Prior pass already concluded this. |

### 3b. The BYO win

`playwright==1.58.0` is already pinned. `Page.context.new_cdp_session()` gives us raw CDP access in-process, no new dep. We send `Accessibility.getFullAXTree` (`fetch-005`); we get back a serialized accessibility tree with `backendDOMNodeId` for every node, **including nodes inside Simplify's open shadow root** (confirmed by `fetch-004` + `fetch-005`).

Six tools, all wrapping methods that already exist:

```python
@function_tool
async def snapshot() -> str:
    """Return the AX-tree serialized as `@e1 button "Apply" / @e2 textbox "Why this company?" required / ...`."""

@function_tool
async def click(ref: str) -> str:
    """Click the element previously serialized as @ref. Errors if the ref is stale."""

@function_tool
async def type(ref: str, text: str) -> str:
    """Type text into the element previously serialized as @ref."""

@function_tool
async def select(ref: str, option: str) -> str:
    """Select an option from a dropdown serialized as @ref."""

@function_tool
async def wait_for(predicate: str, timeout_ms: int = 5000) -> str:
    """Wait for one of: 'network_idle', 'dom_stable', 'ref:@eN_visible'."""

@function_tool
async def goto(url: str) -> str:
    """Navigate the page. DO NOT use except to recover from a hard error — re-navigation kills Simplify."""
```

Estimated implementation: **~250 lines of Python** in `src/agents/apply_finisher/tools.py` + `ax_tree.py`. The `@eN` ref pattern is the load-bearing serialization choice (cheap tokens, stable across snapshots within a turn, semantically meaningful for the model).

---

## 4. The triple-defense no-Submit story in ADK terms

```
┌──────────────────────────────────────────────────────────────┐
│  DEFENSE 1 — snapshot filter (defense by ignorance)          │
│  Before serializing the AX-tree, drop any node where:        │
│    - role == "button" AND name matches /^submit|submit\s/i   │
│    - role == "button" AND name in {"Send Application",       │
│      "Apply Now", "Finalize", "Confirm Submission"}          │
│  The model literally cannot reference a ref it never saw.    │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  DEFENSE 2 — ADK before_tool_callback (denial hook)          │
│  def block_submit_callback(tool, args, tool_context):        │
│      if tool.name == "click":                                │
│          ref = args.get("ref", "")                           │
│          name = ax_tree_state.get_name(ref).lower()          │
│          if any(name.startswith(p) for p in SUBMIT_NAMES):   │
│              return {"error": "BLOCKED: submit-like target"} │
│      return None  # allow                                    │
│  Returning a dict short-circuits tool execution at the       │
│  Python layer. The model sees the error string and can       │
│  course-correct (or escalate to NEEDS_REVIEW).               │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  DEFENSE 3 — existing dry_run=True hardcoded (outer wrap)    │
│  scripts/process_apply_jobs.py:573                           │
│  apply_to_job(..., dry_run=True). The worker's wrapper       │
│  unconditionally bails to NEEDS_REVIEW. Even if Defenses 1   │
│  and 2 both fail, the Submit click would still not be the    │
│  worker's intent — and the SECURITY.md hard rule remains.    │
└──────────────────────────────────────────────────────────────┘
```

The `before_tool_callback` hook is documented in `fetch-005-google-adk-callbacks.md`. Returning a non-`None` dict skips tool execution entirely. This is enforcement at the Python layer — not at the prompt layer — and cannot be bypassed by a prompt-compliant LLM.

Additional safety from `RunConfig`:
- `max_llm_calls=40` — hard cap on loop turns (independent of any soft "stop after 25 turns" prompt guidance).
- After-call cost accounting (Section 5) gives a per-apply $ circuit breaker enforced in `after_tool_callback`.

---

## 5. Cost math, locked numbers

From `analysis-009-model-choice.md`:

| Scenario | Turns | Input tok | Output tok | gpt-5.4-mini cost | Trigger |
|---|---|---|---|---|---|
| Cheap apply (Greenhouse, 1-3 custom Qs) | 5 | 1.5K | 0.75K | **$0.0024** | typical |
| Normal apply (Greenhouse 5-Q or short Workday) | 15 | 4.5K | 2.25K | **$0.0071** | typical |
| Long-tail apply (Workday, multi-step Next) | 25 | 7.5K | 3.75K | **$0.0118** | upper |
| Runaway loop (caught by `max_llm_calls=40` first) | 40 | 12K | 6K | $0.019 | aborted |
| Circuit-breaker abort | — | — | — | **$0.10** | hard ceiling |

Implementation:
- `after_tool_callback` accumulates `prompt_tokens` + `completion_tokens` into `tool_context.state` (or a per-run object passed in via `RunConfig`).
- At the start of each turn, before dispatching another LLM call, the callback checks `cumulative_cost_usd > 0.10` and raises a `CostCeilingExceeded` to abort cleanly.
- Token totals flow into the existing `record_stage_cost_event(stage="APPLY", metadata={"model": "openai/gpt-5.4-mini", "prompt_tokens": ..., "completion_tokens": ...})` — already supported by `src/utils/cost_tracking.py:88-136` per-model rates via `COST_RATE_OPENAI_GPT_5_4_MINI_IN_USD` / `_OUT_USD` env vars.

A $0.10 ceiling is **8.5× our typical-case cost**. Plenty of headroom; a hard guard against pathological loops.

---

## 6. File layout for the Layer-3 finisher

```
src/agents/apply_finisher/                  # NEW
  __init__.py
  agent.py            # build_finisher_agent(model=...) — mirrors root_apply_decider/agent.py
  runtime.py          # run_finisher_for_apply(page, job_context) — mirrors root_apply_decider/runtime.py
  tools.py            # 6 function_tools wrapping Playwright Page + CDP
  ax_tree.py          # serialize_ax_tree() — @eN refs, snapshot filter for Submit-like nodes
  guardrails.py       # block_submit_callback, cost_ceiling_callback (after_tool)
  prompts.py          # FINISHER_INSTRUCTION — bakes in the Simplify gap-list
  schemas.py          # FinisherInvocationContract, telemetry shape, max-turn config
```

Change to existing code is **one site**:

```python
# src/agents/apply_worker/browser.py:347-376 (between Simplify autofill step and field scan)

from src.agents.apply_finisher.runtime import run_finisher_for_apply

# ... existing Simplify autofill click + 8s sleep ...

# NEW — Layer-3 long-tail finisher
try:
    finisher_result = await run_finisher_for_apply(
        page=playwright_page,
        job_hash=job_hash,
        source_url=source_url,
        max_turns=25,
        cost_ceiling_usd=0.10,
    )
    logger.info(
        "Finisher run completed: turns={} cost=${:.4f} outcome={}",
        finisher_result.turns,
        finisher_result.cost_usd,
        finisher_result.outcome,
    )
except Exception as exc:
    logger.warning("Finisher run failed (non-fatal): {}", exc)
    finisher_result = None

# ... existing field scan + confidence + screenshot capture ...
```

The finisher MUST NOT change:
- `dry_run=True` hardcoded path (`scripts/process_apply_jobs.py:573`)
- The NEEDS_REVIEW outcome (the wrapper always sets it; the finisher just makes "review" shorter)
- The Simplify-first strategy (autofill click stays Step 6; finisher is Step 6.5)
- The CDP-attach pattern (`browser.contexts[0]`, never `chromium.launch()`)

---

## 7. What the user asked me to internalize about agents

These are the conceptual clarifications I now have, that I didn't have when I started this pass (from `analysis-001-what-is-an-agent.md` + the immersion fetches):

1. **An agent is an LLM that controls its own while-loop.** The single test that separates an agent from a workflow is whether `llm_should_continue()` is the model deciding, not your code. RAG, chatbots, structured-output one-shots (like our existing resume-tailor) — none of these are agents. A `for field in unresolved_fields: ask_llm(field)` script is not an agent. The Layer-3 finisher is one.
2. **An agent harness is the loop runner, not the LLM client.** `anthropic` SDK and `openai` SDK are HTTP clients — they make one call per invocation. The harness wraps them in: send → parse tool calls → execute tools → append results → repeat. ADK is one such harness. The prior pass's analysis-005 conflated "Instructor + OpenAI" (one-shot structured output) with the loop-runner role; it isn't.
3. **The five Anthropic workflow patterns (prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer) usually beat a true agent.** The existing resume-tailor is evaluator-optimizer (tailor → review → re-tailor). The Layer-3 finisher cannot be — the form is dynamic, the field count varies, the path is not knowable in advance. That's why it has to be a true agent.
4. **Anthropic explicitly recommends starting WITHOUT a framework.** The reason we don't take that advice here is the *denial hook* — we cannot enforce "no Submit" with prompts alone. The hook is the one framework feature whose absence is unacceptable.
5. **Tool calling is the same protocol everywhere.** Tools defined for Claude work in OpenAI's format with a small schema shim. This is what makes ADK + LiteLLM + OpenAI a valid path — ADK speaks tool calling, LiteLLM does the provider translation.
6. **"Cheap + autonomous + can run long" implies five concrete harness requirements**, all of which ADK has:
   - Cheap model selection (`LiteLlm(model="openai/gpt-5.4-mini")`)
   - Per-step token tracking (`after_tool_callback` reads usage from response)
   - Hard turn cap (`RunConfig(max_llm_calls=40)`)
   - Cost circuit breaker (cumulative-cost check in `after_tool_callback`)
   - Clean abort to a known terminal state (NEEDS_REVIEW)

---

## 8. Updated open decisions for the user

These supersede the open questions in the prior pass's `analysis-004` and `analysis-005`:

1. **Eval harness before LLM-call-one.** Record DOM + AX-tree + screenshot fixtures from 10 real applies (post-Simplify) — Greenhouse ×3, Workday ×3, Lever ×2, iCIMS ×1, Ashby ×1. Replay them against the finisher offline. Without this, every model/harness comparison is speculation. **This is the single highest-leverage thing to build first.**
2. **The dormant `pi_coding_agent_*` schema fields** (`src/agents/resume_tailor/schemas.py:439-477`). With ADK confirmed as the canonical agent harness for this repo (decider + finisher both use it), the pi-coding-agent subprocess scaffolding has even less reason to exist. Propose: open a follow-up issue to delete those fields and consolidate on ADK + LiteLLM.
3. **Per-apply LLM cost ceiling number.** `$0.10` is the recommended ceiling (8.5× typical). User confirms or sets a different value.
4. **`gpt-5.4-mini` vs. `gpt-5-mini` as the existing decider model.** The decider currently uses `openai/gpt-5-mini` (`src/agents/root_apply_decider/agent.py:19`). The finisher will use `gpt-5.4-mini` for tool-calling reliability. Worth a follow-up: should the decider also upgrade? The cost delta on a 1-shot decider call is negligible; the τ2-bench gap suggests yes.
5. **Where does the user want the finisher's per-field telemetry stored?** Three options: (a) extend `apply_runs` with `finisher_turns_used`, `finisher_cost_usd`, `finisher_fields_filled`; (b) add a new `finisher_runs` table 1:1 with `apply_runs`; (c) JSON blob in `apply_runs.confidence_report_json`. Recommend (a) — small, queryable, matches existing telemetry shape.

---

## 9. What's still RIGHT from the prior research pass

Carry forward unchanged from `2026-05-22-204703-autonomous-apply-north-star/`:

- **Strategy A (Simplify-first, agent-second).** Simplify still does ~90% of fields for free. The agent does the long tail.
- **The "AX-tree with `@eN` refs" pattern from agent-browser.** Steal the idea; skip the dep. Confirmed in this pass: 6.7× cheaper tokens vs. screenshots.
- **The system prompt that bakes in Simplify's known-gap list.** `analysis-002-simplify-capability-gap.md` from the prior pass is still the right reference for what to include.
- **NEEDS_REVIEW hand-off + human submits.** SECURITY.md rule, unchanged.
- **Per-field telemetry** to measure what each layer (Simplify / LLM / human) actually filled.

---

## 10. Three-bullet bottom line

- **Ship issue #59's Apply button + modal + `POST /api/jobs/{hash}/apply` endpoint** as the user's authorized trigger. (Independently shippable; doesn't depend on Layer 3.)
- **Build Layer 3 as `src/agents/apply_finisher/` — a second ADK agent**, mirroring `root_apply_decider/runtime.py`, using 6 in-process Python tools over Playwright + CDP `Accessibility.getFullAXTree`, with `before_tool_callback=block_submit_callback` + `RunConfig(max_llm_calls=40)`, primary model `openai/gpt-5.4-mini` via the existing `build_openai_litellm_model` factory.
- **Build the eval harness in the same PR** — 10 recorded fixtures, replay path, regression-on-CI. Without it, every model/harness tweak is speculation.
