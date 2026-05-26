# Review Notes

Known risks, in-flight uncommitted work, and prioritized follow-ups. Read this before promising anything about the apply finisher, the base-resume compile path, or the multi-provider story — those are the active edges of the codebase.

## Review basis

- Snapshot of working tree at the time of writing
- Recent ten commits (apply-worker + apply-finisher hardening and the `NotTailoredModal` wiring)
- `.research/` folders documenting prior investigations: `simplify-loop/`, `run18-forensics/`, `greenhouse-widget-anatomy/`, `agent-browser-docker/`, `agent-browser-refactor/`, `final-widget-fix/`
- `SECURITY.md`, `CONTRIBUTING.md`, `tests/test-plan.md`

Per user direction, any uncommitted edits in the working tree are treated as in-spec — they describe behavior the project should have.

## Consistency check

### Documentation vs code

- **`README.md`** still lists "OpenAI, Anthropic, Gemini, OpenRouter, Codex" as supported providers. In reality only OpenAI is wired through gate (via the abstraction) and tailor/reviewer/finisher (hardcoded). Provider settings API rejects everything but OpenAI with `UNSUPPORTED_PROVIDER`. The README needs a refresh to reflect single-provider scope.
- **`AGENTS.md`** lists `src/agents/apply_finisher/` with placeholder docs. Current finisher behavior (Pydantic-AI, Responses API, 8 typed tools, Tier-1/2/3 classification) is accurate at the conceptual level but the doc doesn't enumerate the tools or the Tier semantics. The spec under `spec/components.md` and `spec/workflows.md` is the more current source.
- **Docker compose** is single-service (`docker-compose.yml:22-46`). Older docs referencing `--profile tailor` / `--profile full` are stale — they describe a multi-container layout that no longer exists.
- **Chrome setup docs** in the README describe host Chrome via `--remote-debugging-port=9222`. That's correct. Older snippets referencing `deploy/start-chrome-cdp.sh` apply only to the systemd path (where Chrome runs as its own service unit) — not Docker.

### Code disagreements with itself

- **Provider abstraction is half-implemented.** `src/providers/factory.py` returns only `OpenAIProvider`, and tailor/reviewer in `src/agents/resume_tailor/llm.py:152-184` skip the abstraction entirely with `OpenAI()` + `instructor.from_openai(...)`. The cost-computation path in `OpenAIProvider.compute_cost` (cache-discount math via `litellm.cost_per_token`) is duplicated by a private `_get_cost_provider()` shim in `llm.py`. Switching providers requires touching three places.
- **Legacy `*_yaml_path` columns** are written as `""` post-Phase-3 but still on `tailor_runs` and `review_runs`. The dashboard never reads them. Harmless but worth removing in a future migration.

## Architectural risks

### Apply finisher form variability

The finisher is hardened against specific real forms: Cloudflare's Greenhouse ML Engineer Intern posting (verified live), Notion's Ashby engineer roles, and a handful of others via `.research/run18-forensics/`. Different companies on the same ATS may have radically different custom-question sets, different React-Select version pins, or different field naming conventions.

**Mitigation today:** The finisher's `defer` and `flag_for_verify` tools record questions the agent couldn't or wouldn't answer, and the gate withholds submit when any deferred or low-confidence draft remains. So the worst case is `outcome=NEEDS_REVIEW` rather than a wrong submit.

**Open question:** systematic coverage. Recommend a periodic smoke test that runs the finisher (in dry-run mode) against 5+ Greenhouse organizations and logs the ATS + custom-question signatures so the prompts and `defer_rules.yaml` can be extended.

### React-Select PointerEvent fragility

`src/agents/apply_finisher/tools.py:44-127` encodes the verified-live event sequence for React-Select v4 picks. Bare `click` events do not commit; only the full `PointerEvent + MouseEvent + click` sequence fires React's onChange. A future React-Select major (or a different vendor's React wrapper) could change this.

The agent-browser CLI's `find role option click` doesn't resolve aria-labelledby chains on Cloudflare's Greenhouse build either — the prompt explicitly tells the agent not to use the role selector and instead use ref-based selectors. That instruction is fragile against agent-browser upgrades.

