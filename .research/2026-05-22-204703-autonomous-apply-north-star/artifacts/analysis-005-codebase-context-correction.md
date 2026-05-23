# analysis-005 — CORRECTION: what "pi-mono" actually means in this repo, and how that changes the agent-harness recommendation

**Date:** 2026-05-22 (correction to analysis-003 + analysis-004)  
**Trigger:** User caught that "pi-mono" was already in the codebase and that TypeScript is already a first-class language in this project. analysis-003 researched pi-mono *as if it were external* and analysis-004 framed the agent-runtime choice as "TS sidecar vs. Python re-implementation" — both wrong premises. This file fixes the framing and re-evaluates the recommendation.

---

## Two facts I missed, with primary-source citations

### Fact 1 — "pi-mono" is the in-tree codename for the resume-tailor agent shape; the npm package is NOT installed

The repo uses the phrase `pi-mono` across docstrings, schemas, and migration scripts as **internal vocabulary** for the structured-output LLM-agent pattern the resume tailor was designed around. The schema even **reserves subprocess fields for `pi-coding-agent`** (the npm CLI), but those fields are wired-but-unused — the current runtime uses Instructor.

Evidence:

- `src/agents/resume_tailor/schemas.py:1` — module docstring: *"Schema definitions and lock policy for the pi-mono resume tailor."*
- `src/agents/resume_tailor/schemas.py:439` — `class TailorInvocationContract`: *"Represent the V1 runtime contract for pi-mono resume tailoring."*
- `src/agents/resume_tailor/schemas.py:456-460` — five fields reserve a subprocess invocation of `pi-coding-agent`:
  ```python
  pi_coding_agent_command_argv: list[str] | None = None
  pi_coding_agent_command: str | None = None
  pi_coding_agent_workspace_dir: str | None = None
  pi_coding_agent_timeout_seconds: int = DEFAULT_PI_CODING_AGENT_TIMEOUT_SECONDS
  pi_coding_agent_env_allowlist: list[str] = Field(default_factory=lambda: [..., "PI_CODING_AGENT_DIR", "OPENCLAW_AGENT_DIR"])
  ```
- `src/agents/resume_tailor/schemas.py:36` — `DEFAULT_PI_CODING_AGENT_TIMEOUT_SECONDS = 14_400` (4 hours, sized for a long-running subprocess CLI).
- `src/agents/resume_tailor/schemas.py:483-501` — `_validate_pi_timeout` validator for the same field.
- `scripts/migrate_resume_tex_to_yaml.py:6` — *"by the pi-mono resume-tailor runtime."*
- `config/resume_content.yaml:60` — a resume bullet describing a different project: *"Agentic QA Review application whose pi-mono Director agent orchestrates specialized…"*

**But the actual runtime in `src/agents/resume_tailor/llm.py` does NOT shell out to `pi-coding-agent`. It uses Instructor + OpenAI Responses API directly:**

- `src/agents/resume_tailor/llm.py:25` — `import instructor`
- `src/agents/resume_tailor/llm.py:27` — `from openai import OpenAI`
- `src/agents/resume_tailor/llm.py:143-145` — `instructor.from_openai(OpenAI(), mode=instructor.Mode.RESPONSES_TOOLS)`
- `src/agents/resume_tailor/llm.py:214` — `client.responses.create_with_completion(...)` for structured output

**Python runtime deps** (`pyproject.toml:11,20,24`): `anthropic==0.96.0`, `instructor==1.15.1`, `openai==2.26.0`. **No `pi-coding-agent`, no `@earendil-works/*`, no Node runtime dep.**

### Fact 2 — TypeScript is already first-class in this project, but ONLY in the dashboard

- `dashboard/package.json` ships a React 19 + Vite 8 + TypeScript 5.9 stack with React Query, shadcn, Monaco, etc.
- **None of those deps are agent-related.** No `@earendil-works/*`, no `openai`, no `anthropic`, no `browser-use`, no `stagehand`, no agent framework of any kind on the TS side.
- The dashboard is a **read/write UI for the Python backend** — it makes REST calls to FastAPI. It does NOT host agent runtime code.
- The **worker** (where the browser agent would live) is Python: `scripts/process_apply_jobs.py` + `src/agents/apply_worker/`.

