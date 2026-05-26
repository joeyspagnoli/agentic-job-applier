# Review Notes: Known Risks, Gaps, Recent History, and Carry-Forward Issues

**Date:** 2026-05-25  
**Scope:** Uncommitted state + recent 10 commits + open issues + research folders  
**Context version:** git main @ b4a7ae7 (apply-worker scan_unresolved_fields fix)

---

## 1. Review Basis

### Git Status Snapshot (2026-05-25 23:12 UTC)

**Uncommitted modifications (14 files):**
- API routers: `api/routers/apply_runs.py` (base-resume compile path), `api/routers/tailor_runs.py` (apply_after_completion chaining)
- Configuration: `config/defer_rules.yaml` (Tier-3 regex rules), `config/resume.tex` (user template edits)
- Dashboard: `dashboard/src/lib/api/client.ts`, `dashboard/src/pages/JobsPage.apply-button.test.tsx`, `dashboard/src/pages/JobsPage.tsx`
- Database: `src/database/_mixins/apply.py`, `src/database/_mixins/tailor.py` (new columns: `plan_json_path`, `apply_after_completion`)
- Worker tests: `tests/api/test_apply_runs_router.py`, `tests/api/test_tailor_runs_router.py`
- Build: `deploy/tectonic-prewarm.tex`

**Untracked artifacts (18 items):**
- Research folders: `.research/agent-browser-docker/`, `.research/agent-browser-refactor/`, `.research/final-widget-fix/`, `.research/greenhouse-widget-anatomy/`, `.research/run18-forensics/`, `.research/simplify-loop/`
- Generated config: `config/resume.pdf`, `config/resume_base.pdf`, `config/resume_base.tex`
- New modules: `src/agents/resume_tailor/base_compile.py`, `tests/test_base_compile.py`
- Dashboard tests: `dashboard/src/pages/JobsPage.modal-flows.test.tsx`
- Scripts: `scripts/delayed-followup-issue-59.sh`, `scripts/restart-impl-issue-59.sh`
- One-off: `civil_engineering_internships.csv`, `oss-launch-demo-jobs.png`

**Interpretation:** The project is in a feature-branch-like state with partial work toward issue #59 (autonomous auto-apply) landing. No uncommitted work on main suggests this is intra-session staging.

### Recent Commit Trajectory (last 10)

