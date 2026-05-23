# analysis-001 — Is `vercel-labs/agent-browser` the right harness for the autonomous job-applier?

**Date:** 2026-05-22  
**Built on:** local-001…local-006 (this pass) + `reference-repos/agent-browser/` v0.27.0  
**Verdict (1 sentence):** **Partial fit + significant build — agent-browser is the right *primitive* for the LLM-driven "finish the screener" leg, but we'd use ~15% of its surface and bring our own loop, safety, and evals; the snapshot pattern is worth stealing more than the dependency is worth adopting.**

---

## How this report fits the brief

The brief asked seven questions (Q1–Q7). Each is answered below, anchored to the primary-source local-NNN artifacts in this same pass directory. Read those for the underlying file:line evidence.

---

## Q1 — What is it, mechanically?

**It's a Rust CDP client distributed as a native binary via npm, not a Playwright wrapper.**

- `cli/Cargo.toml` shows `tokio-tungstenite` (raw WebSocket) — no Playwright/Puppeteer deps. The whole CDP layer is hand-rolled in `cli/src/native/` (see `local-001`).
- Distributed as `bin/agent-browser-{linux-x64, darwin-arm64, darwin-x64, windows-x64}.exe`; the `bin/agent-browser.js` shim simply `execFileSync`s the right binary for the host platform.
- `package.json` declares `"engines": { "node": ">=24.0.0" }` — high floor.
- **Three documented browser-attach modes** (cited in `local-001` + `local-006`):
  1. `agent-browser connect 9222` — attach to an already-running Chrome on a known CDP port.
  2. `agent-browser launch --cdp 9222` — spawn its own Chrome with a CDP port open.
  3. `agent-browser --auto-connect` — try to attach, fall back to launch.

- Calling surface = **CLI + `--json` flag for machine-readable output**. There is no SDK, no MCP server, no Python library. Integration is `subprocess.run([...])` + `json.loads(stdout)`. See `local-002` for the verb taxonomy (~80 verbs across 12 families: `screenshot`, `click`, `type`, `select`, `read`, `goto`, `wait_for`, `snapshot`, etc.).

---

## Q2 — The skills system

**Skills are markdown files with YAML frontmatter — instructions for an LLM, not callable functions.** Read `local-003` for the quoted manifests.

- `skills/*.md` ship system-prompt snippets ("how to fill a multi-page form", "how to use the screenshot verb", "how to read a snapshot"). They are templates a model is *given*, not code agent-browser *executes*.
- `skill-data/*.json` are reference fixtures (e.g., snapshot examples).
- Parameterization happens at the model-prompt level, not at a skill-invocation API level. There is no `runSkill("fill-form", { url, resumePath })` entry point.

Implication: the skills system is dead weight for our use case — we'd write our own apply-specific prompts and never load agent-browser's skills.

---

## Q3 — How does it know what to click?

**Accessibility-tree snapshot with stable refs (`@eN`), built from Chrome's `Accessibility.getFullAXTree` — which natively pierces open shadow roots.** This is the load-bearing finding.

From `local-006`:

- `cli/src/native/snapshot.rs:1320-1341` (the `snapshot` verb implementation) calls `Accessibility.getFullAXTree` and serializes each node as `@eN | role "name" attrs`.
- Output is **200–400 tokens for a typical job-form page**, vs. 3,000–5,000 tokens for raw HTML. That's the whole reason this architecture wins on cost.
- Shadow-DOM piercing is **free** because the Chrome DevTools accessibility API walks the full a11y tree including open shadow roots. Simplify Copilot's `simplify-jobs-shadow-root` is open mode (`attachShadow({ mode: "open" })`), so it would appear in the snapshot.
- `wait_for` and visibility primitives exist as separate verbs (`local-002`).

**This is the single most copyable idea**: a 200-line Python module against `page.context.new_cdp_session()` + `Accessibility.getFullAXTree` produces the same `@eN` ref table without taking on a Rust binary as a dependency.

---

## Q4 — LLM coupling

**BYO key. One tool exposed to the orchestrating model: `agent_browser(command: string)`.** See `local-005`.

- agent-browser does ship a model loop (`agent-browser run "..."` enters a chat-style loop), but the contract is brutally simple: one tool, one string argument, the model writes shell-like commands and agent-browser executes them.
- Step cap: **50 steps OR 5 minutes**, whichever first (configurable but hardcoded defaults). Past that, the loop aborts.
- No supervisor + executor split, no planner/actor pair. The same model both decides and acts.
- Provider integration: shells out to `claude -p` or `codex exec` for the actual LLM call — i.e., **it doesn't speak directly to any provider's API**; it depends on Anthropic/OpenAI's CLI being installed and authed on the same machine. That's a deal-breaker for a daemon running on a home server.

Implication: even if we adopted agent-browser's CLI, **we wouldn't use its model loop** — we'd use it only for the browser primitives (`snapshot`, `click`, `type`) and bring our own loop (pi-agent-core, or replicated in Python — see `analysis-004`).

---

## Q5 — Coexistence with our existing flow

**It coexists cleanly as a second CDP client on the same Chrome.** Verified in `local-006`.

