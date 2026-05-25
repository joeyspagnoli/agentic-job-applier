# local-001 — Current apply pipeline state (codebase pass, May 2026)

**Purpose:** Ground the harness-selection decision in what the repo actually does today, so subsequent analyses cite real file paths and don't propose changes that conflict with shipped behavior.

---

## 1. The apply-worker pipeline as it exists today

### Entry points

| Path | Role |
|---|---|
| `scripts/process_apply_jobs.py` (937 LOC) | Standalone CLI + supervisor-importable `run_apply_loop()` poll loop |
| `src/agents/apply_worker/browser.py:142` | `apply_to_job(...)` — the one-shot per-job entry called by the loop |
| `src/agents/apply_worker/browser.py:241` | `_run_application_flow(...)` — the sequential 8-step flow (THIS is where Layer-3 slots in) |

### The 8-step flow (`browser.py:241-442`)

```
1. Navigate to source_url (skip if already there — re-navigation breaks Simplify)
2. wait_for_load_state("networkidle") with 30s timeout
3. ATS-platform detection (Greenhouse/Lever/Workday/iCIMS/Ashby/SmartRecruiters) — diagnostic only
4. Wait for Simplify shadow root + Autofill button via JS poll (≤45 s)
5. Upload tailored PDF to file input  (BEFORE clicking Simplify — Simplify's click can nav away)
6. Pierce shadow root, click Autofill button (defended against Submit-like aria-labels)
7. Sleep 8 s, scan unresolved fields (field_scanner.py), compute confidence (confidence.py)
8. Save screenshot + DOM + unresolved_fields.json → return ApplyRunResult(outcome=NEEDS_REVIEW)
```

**Step 6 → Step 7 is where the long-tail finisher (Layer 3) goes.** Everything before it is "Simplify does 90%." Everything after is "human reviews and clicks Submit."

### Key invariants (do not change)

- **`dry_run=True` hardcoded** in `process_apply_jobs.py:573` → `apply_to_job(..., dry_run=True)`. Even when the new agent fills more fields, the outer wrapper still forces `NEEDS_REVIEW`. (SECURITY.md.)
- **CDP attach, do not launch.** `browser.py:180`: `pw.chromium.connect_over_cdp(cdp_url)`. The Chrome instance is launched OUTSIDE this codebase (typically a user-launched Chrome with Simplify Copilot loaded + `--remote-debugging-port=9222`). Anything that calls `chromium.launch()` would orphan Simplify and break the flow.
- **Use `browser.contexts[0]`**, not a new context. Same reason — the Simplify extension is wired into the existing context, not a fresh isolated one (`browser.py:190`).
- **Use `page.context.new_cdp_session()` for raw CDP commands.** Playwright's `Page` exposes this; we already have it. Future tool layer should use this to call `Accessibility.getFullAXTree` directly.
- **Simplify's autofill aria-labels** (`browser.py:41`): `"Autofill"`, `"Autofill all fields with AI"`, `"Fill"`, `"Continue filling"`. Forbidden labels (`browser.py:51`): `"Submit Application"`, `"Submit"`.

### Telemetry shape (must continue to work)

- `record_stage_cost_event(db, stage="APPLY", job_hash, run_id, metadata={...})` is the cost write (`src/utils/cost_tracking.py:182`).
- When metadata carries `model`, `prompt_tokens`, `completion_tokens`, the cost is computed from `COST_RATE_<MODEL>_IN_USD` / `_OUT_USD` env vars (`cost_tracking.py:88-136`). Else falls back to a flat `COST_RATE_APPLY_USD` (`cost_tracking.py:139-179`).
- **Implication:** every LLM call in the Layer-3 finisher MUST flow token counts through to this metadata so the dashboard cost number stays accurate.

---

## 2. Existing agent patterns in the repo (precedents to follow or avoid)

### 2a. The root_apply_decider — Google ADK + LiteLLM + OpenAI (LIVE in production)