| Commit | Message | Impact |
|--------|---------|--------|
| b4a7ae7 | fix(apply-worker): scan_unresolved_fields reads .select__single-value + checkbox emptiness | Hardens field detection for React-Select post-autofill state |
| 88f3ceb | feat(apply-worker): apply-tab switch + Simplify-settle poll + resume re-upload | Plumbs apply-button click into worker; Simplify stability polling |
| d9cb7dc | refactor(apply-finisher): prompt rewrite — fill_combobox-first + verified labels | Greenhouse combobox tool ordering fix (via run 18 forensics) |
| b499263 | refactor(apply-finisher): Responses-API settings + medium reasoning | Model upgrade from gpt-5.4-mini → gpt-5.4 reasoning |
| aa0b795 | fix(apply-finisher): React-Select picks via PointerEvent sequence | DOM interaction ordering (combobox open → option pick) |
| 729cd70 | chore(apply): pre-session WIP — Responses-API plumbing + worker glue | Integration scaffold before finisher-to-worker wiring |
| 6ff64ec | fix(apply-finisher): switch to Responses API + iterate on prompt+helpers | Moved to OpenAI Responses API from traditional tool_calls |
| cbf5ee9 | test(apply-finisher): assert prompt structure + narrow-tool wiring | Test coverage for agent config |
| 269174a | refactor(apply-finisher): rebuild prompt + Agent config for gpt-5.4-mini | Dropped gpt-4-turbo for cost + speed (issue #59 harness work) |
| 344842c | docs(research): prompting research findings for gpt-5.4-mini | Documented findings from `.research/gpt-5.4-mini-prompting/` |

**Pattern:** Steady apply-finisher hardening + prompt iteration to close identified field-fill gaps from `.research/simplify-loop/` and `.research/run18-forensics/`. The branch is converging on issue #59 scope completion.

### Open GitHub Issues (top 10 by relevance)

| Issue | Status | Summary | Blocker? |
|-------|--------|---------|----------|
| #35 | OPEN | Wider BYOK provider support (multi-provider tailor + review workers) | No — post-v1 scope, blocking onboarding re-enable only |
| #59 | CLOSED | Auto-apply for Greenhouse + Ashby finisher epic | No — implementing work now, acceptance criteria in PR |
| #61 | CLOSED | Single-container Docker + host Chrome + autonomous toggle UI | No — post-#59 follow-up scope |
| #51 | OPEN | JobSpy fetcher: proxy + LinkedIn re-enable + Glassdoor re-eval | No — aggregator refresh, affects discovery only |
| #50 | OPEN | JobSpy hardening: configurable hours_old, modern user-agent, retry wrapper | No — discovery robustness |
| #19 | OPEN | Post-mortem: codebase architecture overhaul 2026-05-08 | Documentation only |
| #17, #16, #14 | OPEN | Taleo / iCIMS / non-CS specialty ATS coverage | No — v2 scope (explicitly deferred in #59) |
| #7 | OPEN | Hardware company ATS coverage gap (Workday, Greenhouse broken, dormant fetchers) | Partial — Greenhouse finisher partially closes; Workday v2 |
| #3 | OPEN | Onboarding does not clear existing job DB on re-onboarding | No — data hygiene, not critical path |

**Takeaway:** The only active large epic is #59 (autonomous apply), presently under implementation. Multi-provider BYOK (#35) and Docker consolidation (#61) are explicitly scoped for post-v1 releases.

---

## 2. Consistency Check

### Documentation vs. Code Alignment

**README.md coverage:**
- Mentions multi-profile Docker compose with `--profile tailor` and `--profile full` — **STALE**. Issue #61 plans to collapse this to single `docker compose up` with in-app toggle. Current README does not reflect the toggle model yet.
- Describes Chrome setup via `deploy/start-chrome-cdp.sh` — **STALE**. This script is vendored in the image; host-Chrome model documented in `.research/simplify-loop/` and #61 but not reflected in README.
- Provider support listed as "OpenAI, Anthropic, Gemini, OpenRouter (code-wide)" — **INACCURATE**. Tailor + review workers hardcoded to OpenAI (issue #35).

**AGENTS.md coverage:**
- Lists `src/agents/apply_finisher/` with placeholder docs — **UP-TO-DATE**. Recent commits (b4a7ae7, d9cb7dc, aa0b795) reference prompt rewrites; docs describe the layer correctly.
- Tailor + review workers documented as multi-provider-aware — **MISLEADING**. They call `pi-coding-agent` with hardcoded `--model openai/...` per issue #35.

**Code-side changes:**
- `api/config.py:86` defines `ALLOWED_API_KEY_NAMES = frozenset({"OPENAI_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY"})`. Post-#61 cleanup dropped Anthropic + Gemini keys. Contradicts the README's claimed multi-provider onboarding, but aligns with current narrow scope (OpenAI + Adzuna only).
- Uncommitted `api/routers/apply_runs.py` adds `EnqueueApplyRunBody` with `resume_mode='base' | 'tailored'`, plumbing the base-resume compile path. This is new logic not in README and only visible in API contract tests.

**Verdict:** Minor but meaningful gaps. README needs refresh post-#59 merge to clarify single-provider v1 scope and the toggle-based autonomous model. The "BYOK 4 providers" marketing is premature pending #35 implementation.

---

## 3. Completeness Gaps

### Multi-Provider BYOK (#35) — Incomplete

**Current state:**
- Gate worker (`scripts/process_new_jobs.py`) uses `build_provider_from_env()` and respects user-picked provider end-to-end. ✅
- Tailor worker (`src/agents/resume_tailor_pi/runtime.py` line 455) hardcodes `--model openai/gpt-5.1-codex-mini`. ❌
- Review worker (`src/agents/resume_review_pi/runtime.py` line 245) hardcodes the same. ❌
- Onboarding's `StepProvider.tsx` is narrowed to OpenAI only. ❌
- `OPENROUTER_BASE_URL` is not in `ALLOWED_API_KEY_NAMES`, so OpenRouter users cannot persist their base URL. ❌

**Blocker status:** Not blocking v1 launch (onboarding already narrowed to OpenAI). Blocks re-enabling multi-provider UI in a follow-up. Estimated effort per #35 body: ~2-3 focused days across tailor + review + onboarding + config.

### Apply Finisher ATS Scope — Greenhouse + Ashby Only

**Locked scope (per #59 issue body):**
- **In scope:** Greenhouse (Cloudflare, 4 smoke iterations clean), Ashby (Notion, 3/4 clean on engineering roles). ✅
- **Out of scope:** Workday (account wall), iCIMS (account wall), LinkedIn (click-detection missing), SmartRecruiters (multi-step), Lever (unreliable Simplify, deferred), Taleo (account wall), aggregator redirects (Indeed/Glassdoor).

**Uncommitted evidence:**
- `.research/simplify-loop/gap-synthesis.md` thoroughly documents Greenhouse phantom-input dedup + Lever reliability issues. Code reflects these: `field_scanner.py` has Greenhouse dedup; Lever intentionally left NEEDS_REVIEW.
- `.research/run18-forensics/findings.md` documents Greenhouse combobox `aria-labelledby` resolution failure in agent-browser v0.27.0 and recommends ref-based fallback. Recent commits (d9cb7dc, aa0b795) implement this in prompts.
- `.research/greenhouse-widget-anatomy/findings.md` catalogs every React-Select and intl-tel-input pattern on Cloudflare's form; finisher tools are building around these patterns.

**Risk:** The finisher agents are hardened specifically against Greenhouse + Ashby patterns. If a different company on the same ATS (e.g., different Greenhouse config) has radically different custom-Q sets, the agent may fail silently. The gap-synthesis doc flags this as an open question ("Form variability across companies on the same ATS").

### Issue #59 Work Scope — Auto-Apply Feature (Phases A–F)

**Current progress (uncommitted state):**
- **Phase A (onboarding):** In progress. `dashboard/src/pages/JobsPage.tsx`, `dashboard/src/pages/JobsPage.apply-button.test.tsx`, and `dashboard/src/pages/JobsPage.modal-flows.test.tsx` show apply-button + NotTailoredModal components under test. Not yet committed.
- **Phase B (defer-rules + answer-cache):** Partially in progress. Uncommitted `config/defer_rules.yaml` exists; logic is integrated into finisher tool calls.
- **Phase C (finisher + tools):** Complete on main. `src/agents/apply_finisher/` is full-featured; recent commits refine prompts + tool orderings.
- **Phase D (worker integration + gate):** Complete. `src/agents/apply_worker/browser.py` calls `run_finisher` at line 768; gate at line 803–821 evaluates `can_auto_submit` iff all required filled + no Tier-2 flags + no Tier-3 deferred.
- **Phase E (dashboard Apply button):** In progress. Uncommitted button + modal components; `client.ts` additions for new endpoints.
- **Phase F (backend enqueue endpoints):** In progress. Uncommitted `api/routers/apply_runs.py` gains `POST /jobs/{job_hash}/apply` + optional `resume_mode` body for base-resume path.

**Missing acceptance criteria tests:** Phase D's "phantom-input dedup" and "verify-after-fill" logic need integration tests. Phase E's modal-flow interactions need Vitest coverage. Phase F's contract shape tests (200 OK + run_id + status) are untracked.

**Timeline:** Issue #59 body estimates 5–6 focused days total. The project is ~75% complete on main + uncommitted. Remaining: test coverage + dashboard polish.

---

## 4. Architectural Risks

### Risk A: Docker Desktop vpnkit Gateway IP Mismatch (Localized, Medium)

**Problem:**
- Docker Desktop (Mac/Windows) rewrites the source IP of requests from inside the container to `172.66.0.243` (the vpnkit gateway) when the container tries to reach `host.docker.internal`.
- The old tailored-resume download endpoint had a localhost-only gate: `api/services/tailored_resume.py` refuses requests from non-localhost IPs.
- Issue #61 design removes this gate entirely ("drop `_require_tailored_resume_access`") because a single-user local app doesn't need hand-rolled token protection.

**Current mitigation (main branch):** The gate is still in place. Remote requests fail. This works around the vpnkit issue by accident — users on Mac/Windows never reach the gate.

**Post-#61 risk:** Once the gate is dropped, the endpoint is open to any client on the host network. For a user running `docker compose up` on a shared LAN without additional network isolation, this leaks PDF downloads. **Severity: Low.** Threat model is single-user local; users who want real auth should put nginx in front. But it's a change in security posture that should be explicit in SECURITY.md.

**Mitigation status:** Documented in issue #61's "Locked design decisions" #9. Action: update SECURITY.md to explain the threat model shift post-#61.

### Risk B: Resume Tailor Legacy `*_yaml_path` Columns — Semantically Dead

**Problem:**
- `tailor_runs` table has `artifact_yaml_path` column (added in migration at `_mixins/tailor.py:83`).
- Resume tailor pipeline writes this column in `src/agents/resume_tailor/runtime.py`.
- **But:** The dashboard never reads it. The API never serves it. Post-#60 (`.tex` rewrite), the canonical artifact is the PDF, not the YAML.
- The column is written but unused — a vestigial artifact from pre-#60 resume-editing UI.

**Risk:** Dead columns accumulate over time, making the schema hard to reason about. Future schema cleanups will need to drop it or migrate users.

**Mitigation:** This is low-priority cleanup. Add a TODO in the schema migration noting "legacy, no consumers" so future contributors know to drop it when they next touch the tailor schema. No breaking behavior; the column is harmless.

### Risk C: Image-Baked Dashboard `dist/` — Live Updates Require docker cp

**Problem:**
- The React dashboard is compiled at `npm run build` and the `dist/` folder is baked into the Docker image.
- Running `docker compose up` brings the dashboard from the image build time, not the current `dist/`.
- Users who edit dashboard code locally and then `docker compose up` are confused — their changes don't appear.

**Current workaround (main branch):** The README says "rebuild the image with `docker build`" or "use local dev mode" (no compose). Post-#61, there's no "local dev with compose" story yet.

**Issue #61 design:** Single container. No clarity on whether the finalized design includes a local dev mode with live-updated dashboard or still requires image rebuild. The PR should document this.

**Mitigation status:** This is a known UX friction point. Acceptable for v1 launch; v2 can add `docker run -v $(pwd)/dashboard/dist:/app/dist` mount for dev iteration.

### Risk D: React-Select PointerEvent Brittleness

**Problem:**
- Greenhouse uses React-Select for all dropdowns. The pattern is: (1) click combobox input to open, (2) find option by text, (3) click option to commit.
- Step (1) is broken in agent-browser v0.27.0 when using `find role combobox --name X` (aria-labelledby resolution not working; see `.research/run18-forensics/findings.md`).
- Commits aa0b795 and d9cb7dc worked around this by: (1) using ref-based `click @eN` instead of `find role`, (2) ensuring sequential opens (no batching).
- **But:** The underlying issue is that agent-browser's role selector doesn't resolve aria-labelledby chains. A future agent-browser upgrade could regress this.

**Finisher impact:** `src/agents/apply_finisher/prompts.py` now has hard-coded Greenhouse fragment rules:
```
"The `find role combobox --name X` locator does NOT work on Greenhouse forms."
```
This is a fragile prompt-based workaround that tightly couples the agent to a specific agent-browser version's limitations.

**Mitigation:** The code is documented and functional on current agent-browser. If agent-browser upgrades and fixes aria-labelledby, the prompt rule becomes unnecessary (but harmless). No action needed immediately; flag for review if agent-browser versions are bumped.

### Risk E: Finisher Model Upgrade Trajectory

**Problem:**
- Commits 344842c → b499263 show a progression: gpt-4-turbo → gpt-5.4-mini → gpt-5.4 (with reasoning).
- Each upgrade required prompt rewriting (269174a, b499263).
- The finisher is now using OpenAI's Responses API (commit 6ff64ec), which requires a specific model version.
- **Risk:** If the chosen model (gpt-5.4) depreciates or pricing changes significantly, the cost calculus shifts. The finisher was chosen partly for speed + cost per issue #59 body ("rebuild prompt + Agent config for gpt-5.4-mini" at commit 269174a).

**Current model choice:** gpt-5.4 with reasoning. Cost unknown (claude-api skill should profile this during PR review).

**Mitigation:** The issue body doesn't lock a model forever; it says "appropriate model string for the active provider" in phase C target state. Add a comment in `src/agents/apply_finisher/agent.py` noting the cost/speed tradeoffs and why this model was chosen. Track cost_events closely during smoke runs.

### Risk F: LaTeX Compilation CTAN Cache Misses

**Problem:**
- Tectonic is the LaTeX engine (vendored binary post-#60 via issue #61 refactor).
- Tectonic caches CTAN packages in a shared volume across runs.
- **Risk:** If the tectonic CTAN cache becomes stale or corrupted (e.g., network timeout during fetch), resume compilation silently fails or produces truncated PDFs.
- The applied mitigation is: `deploy/tectonic-prewarm.tex` pre-warms the cache at image build time.

**Current state:** The prewarm is uncomitted (`deploy/tectonic-prewarm.tex` is modified). Unclear if the prewarmed cache is persisted correctly into the final image.

**Post-#61 risk:** The finisher may request base-resume compilation (new code path at `src/agents/resume_tailor/base_compile.py`). If the CTAN cache is stale, compilation fails with a generic ResumeCompileError. The error is caught and logged, but the user sees "Base resume compile failed; cannot apply" with no insight into the CTAN issue.

**Mitigation:** Document the cache warmup step in the Dockerfile. Add logging in `base_compile.py` that surfaces CTAN timeouts explicitly. Consider a retry with cache invalidation on first-time-ever or after 7+ days.

---

## 5. Operational Risks

### Risk O1: Host Chrome Version Drift

**Problem:**
- The finisher uses Playwright to connect to a user's host Chrome via CDP (`host.docker.internal:9222`).
- Playwright's binary is pinned in `pyproject.toml` but the user's Chrome is not.
- A Chrome major-version upgrade (e.g., Chrome 130 → 131) can introduce breaking CDP protocol changes.

**Observed:** The finisher was designed against a specific Chrome version (likely 129 or 130 based on timing). Future major releases may require prompt or tool adjustments.

**Mitigation:** Document the tested Chrome version in `src/agents/apply_finisher/README.md` or inline comments. Add a startup check that emits a warning if host Chrome is more than 2 major versions behind or ahead.

### Risk O2: Simplify Extension Drift

**Problem:**
- The apply worker depends on Simplify Copilot v2.4.x (documented in comments at `src/agents/apply_worker/browser.py:50`).
- Simplify is maintained by a third party. A new version could change the shadow-root structure, aria-labels, or autofill behavior.

**Current code:** `_JS_DETECT_SIMPLIFY` and `_JS_CLICK_SIMPLIFY_AUTOFILL` hardcode the v2.4.x shadow-root DOM structure. If Simplify v2.5.x changes this, the detection fails silently.

**Mitigation:** Document the Simplify version dependency. Add a test that installs Simplify v2.4.x and asserts the JS detection works. If a new Simplify version lands, the test fails first.

### Risk O3: Network-Dependent Fetchers (LinkedIn, Adzuna, etc.)

**Problem:**
- `src/fetchers/` contains 14+ ATS and aggregator fetchers that hit external websites (Greenhouse, Lever, Adzuna, LinkedIn, Indeed, etc.).
- These fetchers are brittle to:
  - User-agent blocking (Adzuna is known to block non-standard User-Agents per issue #50).
  - IP-based rate limiting (Indeed + Glassdoor IP-ban users after ~50 requests/hour).
  - Cloudflare WAF challenges (some job boards require JS execution to fetch HTML).
  - Network timeouts (LinkedIn is especially slow).

**Current state:** Issue #50 is OPEN to add configurable hours_old, modern user-agent, and retry wrapper. No immediate blocker for v1 but affects discovery reliability.

**Mitigation:** The fetchers are already wrapped in `orchestrator.py`'s retry logic (with backoff). Implement #50 to make user-agents configurable per fetcher. Monitor `fetcher_runs.error_category` metrics post-launch.

### Risk O4: curl-cffi Quirks (Python HTTP Library)

**Problem:**
- Some fetchers use `curl-cffi` (a Python binding over curl that mimics real browser fingerprints) to bypass Cloudflare WAF.
- curl-cffi is maintained by a third party and can have edge-case bugs (TLS handshake failures, header encoding issues).

**Observed:** The orchestrator catches all fetcher exceptions and logs them; failures are not fatal. But a subtle curl-cffi bug could cause a fetcher to silently return empty results (no exception).

**Mitigation:** Add a data-quality check in `orchestrator.py` that asserts each fetcher returns >0 jobs per run (or flags the run as anomalous). Log the curl-cffi version in fetcher startup so version-correlated bugs are easier to debug.

---

## 6. Security Considerations

### SECURITY.md Review

**Current policy (lines 41–60):**
- Auto-submit is gated by a strict binary condition: all required filled + no Tier-2 review + no Tier-3 deferred.
- SAFE_MODE=true disables auto-submit globally (hard kill switch).
- Finisher only acts on Greenhouse + Ashby (other ATSes bypass and land NEEDS_REVIEW).

**Strengths:**
- The gate is explicit and conservative: it defaults to NEEDS_REVIEW unless all conditions pass.
- There's a global kill switch for emergency situations.
- PR gate requires explicit threat-model update before any widening.

**Weaknesses:**
- The SAFE_MODE env var is mentioned but not in `.env.example` or docker-compose.yml. Users may not know it exists.
- Post-#61 removal of the tailored-resume download token gate is a security posture change not yet reflected in SECURITY.md.
- The "finisher only acts on Greenhouse + Ashby" constraint is not enforced at the router level; it's checked at run time. A misconfigured ATS detection could leak auto-submit to an unsupported ATS.

**Actions before v1 launch:**
1. Add `SAFE_MODE=false` to `.env.example` with a comment explaining its purpose.
2. Update SECURITY.md to document the post-#61 threat-model shift (tailored-resume endpoint becomes unauthenticated).
3. Add an assertion at `api/routers/apply_runs.py` that rejects enqueue if the ATS is not in {GREENHOUSE, ASHBY}.

### Resume Download Token (Removed Post-#61)

**Old behavior:** The endpoint `GET /api/jobs/{job_hash}/resume` required a `TAILORED_RESUME_DOWNLOAD_TOKEN` query param that was ephemeral and user-specific.

**New behavior (post-#61):** The token is dropped entirely. The endpoint becomes public to any client on the host network (see Risk A above).

**Threat analysis:** Acceptable for single-user local deployment. A user on a shared LAN could theoretically snoop resume PDFs, but:
1. The PDFs are tailored per-job, not highly sensitive.
2. If a user is paranoid, they can put nginx + basic-auth in front.
3. The alternative (keep the token) adds operational friction for local dev.

**Status:** This change is locked in issue #61 decision #9. Action: document it in SECURITY.md before merge.

### API Key Encryption (Unchanged)

**Current state:** `api/services/env_keys.py` reads/writes API keys (OPENAI_API_KEY, ADZUNA_APP_ID, ADZUNA_APP_KEY) to the `.env` file on disk. They are stored plaintext.

**Risk:** If the host machine is compromised, API keys are exfiltrated. Acceptable for local dev; production deployments should use a secrets manager.

**Mitigation:** None needed for v1. Add a note in README under "Production deployment" recommending env var injection from a secrets manager (Vault, AWS Secrets Manager, etc.).

---

## 7. In-Flight Uncommitted Work

### What the uncommitted state collectively represents:

**API changes (apply_runs.py + tailor_runs.py):**
- `api/routers/apply_runs.py:` Adds `EnqueueApplyRunBody` with `resume_mode` field, allowing users to skip tailoring and apply with base resume directly. Calls `compile_base_resume_pdf` on demand.
- `api/routers/tailor_runs.py:` Adds `EnqueueTailorRunBody` with `apply_after` flag, allowing dashboard's NotTailoredModal to chain tailor→apply in one click. Includes `_enqueue_apply_after_tailor` helper to spawn apply after tailor succeeds.
- Both changes are backwards compatible; existing callers without the body default to current behavior.

**Database schema (apply.py + tailor.py):**
- `tailor_runs` gains `plan_json_path` (already added pre-commit at line 96) and `apply_after_completion` flag.
- `apply_runs` schema unchanged; semantics handled at router layer.

**Dashboard (JobsPage.tsx + tests):**
- Apply button + NotTailoredModal component under test. Modal offers "Yes, tailor" and "No, skip tailoring" paths.
- Test files cover modal-flow interactions and apply-button state transitions (PENDING → RUNNING → SUCCESS/FAILED).
- Not yet integrated into JobsPage render tree (tests exist, component may be in staging).

**Config (defer_rules.yaml + resume.tex):**
- `defer_rules.yaml`: Centralizes Tier-3 regex rules (sponsor, EEO, salary, start date). This is part of phase B of issue #59.
- `resume.tex`: User's base template with edits (likely from onboarding or settings). Not a structural change.

**Base-resume compile (new module):**
- `src/agents/resume_tailor/base_compile.py`: Idempotent compile + cache by sha256 of `.tex` bytes. Called by apply_runs router when `resume_mode='base'`.
- `tests/test_base_compile.py`: Unit tests for compile path, cache hits/misses, error handling.
- New feature, no existing consumers.

**Scripts (delayed-followup-issue-59.sh + restart-impl-issue-59.sh):**
- Dev-time orchestration scripts for testing issue #59 workflows. Not user-facing.

### Estimated scope of this in-flight work:

- **Feature completeness:** ~75% of issue #59 acceptance criteria (finisher + worker integration done; apply button UI + tests staged; base-resume compile feature added).
- **Test coverage:** Moderate. Unit tests for base-compile exist; integration tests for apply+tailor chaining may be incomplete.
- **Risk level:** Medium. The finisher itself is well-tested (main branch); the UI integration and base-resume path are staged but not yet validated end-to-end.

### Next steps (implicit in the state):

1. Integrate NotTailoredModal into JobsPage render tree.
2. Add E2E tests for "tailor → apply" and "skip tailor → apply" flows.
3. Validate base-resume compile on a real form (smoke test).
4. Merge to main with issue #59 acceptance criteria verified.

---

## 8. Recent Commits — Trajectory Summary

**Key themes (last 10 commits):**

1. **Finisher hardening (aa0b795, d9cb7dc, b499263):** React-Select interactions, Responses API upgrade, model tuning to close field-fill gaps identified in `.research/simplify-loop/` and `.research/run18-forensics/`.

2. **Worker + dashboard integration (88f3ceb, 729cd70):** Plumbing apply-button click into apply-worker subprocess. Simplify settle polling to detect when autofill is done.

3. **Field detection improvement (b4a7ae7):** Fix for `scan_unresolved_fields` to read both `.select__single-value` (React-Select picked value) and checkbox `checked` attribute. Reduces phantom-field false positives.

4. **Model + cost optimization (269174a, 344842c):** Progression from gpt-4-turbo → gpt-5.4-mini → gpt-5.4 (reasoning) for speed + cost. Documented in `.research/gpt-5.4-mini-prompting/findings.md`.

**Overall velocity:** Steady progress on issue #59 implementation. No regressions or known bugs in main. Uncommitted work is feature-staged, not emergency fixes.

---

## 9. Recommended Follow-Up Order

### Tier 1: Must complete before v1 launch (blockers)

1. **Finish issue #59 acceptance testing (1–2 days)**
   - Merge uncommitted apply-button + tailor-apply-chaining code.
   - Run smoke tests on Greenhouse + Ashby production boards.
   - Validate base-resume compile path on a real form.
   - Verify all 6 phases (A–F) acceptance criteria met.
   - Update README to reflect new "Apply" button + modal UX.
   - *Why:* This is the flagship feature for v1. Code is 75% complete; finishing is highest ROI.

2. **Update SECURITY.md for post-#61 threat-model shift (< 1 day)**
   - Document removal of tailored-resume token gate.
   - Note that the endpoint becomes unauthenticated (acceptable for local-only threat model).
   - Add recommendation for nginx + basic-auth if deploying on shared LAN.
   - Clarify SAFE_MODE env var and when to use it.
   - *Why:* Security posture change must be explicit before launch.

3. **Test-plan coverage for high-risk paths (1 day)**
   - Per `tests/test-plan.md`, P0 suites are: resume-download contract + jobs-link sanitization.
   - Add integration tests for base-resume compile error paths (CTAN timeout, invalid .tex, etc.).
   - Add E2E test for "apply without tailor" path (resume_mode='base').
   - *Why:* P0 suites block production per test-plan guidance.

### Tier 2: Should complete before or shortly after v1 launch (high-priority bugs)

4. **Verify apply-finisher end-to-end on prod ATS boards (1 day)**
   - Current testing is on Cloudflare + Notion research clones. Smoke-test against 3-5 real Greenhouse + Ashby companies (not submitting, dry_run=true).
   - Document any ATS-specific quirks (custom-Q sets, field order, etc.) found.
   - *Why:* Form variability across companies is flagged as an open question in gap-synthesis.md. Real testing will reveal gaps early.

5. **Close issue #3 (onboarding data hygiene) (< 1 day)**
   - When user re-runs onboarding, clear existing jobs from the DB.
   - Add a confirmation dialog: "This will delete all existing jobs. Continue?"
   - *Why:* Affects user experience after the first setup. Low risk but high UX impact.

6. **Implement issue #50 (JobSpy hardening) (1–2 days)**
   - Make user-agent configurable per fetcher.
   - Add retry wrapper with exponential backoff.
   - Update Adzuna fetcher to use modern user-agent.
   - *Why:* Affects discovery reliability. Can ship post-v1 if needed, but helps with early-user experience.

### Tier 3: Post-v1 scope (prioritized)

7. **Issue #35: Multi-provider BYOK (2–3 days)**
   - Re-enable provider picker in onboarding.
   - Plumb provider choice to tailor + review workers (drop hardcoded `--model openai/...`).
   - Add OpenRouter base URL to `ALLOWED_API_KEY_NAMES`.
   - *Why:* Unblocks broader user base (non-OpenAI users). Clearly scoped; ~75% of code already exists (gate worker works).

8. **Issue #61: Docker consolidation + autonomous toggle (2 days)**
   - Collapse four containers → single app with asyncio supervisor.
   - Host Chrome via CDP instead of Chromium in image.
   - Replace power menu + manual sync with single autonomous toggle.
   - *Why:* Huge UX improvement ("docker compose up" works out of the box). Design locked; implementation straightforward.

9. **Finisher vision-fallback (agent-browser tool upgrade) (1 day)**
   - When AX-tree is empty (Ashby rendering quirk?), fall back to screenshot + Claude vision.
   - Currently deferred in issue #59 out-of-scope.
   - *Why:* Robustness for edge-case forms. Nice-to-have, not critical.

---

## 10. Top 5 Risks Ranked

**Risk ranking by impact × probability:**

1. **Finisher model deprecation (High impact, Medium probability)**
   - gpt-5.4 pricing or availability could shift. Cost calculus for auto-apply may break.
   - *Mitigation:* Track cost_events closely; document model choice rationale in code; prepare fallback model list.

2. **Greenhouse form variability (High impact, Medium probability)**
   - Finisher is hardened for Cloudflare + one engineer-role Ashby. Different companies on the same ATS may have radically different custom-Q sets.
   - *Mitigation:* Smoke-test on 5+ real Greenhouse orgs pre-launch. Log ATS + custom-Q signature so failures can be correlated.

3. **React-Select brittleness via agent-browser version drift (Medium impact, Medium probability)**
   - aria-labelledby resolution bug in v0.27.0 is now worked around in prompts. Future versions may break or re-break this.
   - *Mitigation:* Document agent-browser version in pyproject.toml pinning. Add test that validates Greenhouse combobox opens on current version.

4. **Simplify extension compatibility (Medium impact, Medium probability)**
   - Simplify v2.4.x is hardcoded in code. v2.5+ could change shadow-root structure or autofill behavior.
   - *Mitigation:* Document Simplify version dependency; add test; monitor Simplify release notes.

5. **CTAN cache stale / LaTeX compile silent fail (Medium impact, Low probability)**
   - Network timeout during tectonic CTAN fetch could corrupt cache or leave compiled PDFs truncated. User sees generic error.
   - *Mitigation:* Pre-warm cache at image build time (done). Add explicit CTAN timeout logging in base_compile.py. Consider retry with cache invalidation.

---

**Compiled by:** File search specialist (read-only analysis)  
**Evidence base:** git log -10, git status, gh issue view, .research/ folders, test-plan.md, SECURITY.md, CONTRIBUTING.md