**Mitigation:** pin the vendored agent-browser binary version; add a quick smoke test that opens one combobox and asserts `.select__single-value` populates.

### Image-baked dashboard

`dashboard/dist/` is COPYed into the image at build time. Live changes to the dashboard require either a Docker rebuild or `docker cp dashboard/dist/. <container>:/app/dashboard/dist/`. This is documented in user-facing memory but trips up new contributors.

**Acceptable for v1.** Long-term: a local dev mode that proxies `/api/*` from a host Vite dev server to the container's API would remove the friction.

### Docker Desktop vpnkit gateway IP

On Mac/Windows Docker Desktop, requests from inside the container that try to reach `host.docker.internal` get rewritten with a source IP of `172.66.0.243` (the vpnkit gateway). The localhost-only resume-download token gate that existed pre-consolidation would have failed for these requests.

The gate has been removed (single-user local threat model), but the change is a security-posture shift that `SECURITY.md` doesn't fully reflect. Document the threat model explicitly: single-user, localhost, operator-owned. Anyone deploying on a shared LAN should put a reverse proxy with auth in front.

### LaTeX compile silent failures

Tectonic resolves CTAN packages on demand into the shared `tectonic-cache` volume. If a build's prewarm step misses a package (the resume template uses something `deploy/tectonic-prewarm.tex` doesn't import), the first user tailor pays a 30-60s fetch. If that fetch times out under bad network, compilation might produce a truncated PDF or fail with a generic `ResumeCompileError`.

**Mitigation:** the 240s `TECTONIC_TIMEOUT_SECONDS` default is conservative. Add structured logging in `base_compile.py` and `compiler.py` that surfaces the tectonic stderr verbatim when compile fails, so an operator can see "package X failed to fetch" rather than a generic error.

### Single-writer SQLite under load

`BEGIN IMMEDIATE` serializes writes. Concurrent worker loops + a dashboard mutation + a background-task completion can pile up briefly. WAL journal mode (default) keeps readers non-blocking, but writers wait.

**Acceptable for the single-user local model.** Horizontal scale (multi-user, multi-server) would require PostgreSQL plus reworking the claim-and-lease code to use proper row locks.

## Operational risks

### Host Chrome version drift

The apply worker's CDP probe + Playwright handshake target a specific Chrome version range. Chrome 148+ added the strict Host-header check that the host-header override defeats; pre-148 versions don't need the override but accept it. Future Chrome majors could introduce other CDP-protocol changes.

**Mitigation:** the host-header override is defensive (skipped automatically when the URL already uses localhost or an IP literal). Document the tested Chrome major range in the apply worker README; add a startup warning if the detected version is wildly out of range.

### Simplify Copilot drift

The apply worker's autofill detection (`_JS_DETECT_SIMPLIFY` + `_JS_CLICK_SIMPLIFY_AUTOFILL`) hardcodes v2.4.x shadow-root structure. A Simplify v2.5+ release could change selectors silently.

**Mitigation:** document the Simplify version expectation in the user-facing setup docs. Long-term, add a smoke test that installs Simplify v2.4.x in a headless container and asserts the JS detection succeeds.

### Network-dependent fetchers

LinkedIn, Indeed, Glassdoor, and Adzuna can throttle or return empty results without an exception when their backends rate-limit. The orchestrator wraps fetcher calls in `asyncio.gather(..., return_exceptions=True)` so one stuck source doesn't block the cycle, but a silent zero-result fetcher won't trigger any failure path.

**Mitigation:** add a per-fetcher anomaly check that flags runs where the result count is suspiciously low compared to a rolling average. Mutmut testing on the LinkedIn fetcher catches parser drift but not endpoint behavior changes.

### curl-cffi quirks

LinkedIn fetcher uses `curl-cffi` for TLS fingerprinting bypass. The library is third-party and can have edge-case bugs (handshake failures, header encoding). The fetcher catches exceptions and logs, but subtle silent failures (empty arrays) would be hard to spot.

**Mitigation:** log `curl-cffi` version on fetcher startup so version-correlated bugs are easier to debug.

## Security considerations

