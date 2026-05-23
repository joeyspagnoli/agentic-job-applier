# analysis-004 — North-star synthesis: how all three research threads interleave into "user clicks Apply, the pipeline finishes the rest"

**Date:** 2026-05-22  
**Built on:** analysis-001 (agent-browser), analysis-002 (Simplify), analysis-003 (pi-mono), plus all 16 evidence artifacts in this pass.  
**Purpose:** Think hard about how the Apply button (issue #59) becomes a full autonomous-apply on the user side, and where each research finding plugs in. Not an implementation plan — a strategy + architecture narrative that locks down the load-bearing decisions and exposes the genuinely-open questions.

---

## The single picture

```
                                    JobsPage (issue #59)
                                            │
                                  user clicks [ Apply ]
                                            │
                       ┌────────────────────┴────────────────────┐
                       │   tailor_run.status === SUCCESS?         │
                       └────────────────────┬────────────────────┘
                                            │
                  no ────────────────────┐  │  ┌──── yes
                                         ▼  │  ▼
                                   <NotTailoredModal>
                                   ├ Yes, tailor first ──► POST /api/jobs/{h}/tailor
                                   │                       wait for SUCCESS
                                   │                       ▼
                                   └ No, skip ────────────► POST /api/jobs/{h}/apply
                                                            │
                                                            ▼
                                              ┌─────────────────────────────┐
                                              │  apply-worker (existing)     │
                                              │  scripts/process_apply_jobs  │
                                              │   ├ open Chrome via CDP      │
                                              │   ├ upload tailored PDF      │
                                              │   ├ click Simplify Autofill  │
                                              │   ├ ~90% of fields filled    │
                                              │   ▼                          │
                                              │  ┌────────────────────────┐  │
                                              │  │  LONG-TAIL FINISHER    │  │  <-- THE NEW THING
                                              │  │  (LLM browser agent)   │  │
                                              │  │   ├ AX-tree snapshot   │  │
                                              │  │   ├ pick unfilled refs │  │
                                              │  │   ├ click/type/select  │  │
                                              │  │   ├ stop at Submit     │  │
                                              │  └──────────┬─────────────┘  │
                                              │             ▼                │
                                              │  outcome = NEEDS_REVIEW      │
                                              │  capture screenshot+DOM      │
                                              └─────────────┬────────────────┘
                                                            ▼
                                                user reviews + clicks Submit
                                                  (hard rule: SECURITY.md)
```

The architecture has four layers. **Layers 0, 1, 2 already exist.** Layer 3 (the "long-tail finisher") is the entire piece of new engineering, and it's where every research finding from this pass lands.

---

## Layer-by-layer interleaving

### Layer 0 — The Apply button (issue #59)
*Purely a UI/backend change.* No browser-agent research needed.
- Apply button in `TailoredResumeCell` next to the existing Tailor button.
- Modal when no tailor run exists yet — "Yes, tailor my resume" chains tailor → apply.
- Backend: new `POST /api/jobs/{hash}/apply` endpoint that mirrors the tailor enqueue pattern (returns run id, status). Plus `GET /api/apply-runs/{id}` for polling.

This is the user's authorized one-click entry into the autonomous flow. **No autonomous claim works without this trigger** — the worker today only polls reviewed jobs in the background; there's no user-driven hook.

### Layer 1 — Tailor (already exists)
`run_tailor_review_pipeline` → tailored PDF in `data/tailored_resumes/<job_hash>/`. No change needed. The Apply button waits for `tailor_run.status === SUCCESS` and then triggers Layer 2.

### Layer 2 — Apply orchestration (mostly exists)
`scripts/process_apply_jobs.py` + `src/agents/apply_worker/browser.py` already:
- Opens Chrome via Playwright CDP at `localhost:9222` (with Simplify Copilot extension preloaded).
- Navigates to the source URL, uploads the resume PDF, pierces `div.simplify-jobs-shadow-root`, clicks `Autofill`.
- Captures screenshot + DOM, scans unresolved fields, persists `apply_runs` + `apply_handoffs` rows.
- Stops at `NEEDS_REVIEW` (auto-submit hard-disabled).

What needs to change in Layer 2:
- The synchronous-from-DB-poll claim becomes a synchronous-from-API-call claim when triggered by issue #59's new endpoint.
- After Simplify Autofill finishes, **instead of bailing to NEEDS_REVIEW immediately**, hand control to Layer 3 for the long tail. Only then bail.

### Layer 3 — Long-tail LLM browser agent (NEW)
This is where the three research threads converge.

**From `analysis-002` (Simplify):** we know exactly what's left after the Autofill click. Greenhouse: 1–12 custom application questions per posting. Workday: dropdown mismatches, work-auth explanation, behavioral stories, start date, multi-select preferences. EEO/demographic: deliberately leave blank. Custom essays > 200 chars: re-author to defeat cross-employer leakage.

**From `analysis-001` (agent-browser):** the load-bearing primitive is **accessibility-tree snapshots with stable refs** (`@eN`). Built from `Accessibility.getFullAXTree` over CDP. Two reasons this is the load-bearing decision:
1. **Cost.** A typical post-Autofill job-form page serializes to 200–400 a11y-tree tokens vs. 3,000–5,000 raw-DOM tokens. With ~10–50 turns per apply, that's the difference between $0.05 and $0.50 per application at gpt-5-mini rates.
2. **Shadow-DOM piercing is free.** Chrome's a11y API walks open shadow roots transparently. Simplify lives inside an *open* `simplify-jobs-shadow-root`. So the same snapshot that reads ATS form fields also reads Simplify's UI state (e.g., "Autofill button reads 'Continue filling' — Simplify isn't done yet"). We don't need separate shadow-piercing code.

We do *not* take the agent-browser dependency — we replicate the snapshot pattern in ~200 lines of Python against the existing `page.context.new_cdp_session()`. The verb taxonomy is what we steal: `snapshot`, `click(@ref)`, `type(@ref, text)`, `select(@ref, option)`, `wait_for(predicate)`, `goto(url)`. Six tools is enough.

**From `analysis-003` (pi-mono):** the loop runtime. `@earendil-works/pi-agent-core` gives us, for free: streaming events, sequential/parallel tool dispatch, `beforeToolCall` / `afterToolCall` hooks, six thinking levels, multi-provider model registry, session persistence, abort semantics. The headline use of the hook system is **the "no Submit" gate**:

```ts
beforeToolCall: async ({ toolCall, args }) => {
  if (toolCall.name === "click" && isSubmitLikeRef(args.ref)) {
    throw new Error("BLOCKED: Submit click is disabled");
  }
}
```

**The triple-defense safety story:**
1. **Snapshot filter** (in our code, regardless of harness). Before showing the AX-tree to the LLM, drop any node whose accessible name matches `/^submit/i` or whose role is `button` and name contains "Submit". *The model literally cannot reference a ref it never saw.* This is the strongest defense — defense by ignorance, not by enforcement.
2. **beforeToolCall hook** (pi-mono). If something slips past the filter (e.g., a Submit button labeled "Send Application"), the click handler throws and the agent gets a tool-error response. Belt + suspenders.
3. **Hardcoded `dry_run=True`** (existing, SECURITY.md). Even if both above fail, the worker's outer wrapper has the apply-stage gate. Triple coverage.

This three-layer defense is the right answer because no single layer can be 100% reliable: regex filters miss labels, model overrides happen, and we can't audit every prompt forever. Three independent failures all in the same moment is acceptably rare.

---

## Two genuine architectural choices the user has to make

These are not "obvious wins"; both options work. I'll lay out the trade.

### Choice 1 — Agent runtime: TypeScript sidecar (pi-mono) vs. Python re-implementation

| | TS sidecar (pi-mono via JSON-RPC) | Pure Python loop |
|---|---|---|
| Loop semantics | Battle-tested, 52K-star user base | We write & maintain forever |
| Hooks, streaming, sessions | All built-in | We write the slice we need |
| Multi-provider | Built-in registry | We hand-roll per provider |
| Language boundary | One. Node 24+ in deploy, JSON-RPC IPC. | Zero. Same Python as the rest of the worker. |
| Extra runtime dep | Node + npm install | None |
| Per-turn IPC latency | ~5–20ms (dwarfed by LLM call) | None |
| Total LOC for the integration | ~400 (sidecar boot, JSON-RPC marshal, tool bridge) | ~600 (loop + hooks + provider integration) |

**My honest read:** Pure Python first. The pi-mono surface we'd actually use (loop + hooks + one provider) is small enough that re-implementing it in ~600 lines is straightforward, and it keeps the deploy one language. *Promote to pi-mono sidecar later* only if we discover we want its session-branching, multi-provider, or its precise event protocol — pi-mono is the right second-cut. **This is reversible.**

### Choice 2 — Snapshot: AX-tree (recommended) vs. raw DOM vs. screenshot

`analysis-001` makes the case for AX-tree. Two real alternatives to be honest about:

- **Raw DOM serialization** (what most homegrown attempts use first): 10× the tokens, no shadow-DOM piercing for free, brittle to UI rewrites. Don't.
- **Vision-based** (screenshot → multimodal model): expensive (image tokens > text tokens at small token counts), slower (image encode + decode + multimodal cost), and the model has to re-discover element identity every snapshot. Useful as a **fallback** when the AX-tree comes back empty or wrong; not as the primary.

AX-tree first, screenshot as a secondary tool the LLM can invoke when it's stuck. Both fit in the same `snapshot` tool with a `mode` arg.

---

## Cost & latency target (locks the model choice)

With Simplify carrying ~90% of fields, Layer 3 typically has **1–5 fields per apply on Greenhouse**, more on Workday (5–15). Conservative numbers:

| Knob | Value | Notes |
|---|---|---|
| Snapshot per turn | ~300 tokens (in) | AX-tree, post-filter |
| LLM response per turn | ~150 tokens (out) | mostly tool calls |
| Turns per apply | 5–25 | depends on ATS + custom-Q count |
| Model | `gpt-5-mini`, thinking=minimal | escalate to thinking=high only on loop |
| Per-apply LLM cost | **$0.01–0.10** | matches `analysis-002`'s estimate for Strategy (a) |
| Per-apply wall time | 60–180 s | dominated by Simplify's ~15s render + network |

**Escalation rule (in `afterToolCall`):** if 3 consecutive turns produce the same tool call or the agent appears stuck on the same field, bump thinking to `medium`; if 5 consecutive, bump to `high` and re-snapshot with screenshot. If 8 turns elapse without progress, abort and stamp `NEEDS_REVIEW` with `outcome="LLM_GAVE_UP"`.

---

## The "what to look for" system prompt (pre-computed from `analysis-002`)

The Layer-3 agent shouldn't rediscover Simplify's gaps every apply. Bake the gap-map from `analysis-002` into the system prompt:

> Simplify has already auto-filled the obvious fields. Your job is to handle ONLY what Simplify typically leaves empty:
>
> 1. Custom long-form text answers ("Why $COMPANY?", "Tell us about a time you…") — write a job-specific answer using the user's profile; re-author if the existing text references a different company.
> 2. Work authorization / visa-status free-text explanations.
> 3. Multi-select role-preference checklists.
> 4. Conditional dropdowns where Simplify wrote nothing because the user's exact value wasn't an exact option string — fuzzy-match the closest.
> 5. Preferred start date pickers.
> 6. Multi-step "Next" buttons in Workday-style flows (do navigate, do NOT submit).
>
> Hard rules:
> - NEVER click a button whose label contains Submit, Send Application, or Finalize.
> - NEVER touch EEO / demographic / veteran / disability self-id fields — leave blank for human review.
> - If a textarea is > 200 chars and you didn't author it, re-read it and rewrite if it doesn't match $COMPANY.
> - If you can't progress in 3 turns, return tool_call `give_up` with a reason.

This converts what would otherwise be 25 turns of exploration into ~5 turns of targeted action.

---

## Hand-off semantics (Layer 4)

Unchanged from today. Outcome stays `NEEDS_REVIEW`. The added value is that more fields are filled when the human takes over — and we record per-field telemetry on which layer (Simplify vs. LLM vs. human) eventually touched each field. **After 10–100 real applies, that telemetry is the dataset that tells us whether the strategy is working** and where to invest next.

---

## What is NOT in scope of this synthesis

- **Auto-submit.** Hard-disabled, SECURITY.md is the source of truth. Even if Layer 3 fills every field perfectly with 100% confidence, the worker stops. The synthesis above does not relax this.
- **Multi-account / multi-user.** Single-user assumption throughout. The Simplify CRX is logged into one account; the Chrome profile is one user's.
- **CAPTCHA / interactive verification.** If the ATS throws a hCaptcha or "verify you're human", agent gives up and hands off to `NEEDS_REVIEW`. No Captcha-solver in the architecture.
- **A reviewer/scorer for what the LLM filled.** Worth adding eventually (mirrors the resume-tailor's reviewer step) but explicitly out of scope of the first cut — the human review at NEEDS_REVIEW *is* the reviewer for now.

---

## Open questions for the user (decisions, not blockers)

1. **TS sidecar vs. Python loop for Layer 3?** My lean: Python first; pi-mono later if we need its session/event protocol. But pi-mono is a real win if you'd rather not maintain a loop. (See Choice 1.)
2. **Per-apply LLM budget.** I assumed $0.01–0.10. Is there a per-apply cost ceiling we should enforce in `afterToolCall`? (We already have monthly budgets via `cost_tracking`.)
3. **Where does Layer 3 live in the repo?** Most natural: `src/agents/apply_worker/llm_finisher.py` (Python loop) or `src/agents/apply_worker/finisher_sidecar/` (Node sidecar). Both fit the existing layout.
4. **Eval fixtures.** None exist today for the apply path. The fastest way to bootstrap is to record DOM+a11y snapshots of 5–10 real applications post-Simplify and replay them as test fixtures. Worth a separate research/eval pass once we ship Layer 3 v0.

---

## Bottom line — how the north star is achieved

1. **Ship issue #59** (Apply button + modal + backend enqueue endpoint). This is the user's "go" trigger and unblocks every other piece.
2. **Build Layer 3** (long-tail LLM browser agent) inside the existing apply-worker, using:
   - The accessibility-tree snapshot pattern from agent-browser, replicated in ~200 lines of Python (steal idea, skip dep).
   - Either pi-mono's `pi-agent-core` as a Node sidecar or a 600-line Python re-implementation of the same patterns (real choice; both work).
   - Triple-defense safety: snapshot filter + beforeToolCall hook + existing `dry_run=True`.
   - System prompt that bakes in Simplify's known-gap list, so the agent doesn't rediscover it every turn.
3. **Keep Strategy (a) — Simplify in front of the LLM agent.** Simplify covers 90% of fields for free; the LLM only does the long tail. Per-apply cost stays $0.01–0.10.
4. **Keep the NEEDS_REVIEW handoff and human-submit gate.** Auto-submit remains hard-disabled. Telemetry the per-field "who filled this" so we can measure how close to truly autonomous we're getting.

That's the path. Issue #59 is the first step; the architecture above is what it gates.
