# What is this

A narrative-style companion to the rest of the spec. The other docs describe the system as it is; this one frames why the design landed where it did and what it deliberately is *not* trying to be.

## The one-sentence pitch

Agentic Job Applier crawls job boards, decides which postings are worth pursuing, writes a tailored resume per posting, and drives the user's real Chrome browser to fill the application form — all running locally on the user's own machine, all under a binary gate that refuses to auto-submit anything the user hasn't implicitly approved.

## The shape of the problem

Job applications scale badly. Filling out 50 forms a week by hand is most of the work; the actual judgment ("is this role worth my time?", "does my resume hit the right keywords for this posting?") is a small fraction of the time and the only part the user actually cares about. The traditional automation answer — "click submit a bunch" — fails for three reasons:

1. **The submit click is the riskiest possible action.** Once an application is in, it's in. Wrong resume version, wrong work-authorization answer, wrong sponsorship status — all visible to the recruiter forever. A bug in an auto-applier is a bug visible to every company the user might want to work at.
2. **Forms vary.** Greenhouse, Ashby, Workday, iCIMS, Lever, Taleo, SmartRecruiters, and a long tail of one-off career pages all expose different DOM structures, different question wording, different consent checkboxes. Form-fillers that work on one ATS don't transfer.
3. **The interesting judgment is per-posting.** "Should this resume bullet mention Python or PyTorch first?" depends on the posting; "should I apply at all?" depends on the user's preferences, education status, work authorization, and salary expectations. No generic tool can answer those without a lot of per-user context.

The shape of the system reflects each of those: a strict submit gate so the worst case is "the user reviews the form before submitting," a focused ATS scope (Greenhouse and Ashby for autonomous, everything else falls through to human review), and heavy per-user configuration that the gate, tailor, and finisher all read from the same canonical YAML.

## Scope

What it does:

- Crawls 14+ sources (Greenhouse, Workday, Ashby, Lever, iCIMS, Taleo, JobSpy-backed Indeed/LinkedIn/Glassdoor, LinkedIn direct, Remotive, Himalayas, Working Nomads, The Muse, Adzuna, Startup Jobs, curated GitHub repos, generic career pages) on a 30-minute interval. No LLM spend in discovery.
- Runs every posting through hard and soft filters before any LLM call (title patterns, location, salary, company blocklist, age, positive/negative keyword auto-routing). Most postings never reach the gate.
- Calls an LLM gate (`gpt-5-mini`) on what's left, with the candidate's profile + preferences as context. Decision is APPLY or SKIP.
- For QUALIFIED postings, runs a deterministic LaTeX-native tailor + review pipeline: byte-offset patches into the base `.tex`, tectonic compiles each variant, a reviewer LLM scores tailored vs base on keyword fit / specificity / factuality. Factuality is a veto axis.
- For approved tailored resumes, drives the user's host Chrome over CDP to fill the application form. Simplify Copilot does the obvious fields; an apply-finisher agent with 8 typed Playwright tools handles the long tail (custom questions, comboboxes, async typeaheads).
- Auto-submits only when a binary gate passes: every required field filled, no Tier-3 deferred questions, no Tier-2 drafts below the user's confidence threshold, `SAFE_MODE` not set. Anything else lands in a human-review queue with screenshots, DOM snapshots, the agent's drafted answers, and the deferred questions for the user to finish.

What it intentionally does not do:

- Submit forms on ATSes the apply-finisher hasn't been hardened against (Lever, Workday, iCIMS, SmartRecruiters, etc.). Those reach the application form, get autofilled by Simplify, and stop at `NEEDS_REVIEW` — the user finishes manually.
- Run multiple users in parallel. SQLite, single-writer claim semantics, and the localhost threat model all assume one operator per install.
- Use anything but OpenAI for the LLM stages. The provider abstraction is partially scaffolded but tailor/reviewer/finisher all hardcode `openai`. Widening this is a known follow-up.
- Decrypt API keys at rest. `.env` is plaintext. The `cryptography` library is a declared dependency but unused. Single-user local model.
- Run a vendor cloud service. The whole thing is meant to run on the user's own laptop or homeserver.

## Design choices worth knowing about

### Single FastAPI process, in-process supervisor

Earlier iterations had separate worker containers (one for discovery, one for gate, one for tailor, one for apply). That made deployment painful (compose profiles to enable subsets) and made the autonomous toggle slow (you had to restart containers). The current design collapses everything into one FastAPI app whose lifespan owns a `LoopSupervisor`: four asyncio tasks (discovery + gate + tailor + apply) plus a mode-watcher that reconciles loop state within ~1.5 seconds when the user flips the toggle.

