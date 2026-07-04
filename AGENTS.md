# Agentic Job Applier Guide — Codex / AGENTS.md-aware tools

## Read this first

Authoritative architecture context lives under **`spec/`**. Start at [`spec/index.md`](spec/index.md) — it routes you to the right focused doc for your task (architecture, components, data models, interfaces, workflows, dependencies, review notes). Every claim in those docs is anchored to a `path:line` evidence citation. The consolidated read is `spec/spec.md` (GitHub-renderable with mermaid blocks) or `spec/spec.html` (rich, opens in any browser).

When code and the spec disagree, treat current source as authoritative and update the spec to match.

## Purpose
- This repository discovers jobs from Greenhouse, Workday, Lever, Ashby, iCIMS, Taleo, JobSpy-backed boards (Indeed, LinkedIn, Glassdoor), Remotive, Himalayas, Working Nomads, The Muse, Adzuna, Startup Jobs, curated GitHub repos (e.g. SimplifyJobs internships), and direct career-page watchers. Postings are normalized into a shared model, stored in SQLite, and optionally driven through gate / tailor / review / apply workers.
- The project is organized so fetchers gather raw postings, the database layer persists normalized records, and operational scripts expose common workflows for discovery, querying, and agent processing.

## Key Entry Points
- `api/main.py`: FastAPI app; the real runtime entry point. Its lifespan hook runs all DB migrations, then starts `LoopSupervisor`, which owns the discovery + gate + tailor + apply asyncio tasks for the life of the process.
- `main.py`: Importable async entry for the discovery loop (`run_discovery_loop`); also runnable directly as `python main.py` for discovery-only dev use.
- `src/database/db_manager.py`: Owns SQLite connection management, schema initialization, crawl tracking, and agent-processing persistence.
- `src/models/job_posting.py`: Defines the normalized `JobPosting` model that all fetchers return before persistence.
- `scripts/process_new_jobs.py`: CLI shim for the gate worker (flags: `--once`, `--loop`). The supervisor imports and calls `run_gate_loop()` from this module directly; the script is also usable standalone for local dev. Gate decisions use Instructor-backed structured-output calls via `run_gate_with_provider`.
- `scripts/process_qualified_jobs.py`: CLI shim for the tailor + review worker, same dual-mode pattern.
- `scripts/process_apply_jobs.py`: CLI shim for the apply worker; includes a Chrome reachability preflight before claiming any job.

## Major Subsystems
- `src/fetchers/`: Source-specific integrations for every board listed in Purpose, plus shared helpers (`base_fetcher`, `ats_scanner`, `fuzzy_dedup`, `liveness_checker`, `errors`).
- `src/orchestrator/`: Discovery orchestration, insert pipeline (filter/qualify), and per-ATS fetcher wrappers (`fetchers/greenhouse.py`, `fetchers/workday.py`, `fetchers/jobspy.py`, etc.).
- `src/digest/`: Email digest system — `sender.py` (per-subscriber filtering, category grouping, dedup, Resend delivery), `pages.py` (self-contained HTML signup and manage-preferences pages served by FastAPI).
- `src/utils/notification_protocol.py`, `src/utils/notification_dispatcher.py`, `src/utils/notification_adapters/`: Notification protocol — `NotificationChannel` interface with `NtfyAdapter` and `EmailAdapter`, `NotificationDispatcher` for routing alerts.
- `src/utils/`: Cross-cutting helpers for logging, deduplication, cost tracking, notifications, and path resolution used across orchestrators and workers.
- `src/agents/apply_decider/` (under `src/agents/root_apply_decider/`): Gate agent — qualifies or rejects NEW postings against the candidate profile using Instructor-backed structured-output LLM calls.
- `src/agents/resume_tailor/`: LaTeX tailor + reviewer pipeline — rewrites resume bullets for a specific job, compiles via tectonic, and selects the best variant (base / v1 / v2) via a 3-axis LLM reviewer.
- `src/agents/apply_worker/`: Playwright-driven apply worker — connects to host Chrome over CDP, triggers Simplify autofill, evaluates the binary submit gate, and either submits or hands off to human review.
- `src/agents/apply_finisher/`: Pydantic-AI agent with 8 typed BYO Playwright tools for post-Simplify Greenhouse and Ashby form completion.
- `api/routers/digest.py`: Digest API endpoints — subscriber signup (double opt-in with Turnstile CAPTCHA), email confirmation, preference management, admin-triggered digest sends.
- `tests/`: Integration-style tests that validate the database lifecycle, deduplication, crawl tracking, model normalization, digest filtering, and notification dispatch.