- `src/agents/root_apply_decider/agent.py:9` — `from google.adk.agents import Agent`
- `src/agents/root_apply_decider/agent.py:204` — `Agent(name=..., model=LiteLlm(model="openai/gpt-5-mini"), instruction=...)`
- `src/agents/root_apply_decider/runtime.py:8-11` — `Runner(...)` + `InMemorySessionService(...)` + `types.Content(role="user", parts=[Part(text=...)])`
- `src/agents/shared/model.py:13-38` — `build_openai_litellm_model(model_name="openai/gpt-5-mini")` is the canonical model factory; checks `OPENAI_API_KEY`; raises if `litellm` missing.

**This is the proof that Google ADK + LiteLLM + OpenAI gpt-5-mini is a real, working pattern in this repo today.** A new browser agent that follows the same shape (just adds tools + a `before_tool_callback`) is the smallest-surface graft.

### 2b. The resume_tailor — Instructor + OpenAI (LIVE in production)

- `src/agents/resume_tailor/llm.py:25-29` — `import instructor`, `from openai import OpenAI`
- `src/agents/resume_tailor/llm.py:143-145` — `instructor.from_openai(OpenAI(), mode=instructor.Mode.RESPONSES_TOOLS)`
- `src/agents/resume_tailor/llm.py:34-35` — default models: `openai/gpt-5.4` for tailor/trim, `openai/gpt-5-mini` for reviewer.
- `src/agents/resume_tailor/llm.py:45-59` — `LlmCallResult(parsed, prompt_tokens, completion_tokens, total_tokens, model)` is the token-bundle pattern other code expects.

**This is one-shot structured-output, NOT a tool loop.** Useful as the pricing/telemetry precedent (token usage flows to `LlmCallResult` → `record_stage_cost_event`), not as a loop pattern.

### 2c. Empty modules — pi-style abandoned

- `src/agents/resume_tailor_pi/` and `src/agents/resume_review_pi/` exist but contain only `__pycache__` directories. **Vestigial dirs from an abandoned refactor toward "pi-style" agents** — visible-but-dead. Should not be confused with anything live.

### 2d. Schema scaffolding for `pi-coding-agent` (dormant)

- `src/agents/resume_tailor/schemas.py:439-477` — `TailorInvocationContract` reserves 5 fields for a subprocess invocation of `pi-coding-agent`:
  - `pi_coding_agent_command_argv`, `pi_coding_agent_command`, `pi_coding_agent_workspace_dir`, `pi_coding_agent_timeout_seconds`, `pi_coding_agent_env_allowlist`
- `DEFAULT_PI_CODING_AGENT_TIMEOUT_SECONDS = 14_400` (4 hours)
- **But:** the active runtime in `llm.py` does NOT shell out to `pi-coding-agent`. The fields are scaffolding for a future "we might subprocess Node" pivot that never happened.

---

## 3. Already-installed agent toolchain (the dep budget is partly paid)