The tradeoff is that one process holding one SQLite connection means writers serialize. For a single-user local deployment that's fine; the next-step "multi-user, multi-server" scenario would need PostgreSQL plus rethinking the claim semantics.

### Host Chrome over CDP, not in-container Chromium

Putting Chromium in the container was the original plan. It would have added ~400MB of image, plus Xvfb / dbus / fontconfig, plus the user's Simplify Copilot extension wouldn't be there. Worse, many job boards rate-limit by IP, and Docker Desktop's vpnkit NAT shows the container's outbound IP as a gateway address (`172.66.0.243`) rather than the user's residential IP, which trips a lot of "unusual activity" heuristics.

Instead the apply worker connects Playwright over CDP to the user's already-running host Chrome at `host.docker.internal:9222`. Simplify Copilot, the user's cookies, the user's saved passwords, the user's IP — all real. Chrome 148+ added a stricter Host-header check that the obvious URL choice fails; the worker forces `Host: localhost:<port>` on both the `/json/version` probe and the Playwright handshake to satisfy that check.

The cost is operational: users have to remember to start Chrome with the debug port open before turning on autonomous mode. The dashboard's top-bar Chrome chip shows reachability in real time and an OS-specific copy-paste command in a popover. The apply loop sleeps without claiming when Chrome is unreachable, so closing Chrome never produces FAILED rows.

### `.tex` source-of-truth instead of YAML resume

An earlier iteration represented the resume as YAML and rendered to LaTeX via templates. That model had two problems:

1. Real LaTeX templates are heterogeneous. Jake's, sb2nov, ModernCV, Awesome-CV, AltaCV, Deedy — each uses a different macro family. Forcing them all into one YAML shape lost information.
2. Bullet identity was fragile. If two bullets had identical body text (which happens — "Built X using Y" appears across multiple roles), the YAML couldn't distinguish them, and patch attempts collided.

The current model treats the user's actual `.tex` file as the canonical artifact. A pure-function locator walks the file once, emits a manifest of bullet IDs paired with **byte offsets** pointing at body bytes only (not wrapping macros). The tailor LLM emits patches keyed by those IDs. The patcher splices replacements in descending offset order so earlier offsets stay valid. Duplicate bullet bodies are never confused because offsets disambiguate.

The price of this design is a strict contract on what `.tex` shapes the locator accepts (documented in `docs/resume-tex-contract.md`). The validator runs on upload and on every tailor run; failures surface line-numbered errors. Users with exotic templates have to either conform or extend the contract.

### Sub-agents for browser work, single agent for tailoring

The tailor stage is one LLM call (plus optional trim and retry) because rewriting bullets is a focused, bounded task. The apply finisher is a Pydantic-AI agent loop because driving a form is a sequence of dozens of small interactions, each of which mutates state the next interaction has to read. Trying to do form-filling with a single LLM call (one giant plan executed blindly) breaks down within two clicks because every click can change which fields are visible, which options exist in a combobox, which validation errors are showing.

The 8 finisher tools are intentionally narrow:

- A typed `fill_combobox(field_id, target_option, exact)` is much harder for the agent to misuse than a generic "run this JS" tool that lets it interpolate strings into selectors.
- `defer` and `flag_for_verify` make the agent's "I don't know how to answer this" / "I drafted something but want a human to check" decisions first-class — surfaced in `deferred_questions_json` and `drafted_fields_flagged_for_verify` instead of buried in free-text reasoning.
- `lookup_cached_answer` lets the user's accumulated answers (from human review) feed forward into future runs without any prompt engineering.

Token discipline matters a lot at this scale. A 40-turn form would blow the TPM ceiling if every turn resent the full message history. The finisher uses the OpenAI Responses API with `openai_previous_response_id="auto"` so context is reconstructed server-side, plus `openai_prompt_cache_key` so the system prompt + tool catalog is a cached prefix, plus `parallel_tool_calls=False` because the DOM mutates after every interaction and any plan with two calls is stale by the second one.

### Per-stage modes (`autonomous` / `opt_in` / `both`) instead of one big toggle

The user-facing autonomous toggle in the top bar is a convenience: it flips all three stages between `both` (loop runs + button works) and `opt_in` (loop idles + button works). Under the hood there are three independent `system_settings.automation.<stage>_mode` rows, and the workers read them on every cycle.