## Documentation Standard
- Every Python callable should start with plain-English sentence(s) describing what it does.
- Every callable docstring should then include `Purpose:`, `Args:`, and `Output:` sections.
- The `if __name__ == "__main__":` guard is the only exception and should not receive a docstring.
- Inline comments should appear frequently enough that a reader can understand what the code is doing, why the step exists, and how the flow fits the larger pipeline.

## Commenting Guidance
- Prefer comments on logical blocks rather than every single line.
- Use comments to explain normalization rules, persistence choices, guardrails, and non-obvious control flow.
- Avoid comments that merely restate syntax or repeat a function's name.

## Source of Truth
- Start with `README.md` for orientation and follow links from there.
- If code and documentation disagree, treat the current source code as authoritative and update surrounding documentation to match.

## Test Flags
- Default deterministic test suite (network-free): `uv run pytest -q`
- Run only deterministic integration coverage: `uv run pytest -q tests/test_scraper_to_agent_integration.py`
- Opt-in live model end-to-end tests: `uv run pytest -q --run-live-agent-e2e -m live_agent_e2e`
- Live model tests require `OPENAI_API_KEY` and are skipped unless `--run-live-agent-e2e` is passed.

## Resume Tailor Worker (Per-Stage Mode)
- The tailor loop runs as an asyncio task owned by `api/services/supervisor.py:LoopSupervisor`. On every cycle it sweeps stale runs and reads `automation.tailor_mode` from `system_settings`. `scripts/process_qualified_jobs.py` is a standalone CLI shim that calls the same `run_gate_loop` / `run_tailor_loop` logic and is used for local dev or the legacy systemd deployment.
- When the mode is `autonomous` or `both` the loop claims one QUALIFIED job and runs `src.agents.resume_tailor.run_tailor_review_pipeline`. When the mode is `opt_in` the loop idles — user-triggered runs from the dashboard are the only way to tailor.
- The pipeline is a single async function (Instructor-backed structured LLM calls) covering tailor → patch → compile → reviewer → optional retry → 3-way pick. It writes both `tailor_runs` and the matching `review_runs` row from one process; there is no separate review worker.
- The pipeline reads `config/resume.tex` (re-validated against `docs/resume-tex-contract.md` at runtime), builds a deterministic bullet manifest via `src/agents/resume_tailor/locator.py`, and splices LLM rewrites in via the byte-offset patcher (`src/agents/resume_tailor/patcher.py`). The on-disk `.tex` is never mutated by a tailor run — every patched variant lands in the per-run artifact dir.
- State lives in `tailor_runs` (PENDING → RUNNING → SUCCESS/FAILED, plus a `deleted_at` soft-delete column) and `review_runs` (verdicts: PASS, TAILORED, BASE, FAIL, NO_IMPROVEMENT, PAGE_FIT_FAILED). The DB retains legacy `*_yaml_path` columns (`artifact_yaml_path`, `selected_yaml_path`, `fallback_base_yaml_path`); the pipeline writes `""` to them — they have no consumers.
- Preflight requires `tectonic` (the default compiler; `RESUME_COMPILER=latexmk` falls back to the legacy path) and a resolvable database path.
- Generated artifacts land in `<TAILOR_OUTPUT_DIR>/<job_hash>/{base,tailored_v1,tailored_v2}/...` (default `data/tailored_resumes/...`).
- Systemd unit: `deploy/job-tailor-worker.service`.
- Environment knobs: `TAILOR_POLL_INTERVAL_SECONDS`, `TAILOR_MAX_RETRIES`, `TAILOR_CLAIM_LEASE_SECONDS`, `TAILOR_OUTPUT_DIR`, `RESUME_TAILOR_MODEL`, `RESUME_REVIEWER_MODEL`, plus `TAILOR_MODE` / `REVIEW_MODE` for first-boot seeding of the per-stage modes.

