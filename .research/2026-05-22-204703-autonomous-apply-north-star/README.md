# Research pass: Autonomous-Apply North Star

> **⚠️ CORRECTION POSTED 2026-05-22** — analysis-003 and analysis-004 evaluated `pi-mono` as if it were an *external* package under consideration. It's not: `pi-mono` is the **internal codename** for the resume-tailor's agent shape, and `src/agents/resume_tailor/schemas.py:456-477` already reserves (but does not yet wire) subprocess fields for `pi-coding-agent`. The actual current runtime uses **Instructor + OpenAI direct** (`src/agents/resume_tailor/llm.py:143-145`). The TypeScript dashboard does NOT host agent runtime — adding a Node sidecar would still mean adding Node to the worker deploy surface. **Read [`artifacts/analysis-005-codebase-context-correction.md`](./artifacts/analysis-005-codebase-context-correction.md) FIRST** — it supersedes analysis-003 and the agent-runtime parts of analysis-004. Updated recommendation: **OpenAI Agents SDK (Python), in-process**, as the primary harness.

**Date:** 2026-05-22 20:47:03 UTC  
**Topic:** How to wire `vercel-labs/agent-browser` + an in-process Python agent harness on top of Simplify Copilot to take a job posting from "user clicked Apply" all the way to "form is filled, awaiting human submit".  
**Mode:** `design` (architecture decision, three-way evaluation of harness + extension + agent runtime).  
**Built on:** none. No prior pass covered the autonomous-apply pipeline.  
**Linked GitHub issue:** [#59 — feat(dashboard): Apply button + 'tailor first?' modal on Jobs page](https://github.com/joeyspagnoli/agentic-job-applier/issues/59)

---

## TL;DR

| Question | Verdict |
|---|---|
| Is `vercel-labs/agent-browser` the right harness? | **Partial fit — steal the accessibility-tree snapshot pattern (`@eN` refs over `Accessibility.getFullAXTree`), skip the Rust binary dependency.** |
| Should Simplify Copilot stay in the flow? | **Yes — Strategy (a) "Simplify-first, agent-second" wins on cost, coverage, and maintenance vs. agent-only or DIY-autofill.** |
| Is `pi-mono` real, and does it fit? | **CORRECTED** — `pi-mono` in this repo is the internal codename for the resume-tailor agent shape (schema hooks for `pi-coding-agent` reserved but inactive; runtime uses Instructor+OpenAI). The npm `pi-mono` is a real external project but NOT installed here. For the browser-agent loop, **OpenAI Agents SDK (Python), in-process** is the better fit. See `analysis-005`. |
| Architecture for the new "long-tail" LLM browser agent | **AX-tree snapshot + 6 tools (click/type/select/wait/goto/snapshot) + triple-defense safety (filter + hook + existing `dry_run=True`) + system prompt baking Simplify's known-gap list.** |

**One-sentence north-star path:** Ship issue #59 (Apply button + modal + new `POST /api/jobs/{hash}/apply` endpoint) → add a "long-tail finisher" stage to the existing apply-worker that runs AFTER Simplify Autofill and BEFORE the NEEDS_REVIEW handoff → that finisher uses an in-process LLM browser-agent loop driven by AX-tree snapshots, with auto-submit still hard-disabled.

The full architectural reasoning is in **`artifacts/analysis-004-north-star-synthesis.md`** — that's the centerpiece of this pass.

---

## Queries used and tools used

**Local clone (no network):**
- `git clone --depth 50 https://github.com/vercel-labs/agent-browser.git reference-repos/agent-browser` (then read AGENTS.md, README.md, agent-browser.schema.json, cli/, skills/, skill-data/, examples/, evals/)

**Web search / fetch (Simplify thread):**
- WebSearch / WebFetch on chromewebstore.google.com, simplify.jobs, help.simplify.jobs
- WebSearch on remotejobassistant.com, jobcopilot.com, adzuna.co.uk for review coverage
- Reddit/HN attempts blocked by Anthropic crawler — worked around via Firefox add-on reviews and second-hand quotes
- `gh search code "simplify-jobs-shadow-root"` for extension-internals reverse-engineering signals (turned up `ksrawr/auto_apply`, `soumilbaldota/auto_filler`)

**Web search / fetch + gh CLI (pi-mono thread):**
- `gh search repos "pi-mono"`, `pimono`, `phi-mono`, `pi_mono` (disambiguation)
- `gh search code "import pi_mono"`, `"from pi_mono"`, `"@earendil-works/pi-agent-core"`
- WebFetch on the canonical README + secondary write-ups
- `gh repo view earendil-works/pi`

**Sub-agents launched:** 3 general-purpose research agents, dispatched in parallel:
1. agent-browser deep-dive (local clone analysis, ~14 minutes)
2. Simplify capability + automation research (web, ~14 minutes)
3. pi-mono disambiguation + fit analysis (gh + web, ~8 minutes)

All three sub-agents wrote into this same pass's `artifacts/` directory per the `better-search-claude` skill's "shared pass" rule. Each sub-agent's analysis file (analysis-001, 002, 003) was written by the parent (this session) because the sub-agent harness blocked the final writes — content is identical to what the sub-agents returned in their result messages.

---

## Evidence table

| Source | Type | Date | Relevance | Confidence |
|---|---|---|---|---|
| `reference-repos/agent-browser/` v0.27.0 (local clone, ~50 files read) | Primary code | 2026-05-22 | Direct primary source for agent-browser claims | HIGH |
| chromewebstore.google.com (Simplify Copilot listing) | Primary marketing | 2026-05-22 | What Simplify *claims* to do | HIGH |
| simplify.jobs (product site) | Primary marketing | 2026-05-22 | Tier features, supported ATSes | HIGH |
| help.simplify.jobs (help articles) | Primary docs | 2026-05-22 | "Request new autofill support" page | MEDIUM (404 on body, title only) |
| remotejobassistant.com 2026 Simplify review | Secondary review | 2026 | Source for "cross-employer text leakage" finding | MEDIUM-HIGH (single source, but specific + dated) |
| jobcopilot.com, adzuna.co.uk competitor reviews | Secondary | 2025–2026 | Competitor positioning + indirect Simplify-pain signal | MEDIUM |
| ksrawr/auto_apply, soumilbaldota/auto_filler (GitHub) | Reference impl | 2024–2026 | Confirm shadow-root contract stability for ~2 years | MEDIUM-HIGH |
| `badlogic/pi-mono` → `earendil-works/pi` README + npm | Primary docs | 2026-05-22 | Identification + package surface | HIGH |
| `algopian/chromeclaw` (GitHub) | Reference impl | 2026 | Proves pi-mono works inside a Chrome extension with CDP DOM tools | MEDIUM-HIGH |
| Reddit / HN | Forum | — | NOT REACHED — Anthropic crawler blocked | N/A |
| Unpacked Simplify CRX | Primary code | — | NOT FETCHED this pass (script identified) | N/A |

**Sources we couldn't reach:** Reddit threads, sonara.ai homepage, chrome-stats.com, Simplify TrustPilot, unpacked CRX. All worked around via second-hand or competitor reviews. See `artifacts/analysis-002-simplify-capability-gap.md` for the full follow-up list.

---

## Recommendation

**Adopt the architecture in `analysis-004-north-star-synthesis.md`:**

1. **Layer 0 — issue #59 Apply button** unlocks user-driven autonomous apply.
2. **Layer 1+2 — existing tailor + apply-worker + Simplify Autofill** stay as-is. Simplify carries ~90% of fields on big-5 ATSes for free.
3. **Layer 3 (NEW) — LLM "long-tail finisher"**:
   - AX-tree snapshot via `Accessibility.getFullAXTree` over CDP, serialized as `@eN` refs (idea stolen from agent-browser, replicated in ~200 lines of Python; shadow-DOM piercing is free).
   - ~6 tools: `snapshot`, `click(@ref)`, `type(@ref, text)`, `select(@ref, option)`, `wait_for`, `goto`.
   - Agent loop: **OpenAI Agents SDK (Python), in-process** — same provider as the existing Instructor+OpenAI stack, no new runtime, ~200 LOC integration. Alternates (in order): Claude Agent SDK (Python or TS, if we want Claude for browser), custom loop on `openai` SDK directly (~150 LOC), `pi-coding-agent` Node sidecar (deferred; schema hooks exist but never wired). **See `artifacts/analysis-005-codebase-context-correction.md` for why this supersedes the original analysis-004 recommendation.**
   - Triple-defense no-Submit: snapshot filter (model never sees Submit nodes) + agent SDK Guardrail / `beforeToolCall` hook (refuses if a Submit-ish click slips past the filter) + existing `dry_run=True` wrapper.
   - System prompt bakes Simplify's known-empty field map from `analysis-002` so the agent doesn't rediscover the gap every apply.
4. **Layer 4 — handoff** stays as-is. `NEEDS_REVIEW` outcome, human submits, per-field telemetry recorded so we can empirically measure "fraction of fields touched by humans" over time.

**Per-apply target:** $0.01–0.10 in LLM cost; 60–180 s wall time. Driven primarily by gpt-5-mini at thinking=minimal, escalating only on observed loop.

## Alternatives considered

- **Adopt agent-browser as a hard dep + shell out from Python.** Rejected: 50–200ms subprocess overhead per action, extra Rust binary in deploy, BYO-CLI provider integration is a non-starter for a daemon. See `analysis-001`.
- **Skip Simplify, agent does everything.** Rejected: 4–8 weeks to rebuild the ~10-person Simplify team's 2 years of per-site selector maps, with no revenue share. See `analysis-002`.
- **Hybrid DIY autofill (replicate Simplify's trivial-field filling, agent does long tail).** Rejected: same maintenance trap as agent-only, no Simplify upside. See `analysis-002`.
- **`browser-use` / `Stagehand` instead of pi-mono.** Plausible — both bundle DOM tools out of the box. Worth a follow-up bake-off if Choice 1 (TS sidecar vs. Python) lands on "TS but not pi-mono". See `analysis-003`.

## Risks and unknowns

| Risk | Status |
|---|---|
| Simplify's AI-fill long-text leakage (cross-employer "Why this company" bleed) | **Known.** Mitigated by: never trust textareas > 200 chars, agent re-authors, human reviews. |
| Simplify CRX auto-updates breaking our DOM-pierce path | **Mitigated by pinning the CRX.** Public download URL identified in `search-003`. |
| Auto-submit slipping through | **Triple-defense** (snapshot filter + hook + existing `dry_run=True`). |
| LLM stuck in a loop, burning budget | **Mitigated by `afterToolCall` budget circuit-breaker** + 8-turn no-progress abort → `NEEDS_REVIEW`. |
| Workday-style multi-step React forms | **Open.** Need to record fixtures and validate snapshot tool actually captures inter-step state. |
| Reddit / community failure modes we couldn't verify | **Open.** Anthropic crawler is blocked; user (or someone running outside that environment) should sanity-check the gap list in `analysis-002` against r/jobs / r/cscareerquestions threads. |
| Unverified Simplify CRX manifest internals | **Open.** Have the download script; not executed. ~1 minute follow-up if needed. |

## Next steps / validation needed

- **User decision: TS sidecar (pi-mono) vs. Python in-process loop?** See `analysis-004` Choice 1.
- **User decision: per-apply LLM cost ceiling** for `afterToolCall` circuit-breaker.
- **Build the new `POST /api/jobs/{hash}/apply` endpoint** as the gating dep for issue #59.
- **Record 5–10 real-application AX-tree snapshots** post-Simplify for use as eval fixtures (separate research/eval pass once Layer 3 v0 lands).
- **Verify Reddit gap-list** from outside the Anthropic crawler (or wait until indirect evidence accumulates from real applies).
- **Measure**: after 10–100 real applies with Layer 3 in place, the per-field "who filled this" telemetry tells us whether Strategy (a) is still the right call.

---

## Files in this pass

```
README.md  ← you are here
artifacts/
  ├── local-001-agent-browser-overview.md
  ├── local-002-agent-browser-cli-surface.md
  ├── local-003-agent-browser-skills-system.md
  ├── local-004-agent-browser-examples-and-evals.md
  ├── local-005-agent-browser-llm-coupling.md
  ├── local-006-agent-browser-coexistence.md
  ├── fetch-001-simplify-chrome-web-store.md
  ├── fetch-002-simplify-marketing-site.md
  ├── fetch-003-simplify-help-or-blog.md
  ├── fetch-004-pi-mono-primary-source.md
  ├── fetch-005-pi-mono-secondary-sources.md
  ├── search-001-simplify-failure-modes.md
  ├── search-002-simplify-competitors-and-gaps.md
  ├── search-003-simplify-extension-internals.md
  ├── search-004-pi-mono-disambiguation.md
  ├── gh-001-pi-mono-github-search.md
  ├── analysis-001-agent-browser-fit-for-job-apply.md      ← verdict per source thread
  ├── analysis-002-simplify-capability-gap.md
  ├── analysis-003-pi-mono-fit-for-browser-agent.md         ← SUPERSEDED by analysis-005 (treats pi-mono as external; it's not)
  ├── analysis-004-north-star-synthesis.md                  ← centerpiece; agent-runtime section superseded by analysis-005
  └── analysis-005-codebase-context-correction.md           ← READ FIRST — corrects analysis-003/004 with in-tree evidence
```

Read order: `README.md` → **`analysis-005` (correction)** → `analysis-004` (centerpiece, with the correction in mind) → `analysis-001/002` for the per-thread verdicts on agent-browser + Simplify → the per-source artifacts for evidence. Skip `analysis-003` — superseded.