- **Auto-submit gate is conservative.** Default policy: `tier2_confidence_threshold=1.0` means any Tier-2 draft below perfect confidence blocks submit. Users who want looser gates lower this in their profile.
- **`SAFE_MODE=true`** is a global kill switch — set it and the gate always returns `(False, "safe_mode")`. Currently not in `.env.example`. Add it with a comment explaining when to use it.
- **Finisher scope is enforced at runtime only.** `supported_finisher_ats` returns None for non-Greenhouse/Ashby platforms, so the worker skips the finisher entirely. There is no router-level guard rejecting apply requests to unsupported ATSes; the worker just lands `outcome=NEEDS_REVIEW` with `finisher_outcome=SKIPPED`. Adequate for the threat model (no auto-submit happens for unsupported ATSes), but worth tightening if router-side denial would be clearer.
- **API keys plaintext in `.env`.** Single-user local model. Operators on shared infra should layer a secrets manager.
- **Resume download endpoint is unauthenticated.** `GET /api/jobs/{hash}/resume` serves the tailored PDF without a token. Acceptable for the single-user local threat model; operators on shared LANs should layer auth.

## In-flight uncommitted work

Snapshot of the working tree at write-time (these are not regressions — they're the active feature):

- `api/routers/apply_runs.py` — `EnqueueApplyRunBody { resume_mode: "base" | "tailored" }`; the `"base"` path compiles `config/resume.tex` on demand (cached by content hash) and synthesizes tailor + review SUCCESS rows so the apply worker's BASE-verdict path runs unchanged.
- `api/routers/tailor_runs.py` — `EnqueueTailorRunBody { apply_after: bool }`; persists on `tailor_runs.apply_after_completion`; the BackgroundTask enqueues an apply run automatically on pipeline success.
- `src/agents/resume_tailor/base_compile.py` + `tests/test_base_compile.py` — the on-demand base-compile helper with content-hash caching under `data/base_resume/<sha>.pdf`.
- `dashboard/src/pages/JobsPage.tsx` + `JobsPage.modal-flows.test.tsx` + `JobsPage.apply-button.test.tsx` + `dashboard/src/lib/api/client.ts` — the `NotTailoredModal` wiring: `handleApplyTailored` (no body) and `handleApplyBase` (`{resumeMode: "base"}`), and `handleTailorThenApply` as a single `enqueueTailorRun` with `applyAfter: true`. No client-side mutation chaining.
- `src/database/_mixins/apply.py` + `src/database/_mixins/tailor.py` — corresponding mixin changes for the new column and the synthetic-rows enqueue path.
- `tests/api/test_apply_runs_router.py` + `tests/api/test_tailor_runs_router.py` — contract tests for the new bodies and chain behavior.
- `config/defer_rules.yaml` — narrowed to sponsor + salary as Tier 3 (the legally-consequential rows); EEO and start-date moved out because the user has explicit cached answers and deferring them would block every submit.
- `config/resume.tex` — user-template edits.
- `deploy/tectonic-prewarm.tex` — package-list edit.
- `config/resume.pdf`, `config/resume_base.pdf`, `config/resume_base.tex` — generated artifacts not under VCS yet.
- Helper shell scripts under `scripts/` (`delayed-followup-*.sh`, `restart-impl-*.sh`) — dev-time orchestration, not user-facing.

## Recent commit trajectory

Latest ten commits form one coherent story: harden the apply-finisher loop and wire it to the dashboard.

1. Apply-worker `scan_unresolved_fields` now reads both `.select__single-value` (React-Select picked value) and checkbox `el.checked` properly — closes a class of phantom-empty-field false positives that were triggering NEEDS_REVIEW unnecessarily.
2. Apply-worker apply-tab switching, Simplify-settle polling (replaces fixed sleeps), and resume re-upload (because Simplify clobbers the file input on click).
3. Apply-finisher prompt rewrite emphasizing `fill_combobox`-first ordering and verified-label checks — derived from `.research/run18-forensics/`.
4. Apply-finisher moves to OpenAI Responses-API settings (`openai_previous_response_id="auto"`, prompt cache key, medium reasoning) — required to keep a ~40-turn form under TPM ceilings.
5. React-Select pick fix via the full PointerEvent sequence (bare clicks don't commit on Cloudflare's Greenhouse).
6. Earlier pre-session WIP plumbing the Responses API and worker glue.

Velocity is steady; no regressions on the main branch.

## Test coverage gaps

Drawn from `tests/test-plan.md`:

- **Dashboard:** JobsPage outbound URL sanitization isn't covered by an integration test (unit test exists for `toSafeJobPostingUrl`). SettingsPage drafts may be lost on concurrent invalidation — no test pins durability. Worth adding 6 test suites (per the test plan).
- **Base-resume compile error paths:** the new `base_compile.py` has unit tests for cache hit/miss and a successful compile, but CTAN-timeout and invalid-`.tex` paths aren't covered by integration tests yet.
- **Apply-after-tailor end-to-end:** the apply_after column + BackgroundTask chain works in unit tests but the full smoke (tailor pipeline succeeds → apply enqueued → browser flow completes) isn't covered by an integration test.
- **Cross-ATS finisher behavior:** finisher tests use fixture HTML for Greenhouse and Ashby (`tests/_fixtures/finisher/`); live cross-company smoke is manual.

The default `uv run pytest -q` runs ~100 deterministic tests in under 3 minutes with `mypy --strict` blocking merges. Live model tests are gated by `--run-live-agent-e2e` (and the `OPENAI_API_KEY` check is a backstop). Hypothesis property tests cover normalization idempotence, patcher ordering, fetcher parsing. Mutmut is scoped to the LinkedIn fetcher.

## Top risks ranked

By impact × probability:

1. **Greenhouse form variability** (high × medium). Different companies' Greenhouse forms have radically different custom questions; the finisher's hardening is tuned against a small sample. *Mitigation:* dry-run smoke against 5+ organizations pre-launch; log ATS + custom-question signatures to correlate failures.
2. **Finisher model availability or price drift** (high × medium). The finisher relies on `gpt-5.4` with reasoning; price or availability shifts change the cost calculus. *Mitigation:* track `cost_events` closely; document fallback model list; the soft cost cap ($0.20/run, log-only) gives early warning.
3. **Simplify Copilot version drift** (medium × medium). v2.4.x DOM structure is hardcoded. *Mitigation:* explicit version requirement in user docs; smoke test that installs the expected version and asserts JS detection.
4. **React-Select / agent-browser version interaction** (medium × medium). The PointerEvent workaround targets specific versions. *Mitigation:* pin vendored agent-browser; add a one-combobox smoke test.
5. **CTAN cache stale or LaTeX compile silent failure** (medium × low). Prewarm covers the common case but new templates or transient network issues could surface as opaque errors. *Mitigation:* surface tectonic stderr verbatim on compile failure; consider a cache-rebuild path the dashboard can trigger.

## Recommended follow-up order

**Tier 1 — finish what's in flight**
1. Land the `resume_mode=base` + `apply_after` + `NotTailoredModal` flow on main with the corresponding contract tests.
2. Update README to drop the multi-provider claim and document the single-provider scope honestly.
3. Add `SAFE_MODE` to `.env.example` with a one-line comment.

**Tier 2 — close the test gap**
4. Add the missing dashboard test suites called out in `tests/test-plan.md`.
5. Add an end-to-end integration test for `apply_after=true` through the BackgroundTask + detached apply task chain.
6. Add a CTAN-timeout integration test for `base_compile.py`.

**Tier 3 — operational hardening**
7. Smoke-test the apply finisher against 5+ real Greenhouse organizations in dry-run, log signatures, extend `defer_rules.yaml` if needed.
8. Document Chrome and Simplify version expectations in the user-facing setup docs; add a startup warning when versions are out of range.
9. Tighten apply-router unsupported-ATS handling — return a clean signal at the API layer rather than relying on the worker to skip silently.

**Tier 4 — future scope**
10. Multi-provider BYOK: add `AnthropicProvider`, route it in the factory, branch `instructor.from_anthropic()` in tailor/reviewer, handle Anthropic's 10% cache-read discount in `compute_cost`. Re-enable the provider picker in onboarding.
11. Drop the legacy `*_yaml_path` columns from `tailor_runs` and `review_runs` with a clean migration.
12. Consider a local-dev mode that proxies the dashboard via the Vite dev server to remove the image-baked friction.