`pyproject.toml` Python deps already pinned (`==` per the project's pinning rule):

```
anthropic==0.96.0
openai==2.26.0
google-adk==1.23.0
google-genai==1.60.0
litellm==1.82.1
instructor==1.15.1
playwright==1.58.0
pydantic==2.12.5
```

Implications for harness choice:

| Harness | Already paid? | Existing-usage precedent |
|---|---|---|
| Google ADK | **Yes** (`google-adk==1.23.0`) | `root_apply_decider` is in production |
| OpenAI Agents SDK | No (would add `openai-agents`) | But `openai==2.26.0` is the underlying SDK and IS in use |
| Claude Agent SDK | No (would add `claude-agent-sdk`) | But `anthropic==0.96.0` is paid; no Claude usage today |
| LangChain/LangGraph | No (large transitive dep cost) | No precedent |
| Strands | No (single repo, smaller dep tree) | No precedent |
| Vercel AI SDK | No — TS, would require Node sidecar | Worker is pure Python |

---

## 4. Constraints that bind the harness choice

| Constraint | Source | Implication |
|---|---|---|
| Pin all deps with `==`, no ranges | `feedback_dependency_pinning.md` (memory) | Pick libraries with stable APIs; bare-`openai` or bare-`anthropic` is safer than fast-moving framework |
| Self-hosted, distributed via `dist/` to Windows users | `project_dist_onboarding.md` (memory) | NO cloud-only agent services (AgentCore, Browserbase, Steel as a service) |
| Pure Python worker | `scripts/process_apply_jobs.py` | Picking Vercel AI SDK requires Node sidecar; default reject |
| Hard-disabled auto-submit | `SECURITY.md` + `dry_run=True` hardcoded | Triple-defense (snapshot filter / harness guardrail / outer dry-run) needed |
| Must attach to existing CDP-controlled Chrome with Simplify extension | `browser.py:180` | Browser harnesses that launch their own Chrome are non-starters |
| Cost target $0.01-0.10/apply | Prior research north-star synthesis | Cheap model (gpt-5-mini class) + cheap snapshot (AX-tree, ~300 tok) + tight loop (≤25 turns) |
| 5-25 turn tool-calling loop, 6 tools | `analysis-001`/`analysis-004` (prior pass) | Need: hooks (no-Submit guardrail), token-usage telemetry, abort, structured-output for tool calls |

---

## 5. Where Layer 3 lands in the file tree (anticipated)

Following the existing per-agent layout (`src/agents/<agent_name>/`):

```
src/agents/apply_finisher/        # NEW — the Layer-3 long-tail finisher
  __init__.py
  agent.py                          # Agent definition (instruction + tools)
  runtime.py                        # Runner / loop / per-apply session
  tools.py                          # 6 tool functions over Playwright + CDP
  ax_tree.py                        # snapshot + @eN-ref serializer
  guardrails.py                     # before_tool_callback / Guardrail / hook for "no Submit"
  prompts.py                        # system prompt with Simplify gap-list
  schemas.py                        # FinisherInvocationContract, telemetry shape
```

`src/agents/apply_worker/browser.py` would be modified at one site only: after Step 6 (Simplify autofill click + 8 s wait) and before Step 7 (field scan + confidence), insert one call to `apply_finisher.runtime.run_finisher(page, job_context)`.

---

## 6. What does NOT need to change

- The apply-loop polling, claim, retry, backoff, cost-telemetry, ntfy notification — all in `scripts/process_apply_jobs.py`. Untouched.
- The NEEDS_REVIEW outcome semantics, the `apply_handoffs` table, the human-review UI route — untouched.
- The Simplify shadow-root pierce + Autofill click — untouched; it's still the 90% strategy.
- The dry-run hard rule — UNCHANGED. The finisher hands back, never submits.

---

## 7. Open repo questions for the synthesis to answer

1. **Use Google ADK (already in repo) for the new finisher, or pick a different harness?** ADK has the strongest inertia argument: zero new deps, the `root_apply_decider` is the working precedent, LiteLLM bridge to OpenAI is proven. The question is whether ADK's tool-calling loop and `before_tool_callback` hook are ergonomic enough for a 6-tool, 5-25-turn loop, or whether a more loop-focused harness (OpenAI Agents SDK / Claude Agent SDK) is better.
2. **Bare `openai` SDK + ~150-line hand-rolled loop**, no agent harness at all? Anthropic's "Building Effective Agents" explicitly recommends starting WITHOUT a framework. The repo's dep-pinning + dist-distribution constraints argue for the smallest dep surface.
3. **Resolve the dormant `pi_coding_agent_*` schema fields** — keep as scaffolding, wire them up for the new finisher (would commit to a Node sidecar pattern), or remove? This decision is adjacent but not blocking.
4. **Reuse `root_apply_decider/runtime.py` patterns**? The `Runner` + `InMemorySessionService` + `types.Content` dance is in place. New finisher would either reuse it or re-implement it depending on harness choice.