- Our Playwright Python worker holds one CDP session; agent-browser would open a second on the same `localhost:9222`. Chrome supports many concurrent CDP clients; the Simplify extension stays loaded.
- The thing we **can't** do is hand a live `playwright.async_api.Page` object to agent-browser — it owns its own CDP session and doesn't accept foreign handles. The handoff happens at the Chrome layer, not the in-process layer.
- Pragmatic flow: Python worker drives Simplify Autofill (existing code), then `subprocess.run(["agent-browser", "snapshot", "--json"])` to get the post-autofill page state, parses, decides, then `subprocess.run(["agent-browser", "click", "--ref", "@e42"])`. Per-action overhead: spinning the Rust binary every time — adds 50–200ms per action. Tolerable.
- Better long-term: skip agent-browser CLI entirely, drive `page.context.new_cdp_session()` directly from Python, replicate the snapshot pattern. Same primitives, no shell-out cost, one language.

---

## Q6 — Real examples / benchmarks

**There is essentially one real example, and it's a toy.** See `local-004`.

- `examples/vercel-sandbox/` — opens example.com, takes a screenshot, uploads to Vercel Blob. That's it.
- `benchmarks/` — synthetic 2-field signup forms on example.com or local HTML fixtures. No Workday, no Greenhouse, no Lever, no real ATS fixtures anywhere in the repo.
- `evals/cases/command-usage.ts` runs `claude -p` against a fixture prompt and **regex-matches the model's text reply against expected `agent-browser` CLI call patterns**. The browser is never launched. This is a "does the model write the right command" eval, not a "does the browser actually fill the form" eval.

**Practical consequence:** we cannot trust that agent-browser "just works" on a real Greenhouse/Workday page based on maintainer testing — we'd have to build our own e2e eval harness regardless of which CDP client we pick.

---

## Q7 — Honest assessment

**Operational maturity:** mixed.
- Versioned releases (currently 0.27.0), CHANGELOG.md, multi-platform builds, docker images. Plus.
- No CI badge in README, no visible GitHub Actions workflow, no public eval results. Minus.
- The "skills" system is documented at the README level but not deeply specified — we'd be writing our own conventions.
- Single primary maintainer (vercel-labs is more a publishing org than an active maintenance team for this repo, judging by issue/PR cadence).

**Gaps we'd still have to fill if we wired it in:**
1. **Python ↔ Rust bridge.** No native Python SDK. We shell out + parse JSON.
2. **Submit-button guard.** `--action-policy` is verb-level only ("deny `click`"), not selector-level ("deny clicks on aria-label='Submit'"). We have to filter the snapshot in Python *before* showing it to the LLM. See `analysis-004` for the triple-defense story.
3. **Eval harness.** Need real ATS fixtures (Workday/Greenhouse/Lever/Ashby/iCIMS) recorded somewhere and a regression suite against them. Not in agent-browser.
4. **Cost telemetry.** agent-browser is provider-agnostic — token counts are the model's problem, not the harness's. We integrate with our existing `cost_tracking` ourselves.

---

## Cost comparison: with vs. without agent-browser

| Path | Effort | Runtime cost | Operational cost (6mo) |
|------|--------|--------------|------------------------|
| Adopt agent-browser CLI | ~1 week — Python wrapper + snapshot filter + LLM loop + eval harness + docker rebuild | Per-action 50–200ms subprocess overhead | Extra binary in deploy; second CDP client; another upstream to track |
| Pure Playwright + Python | ~3–5 days — `Accessibility.getFullAXTree` Python wrapper + ref table + same LLM loop + eval harness | None (in-process) | One language, one CDP session, existing deploy |

The pure-Python path wins on engineering effort *and* operational simplicity. The only reason to take agent-browser is if we want its multi-provider features (Browserbase / Kernel / hosted Chrome integration) or its dashboard (live JPEG stream on port 4848 — could be useful for human review during NEEDS_REVIEW handoff).

---

## Verdict

> **Steal the architecture. Skip the dependency.**

What to copy verbatim:
1. The `@eN` ref scheme over `Accessibility.getFullAXTree`. This is the load-bearing primitive that makes LLM-driven browser agents tractable cost-wise.
2. The verb taxonomy: `snapshot`, `click(@ref)`, `type(@ref, text)`, `select(@ref, option)`, `wait_for(predicate)`, `goto(url)`. ~6 tools is plenty.
3. The convention of always returning a fresh snapshot after every state-changing action — the model sees what changed.

What to skip:
- The Rust binary, the shell-out cost, the BYO-CLI provider integration, the skills/skill-data formalism, and the 50-step hard cap (we want our own budget circuit-breaker via `afterToolCall`).

**Verdict could flip** if we ever want:
- Cloud-browser-provider support (Browserbase/Kernel) — agent-browser's `--provider` integration is real saving.
- The observability dashboard (live JPEG stream on port 4848) for human review during NEEDS_REVIEW handoff.
- A future agent-browser version ships an MCP server or Python SDK (would change the calculus on shelling out).

See `analysis-004-north-star-synthesis.md` for how this verdict interleaves with the Simplify and pi-mono findings into a single architecture.