## Apply Finisher Worker
- `src/agents/apply_finisher/`: Pydantic-AI agent that picks up after Simplify Copilot autofill and drives Greenhouse and Ashby form completion to the point of submission.
- ATS scope: Greenhouse and Ashby only. Other ATSes land `NEEDS_REVIEW` without finisher involvement.
- The agent is equipped with 8 typed BYO Playwright tools: field detection, value injection, file upload, dropdown selection, checkbox/radio handling, form-state snapshot, page-scroll, and submit-click.
- Binary submit gate (evaluated inside `src/agents/apply_worker/browser.py:_run_application_flow`): `all_required_filled AND no_tier3_deferred AND (no_tier2_pending OR all_tier2_drafts >= threshold)`. If the gate fails the apply lands `NEEDS_REVIEW`; the human-review queue at `/human-review` is the canonical approval point.
- Soft cost cap: $0.20 per apply run, log-only (no hard abort).
- `SAFE_MODE=true` env var disables auto-submit globally regardless of gate outcome; the worker still fills forms and writes `apply_handoffs` rows.
- Runtime caches: `config/defer_rules.yaml` (user-tunable Tier-3 regexes), `data/answer_cache.yaml` (machine-mutable, schema_version 1).
- DB columns: `apply_handoffs.deferred_questions_json`, `apply_handoffs.finisher_diagnostics_json`.
- REST surface: `POST /api/jobs/{job_hash}/apply` (409 on in-flight conflict), `GET /api/apply-runs/{id}`, `DELETE /api/apply-runs/{id}`.
- Environment knobs: `SAFE_MODE`, `LITELLM_LOCAL_MODEL_COST_MAP`.