This matters because power users want different defaults for different stages. Common setup: discovery always runs, gate is `autonomous` (cheap, fast, useful), tailor is `opt_in` (expensive — let me decide which postings to tailor), apply is `opt_in` (the highest-risk stage; let me drive every submit myself). The single-toggle UI papers over this for the common case but the underlying knobs are there for users who want finer control.

### The binary submit gate

This is the single most important safety feature. Code at `src/agents/apply_worker/finisher_integration.py:204-253`:

```
auto_submit ⇔
  not safe_mode AND
  not dry_run AND
  finisher_outcome == COMPLETE AND
  all_required_filled AND
  not has_tier3_deferred AND
  (not has_tier2_pending OR all_drafts.confidence >= tier2_confidence_threshold)
```

Every one of those needs to be true. The default `tier2_confidence_threshold=1.0` means a single Tier-2 draft below perfect confidence blocks submit. Users who want looser gates lower this knob in their profile.

The gate decision label propagates through to `apply_handoffs.finisher_diagnostics_json.gate_decision`, so the user can see in the dashboard *why* a particular apply didn't submit. The point isn't to be permissive — it's to be explicit about every blocker.

## Lessons baked into the codebase

A few things that look like over-engineering until you understand the failure mode they prevent:

- **Random claim tokens on every PENDING row.** Without them, a crashed worker restarting could write success to a row another worker has already taken over.
- **Lease expiry on every claim.** Without it, a crashed worker leaves its row PENDING forever and the job is stuck.
- **Soft-deletes that free the per-job slot.** Without this, a user who hits "delete and retry" can't re-enqueue immediately — the slot's still held by the row they just "deleted."
- **Re-upload of the tailored resume after Simplify autofill.** Simplify uploads its own cached resume to the file input. Without the re-upload, the user's tailored PDF would lose to Simplify's generic one.
- **`scan_unresolved_fields` reads `.select__single-value` instead of `el.value`.** React-Select doesn't expose the picked value through `el.value` — checking the wrong attribute makes the finisher think every dropdown is empty after autofill, leading to a cascade of bogus "fill this combobox" turns.
- **PointerEvent sequence on React-Select picks.** React listens for `mousedown`, not `click`, to commit option selection. A bare `click` leaves the form blank. Verified live against Cloudflare's Greenhouse.
- **Forcing `Host: localhost:<port>` on the CDP connection.** Chrome 148+ rejects the WebSocket upgrade otherwise. The override is conditional (skipped if URL already uses localhost or an IP literal) so it doesn't break on older Chrome.
- **`asyncio.gather(..., return_exceptions=True)` on discovery families.** One Workday tenant returning 800+ jobs and timing out would otherwise block every other family in the cycle.
- **Late-bound `main.<Fetcher>` lookup in family tasks.** Lets tests monkeypatch the fetcher class at the top of `main` without modifying any imports inside the orchestrator code.
- **`previous_response_id="auto"` on the finisher.** Resending the full message history every turn would hit the TPM ceiling within ~5 turns; the chained-response-id pattern keeps each turn payload small.

Each of these has a corresponding test that pins the behavior; the test names are usually a good entry point for understanding what the codebase has learned the hard way.

## What's broken-by-design vs broken-by-accident

Broken by design (and deliberately so):

- **Multi-provider BYOK** is not really there. OpenAI only. The abstraction exists; the tailor and reviewer ignore it. Wider provider support is on the follow-up list.
- **The finisher only fires on Greenhouse and Ashby.** Other ATSes drop straight to NEEDS_REVIEW. Fine — the threat model says "never auto-submit something we don't understand."
- **The dashboard `dist/` is image-baked.** Live code updates need either a Docker rebuild or a `docker cp` of the freshly-built dist. Acceptable cost for the simpler deployment story.
- **API keys live plaintext in `.env`.** Single-user local model. Production users with shared infra should layer their own secrets manager.
- **No automatic retry on transient browser errors past `max_retries=2`.** Apply runs that fail twice land terminally failed; the operator decides whether to requeue.

Broken by accident or by deferred cleanup:

- **Legacy `*_yaml_path` columns** on `tailor_runs` and `review_runs` are written as `""` but still in the schema. Deferred cleanup.
- **The README's provider claims are stale.** "OpenAI, Anthropic, Gemini, OpenRouter" misrepresents current scope.
- **Some discovery fetchers can return silent zero results** when their backends rate-limit — `asyncio.gather` catches exceptions but not silent failures. An anomaly check on per-fetcher result counts would catch this.

`review_notes.md` ranks these by impact × probability with a prioritized follow-up order.