So "we already use TypeScript" means **the build/lint/test toolchain exists** and the team is comfortable in it — but it does NOT mean the worker side runs Node today. Adding a Node sidecar to the worker WOULD be adding a runtime to the deploy surface.

---

## How those two facts change the analysis-004 framing

**Wrong (analysis-004 Choice 1):** *"TS sidecar (pi-mono via JSON-RPC) vs. Python re-implementation of the loop"*

That binary was misframed. The real question is: **which agent harness do we pick for the browser-agent loop, knowing the resume-tailor already established the Instructor + OpenAI pattern (and the codebase already has `pi-coding-agent` schema hooks reserved if we ever wanted to graduate to that)?**

The pi-coding-agent subprocess path is a real, pre-thought option in this repo — but it's not the only option, and it was never live. It's been sitting as scaffolding waiting for either (a) us to actually wire the resume-tailor through it, or (b) us to retire those fields. So adopting it for the browser agent inherits the same "is the Node runtime worth it?" decision that the team apparently already deferred for the resume-tailor.

---

## Re-evaluation: real harness options for the browser agent

The browser agent needs a **multi-turn tool-calling loop** (see page → choose action → see result → repeat). That's a different shape from the resume-tailor (one-shot structured output). Instructor by itself isn't the right tool for tool-calling loops — but several things are.

| Option | Lang | Tool loop | Browser tools incl | Existing repo fit | Verdict |
|---|---|---|---|---|---|
| **OpenAI Agents SDK** (`openai-agents`, MIT, official) | Python | Yes, native | No (we write `read_dom`/`click`/`type` over our existing CDP) | Same provider (OpenAI), same async style, matches Instructor minimalism | **Strongest default.** Drop-in, in-process, designed exactly for this. |
| **Claude Agent SDK** (`@anthropic-ai/claude-agent-sdk`, Python + TS) | Either | Yes, native | Yes (newer versions bundle `computer_use` + browser tools) | Anthropic SDK already in `pyproject.toml`; switches the worker to Claude for browser agent | Strong if we're willing to use Claude for the browser leg; ships browser tools so less code to write. |
| **`pi-coding-agent` via subprocess** (`@earendil-works/pi-coding-agent`, npm) | Node | Yes | No | Repo already has the schema hooks reserved (`schemas.py:456-477`); BUT it's never been wired anywhere; adds Node runtime to the worker | Pre-thought, but never live. Real lift to make production-ready: process supervision, JSON-RPC marshaling, Node in deploy. Only worth it if we want pi-coding-agent's session/event protocol specifically. |
| **`browser-use` (Python)** | Python | Yes | **Yes — ships DOM tools** | Python, in-process, but opinionated about its own browser stack (Playwright-driven, owns the page) — may fight our existing Simplify-extension + CDP-attached flow | Compelling if we'd start a new Chrome; awkward graft on top of our existing Playwright-CDP-with-Simplify setup. |
| **`stagehand` (TS, Browserbase)** | Node | Yes | Yes | TS dashboard exists but stagehand is for the worker; ties to Browserbase | Not a fit — Browserbase tie-in is wrong for a self-hosted home-server use case. |
| **Custom Python loop on `openai.responses.create(..., tools=[...])`** | Python | DIY (~150 LOC) | No | Identical philosophy to the existing Instructor code: thin wrapper, no magic, all behavior visible | Pragmatic fallback if we want zero new deps. |

---

## Updated recommendation

**Primary choice: OpenAI Agents SDK (Python), in-process inside the existing apply-worker.**

Reasoning (replacing the analysis-004 recommendation):

1. **Same provider as the existing Instructor + OpenAI stack.** No new credential, no new BYOK pattern, no new cost-tracking dimension. The resume-tailor's `LlmCallResult` accounting flows continue to work with minor shape changes.
2. **Designed exactly for the tool-calling loop shape we need.** Tools (`snapshot`, `click(@ref)`, `type(@ref, text)`, `select(@ref, option)`, `wait_for`, `goto`) become Python functions; the SDK handles the loop, retries, and event streaming.
3. **In-process.** No subprocess management, no JSON-RPC marshaling, no extra runtime in deploy. The worker stays a single Python process.
4. **Same hook surface as pi-mono's `beforeToolCall` / `afterToolCall`.** OpenAI Agents SDK has `Guardrails` (pre/post execution) that map cleanly to our triple-defense "no Submit" story (filter snapshot + guardrail rejects Submit clicks + existing `dry_run=True`).
5. **Cost dial.** Same `gpt-5-mini` family, same `thinking` parameter, same cost telemetry path.