## Email Digest System
- `src/digest/sender.py`: Queries `job_postings` for roles fetched since each subscriber's `last_digest_at`, filters by per-subscriber preferences, groups by category, renders an HTML email, and delivers via the Resend API. On success, writes `digest_sends` rows and bumps `last_digest_at`.
- Subscriber preferences: `role_level` (intern, new-grad, either), `allowed_categories` (Software, AI/ML/Data, Hardware, Design, Product, Quant, Business), `allowed_terms` (Fall 26, Spring 27, Summer 27), `location_preference` (remote, on-site, either), `excluded_companies`.
- Two screens apply to every subscriber regardless of preferences: senior-marker titles are dropped, and roles whose resolved posted date is older than 30 days are aged out (Workday-style "Posted N Days Ago" strings resolve against `fetched_at`; unresolvable dates pass through). The freshness guard exists because the digest windows on `fetched_at` — without it, any newly-added source dumps its entire backlog into one email.
- Category routing: every job is classified at digest-render time by the title-based classifier in `src/digest/categorize.py` (source-provided labels like Simplify's are only a fallback for titles no rule matches). The field filter is strict — subscribers with field selections only receive jobs classified into them; "Other" only reaches subscribers with no field selection. Role-level matching is source-aware: listings from the Simplify new-grad tracker count as new-grad even with plain titles.
- The public signup page (`/subscribe`) is CS-scoped: chips for Software, AI/ML/Data, Hardware, Design, Product, Quant. Business has no public chip — non-CS subscribers (e.g. business majors) are added manually via Claude sessions by inserting `email_subscribers` rows with `fields=["business"]`; the digest pipeline then handles their emails identically (the `business` field id and Business category remain fully supported in the sender).
- The discovery pipeline is 100% generic. All fetchers accept arbitrary search terms and companies. The CS/tech focus is purely configuration (`config/search_criteria.yaml`, `config/companies.yaml`, `config/filters.yaml`). Other fields can be supported by adding config profiles without code changes.

## Production Deployment

The canonical production instance runs on bare-metal Ubuntu LTS (i5-6500, 8GB RAM, 1.8TB storage) using `uv` (no Docker, pip, or Chrome). User-level systemd units with linger keep the services running:

- `job-api.service` — FastAPI on `localhost:8000`
- `job-discovery.timer` — discovery cycle every 15 minutes
- Daily digest cron at 3pm EST: `curl -s -X POST http://localhost:8000/api/digest/send`

The digest signup page is exposed via Cloudflare Tunnel at `jobs.joeyspagnoli-cloud.cc`. Host-based middleware locks that subdomain to digest routes only; the dashboard is only accessible on `localhost:8000`.

Email delivery uses Resend (free tier, 3K emails/month). Bot protection on the signup page uses Cloudflare Turnstile in invisible mode.

## Discovery Pipeline

The pipeline is 100% field-agnostic. All fetchers accept arbitrary search terms and companies. The CS/tech focus is purely config — other fields (business, finance, engineering) can be supported by adding YAML config without code changes.

Key operational patterns:
- **`search_text` per-company overrides:** Companies like Salesforce need `search_text: "internship"` instead of the default `"intern"` to avoid matching "internal" roles. Set in `companies.yaml`.
- **Digest categories are not set by fetchers.** `digest_category` tagging was removed — the digest classifies every job by title at render time (`src/digest/categorize.py`), so boards and ATS sources need no category config and cross-field contamination is handled in one place.
- **`exclude_title_patterns`:** Regex patterns in `search_criteria.yaml` that filter out senior/staff/manager roles before storage. `filters.yaml` also hard-rejects seniority markers via `hard_filters.exclude_title_patterns`, which covers the curated GitHub-tracker path.
- **No `skip_job_filter`:** Business/CRE/banking sources run through the normal filter pipeline; early-career program titles (Summer Analyst, Trainee, Rotational, Analyst Program, ...) are part of `filters.yaml` `require_title_patterns`.
- **Curated GitHub trackers skip the title gate:** the `github_repos` family uses a JobFilter clone with no `require_title_patterns` (see `build_curated_filter`) because tracker listings are early-career by construction but mostly plain-titled ("Software Engineer").
- **`max_days_old` and term filtering:** The GitHub repo fetcher auto-computes current term windows (e.g. Fall 2026 through Fall 2027) and filters by posting date.
- **Job hash dedup:** SHA-256 of `(source_url, company, title)` — `source` was deliberately removed after it caused 35% duplicate rows when the same job appeared from multiple search queries.
- **DB TTL:** 90-day TTL for `crawl_history` and stale `job_postings`, enforced on each discovery cycle.

### Adding a new field (subscriber category)

All fields share one database and one discovery instance — the subscriber
`fields` column multiplexes who sees what, and the title classifier keeps
fields from contaminating each other. To support a new field:
1. Add companies to `companies.yaml` with appropriate ATS config and `search_text` overrides
2. Add an Indeed board entry (e.g. `Indeed_Business`, `Indeed_Design`) with field-specific search terms and metro areas
3. Add classification rules for the field's titles in `src/digest/categorize.py` and the field id in `_FIELD_TO_CATEGORY` in `src/digest/sender.py`
4. Only add a chip in `src/digest/pages.py` if the field belongs on the public CS-scoped signup page — non-CS subscribers are inserted directly into `email_subscribers` via a Claude session instead

### Known unsupported ATS platforms

SmartRecruiters (Canva, Two Sigma), Gem ATS (Retool), Phenom People (Snowflake), and proprietary systems (Tesla, TikTok/ByteDance, Rippling) were investigated and confirmed unsupported. Jobs from these companies are discovered via Indeed/LinkedIn aggregators only.

## Opt-In API Surface
- `POST /api/jobs/{job_hash}/tailor` (`api/routers/tailor_runs.py`): enqueues a FastAPI BackgroundTask that runs `run_tailor_review_pipeline`. Returns 409 with `code=MODE_AUTONOMOUS` when `tailor_mode=autonomous`, `code=RUN_ALREADY_EXISTS` when a non-deleted active run already exists, or `code=BUDGET_EXCEEDED` when the monthly budget is exhausted.
- `GET /api/tailor-runs/{id}`, `DELETE /api/tailor-runs/{id}`, `POST /api/tailor-runs/{id}/retry` (`api/routers/tailor_runs.py`): back the JobsPage row's polling, soft-delete, and "delete & retry" buttons.
- `POST /api/jobs/{job_hash}/apply` (`api/routers/apply_runs.py`): accepts `{resume_mode: 'base' | 'tailored'}`, spawns a detached asyncio task for the browser flow.
- `GET /api/apply-runs/{id}`, `DELETE /api/apply-runs/{id}` (`api/routers/apply_runs.py`).
- `GET/PATCH /api/system-settings/automation` (`api/routers/system_settings.py`): drive the Automation card on the Settings page. The supervisor re-reads the modes within ~1.5 s of a toggle via `notify_mode_changed()`.

## Autonomy End Goal
- This repository can be cloneable on a home server, configured once, and run autonomously through discovery → gate → tailor → review → apply.
- Per-stage modes (`autonomous | opt_in | both`) let users dial in how much of that pipeline runs without their intervention — power users keep gate=autonomous + tailor=opt_in if they want manual control of the costly stages while letting discovery run on its own.
- Ongoing human involvement should be limited to updating preferences, the base resume, and reference files.