**Alternates I'd seriously consider, in order:**

1. **Claude Agent SDK** if we want to lean on Claude's stronger computer-use track record. Anthropic SDK is already in our `pyproject.toml`. Trade-off: the worker now talks to two providers (OpenAI for resume, Anthropic for browser); cost accounting needs to handle both.
2. **Custom Python loop on `openai` SDK directly with `tools=[...]`** if we want the smallest possible surface and don't trust the OpenAI Agents SDK API stability. ~150 LOC, no new dep, matches Instructor's "no magic" ethos.
3. **`pi-coding-agent` sidecar** *only* if we're actively planning to retire the Instructor-direct path for the resume-tailor too and route both through pi-coding-agent. Otherwise we're paying for Node runtime in the worker for one feature.
4. **`browser-use`** *only* if we're willing to refactor the existing Playwright-CDP + Simplify-extension flow to match its model. Otherwise the integration overhead eats the "DOM tools included" benefit.

**Explicitly NOT recommended for this repo:** the pi-mono npm package as an external sidecar via JSON-RPC. That's what analysis-004 leaned toward; it was wrong. The repo already has more direct, in-process options that better match the existing Python/Instructor stack.

---

## What stays unchanged from analysis-001/002/004

- **Snapshot pattern from agent-browser** (`Accessibility.getFullAXTree` → `@eN` refs) — still the load-bearing primitive. Replicate in Python over `page.context.new_cdp_session()`, ~200 LOC. Unchanged.
- **Strategy A** (Simplify-first, agent-second) — unchanged.
- **Triple-defense no-Submit** (snapshot filter + guardrail/hook + existing `dry_run=True`) — unchanged; just substitute "OpenAI Agents SDK Guardrail" wherever analysis-004 said "pi-mono `beforeToolCall`".
- **System-prompt baking in Simplify's known-gap list** — unchanged.
- **Cost target $0.01–0.10/apply** — unchanged.
- **Hand-off at `NEEDS_REVIEW`, human submits, per-field telemetry** — unchanged.

---

## What was incorrect in earlier files (for the record)

- **analysis-003** (pi-mono fit): treated the npm package as an external thing under consideration. The repo's "pi-mono" is internal vocabulary; the schema reserves subprocess fields for `pi-coding-agent` but they're inactive. Reading analysis-003 in isolation will mislead — read this file first.
- **analysis-004 Choice 1** ("TS sidecar vs. Python re-implementation"): the binary was wrong. The Python loop **already exists in style** (Instructor + OpenAI direct in `src/agents/resume_tailor/llm.py`); the right question is which *Python* loop library (Agents SDK / Claude SDK / custom on top of `openai`), with the pi-coding-agent subprocess as a deferred fourth option.
- **analysis-004 cost analysis ("~600 lines of Python re-implementing the same patterns")**: overstated. With OpenAI Agents SDK the integration is closer to **~200 lines** (define 6 tools as Python functions; pass them to the SDK; add a Guardrail for Submit). Custom loop without the SDK is closer to ~150–250 lines.

---

## Updated open decisions for the user

These supersede the analysis-004 "open decisions" list:

1. **Which Python agent harness for the browser-agent loop?**
   - **My lean: OpenAI Agents SDK.** Same provider as today, in-process, designed for tool-calling, ~200 LOC integration.
   - Alternates: Claude Agent SDK (if we want Claude for browser), custom `openai`-direct loop (smallest surface), `pi-coding-agent` sidecar (only if we're also retiring Instructor-direct for the resume-tailor).
2. **Should we either wire up the dormant `pi_coding_agent_*` schema fields for the resume-tailor OR remove them?** They've been sitting as scaffolding. If we're picking OpenAI Agents SDK for the browser agent, the inertia argument for keeping those fields weakens — they're a "we might subprocess pi-coding-agent someday" placeholder with no live consumer. Worth a follow-up issue either way.
3. **Per-apply LLM cost ceiling** — unchanged from analysis-004.
4. **Layer 3 file location** — `src/agents/apply_worker/llm_finisher.py` (Python loop) regardless of which harness wins; sidecar dirs are unnecessary if we stay in-process.
