# Agentic Job Applier Guide

## Purpose
- This repository discovers jobs from Greenhouse, Workday, Lever, Ashby, iCIMS, Taleo, JobSpy-backed boards (Indeed, LinkedIn, Glassdoor), Remotive, Himalayas, Working Nomads, The Muse, Adzuna, Startup Jobs, curated GitHub repos (e.g. SimplifyJobs internships), and direct career-page watchers. Postings are normalized into a shared model, stored in SQLite, and optionally driven through gate / tailor / review / apply workers.
- The project is organized so fetchers gather raw postings, the database layer persists normalized records, and operational scripts expose common workflows for discovery, querying, and agent processing.

## Key Entry Points
- `main.py`: Runs the async discovery cycle, coordinates fetchers, deduplicates results, persists jobs, and updates crawl metrics.
- `src/database/db_manager.py`: Owns SQLite connection management, schema initialization, crawl tracking, and agent-processing persistence.
- `src/models/job_posting.py`: Defines the normalized `JobPosting` model that all fetchers return before persistence.
- `scripts/process_new_jobs.py`: Pulls NEW jobs from the database, builds the agent prompt payload, runs the ADK decider, and records the resulting status.

## Major Subsystems
- `src/fetchers/`: Source-specific integrations for every board listed in Purpose, plus shared helpers (`base_fetcher`, `ats_scanner`, `fuzzy_dedup`, `liveness_checker`, `errors`).
- `src/utils/`: Cross-cutting helpers for logging, deduplication, cost tracking, notifications, and path resolution used across orchestrators and workers.
- `src/agents/`: Agent schemas and builder code for the apply/skip workflow.
- `src/agents/apply_finisher/`: Pydantic AI agent + 8 typed BYO Playwright tools that drive Greenhouse and Ashby form completion after Simplify autofill, evaluates the binary submit gate, and clicks Submit when the gate passes.
- `tests/`: Integration-style tests that validate the database lifecycle, deduplication, crawl tracking, and model normalization.

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
- `scripts/process_qualified_jobs.py`: Polls the database and, on every cycle, sweeps stale tailor runs and reads `automation.tailor_mode` from `system_settings`.
- When the mode is `autonomous` or `both` the worker claims one QUALIFIED job and runs `src.agents.resume_tailor.run_tailor_review_pipeline`. When the mode is `opt_in` the worker idles — user-triggered runs from the dashboard are the only way to tailor.
- The pipeline is a single async function (Instructor-backed structured LLM calls) covering tailor → patch → compile → reviewer → optional retry → 3-way pick. It writes both `tailor_runs` and the matching `review_runs` row from one process; there is no separate review worker.
- The pipeline reads `config/resume.tex` (re-validated against `docs/resume-tex-contract.md` at runtime), builds a deterministic bullet manifest via `src/agents/resume_tailor/locator.py`, and splices LLM rewrites in via the byte-offset patcher (`src/agents/resume_tailor/patcher.py`). The on-disk `.tex` is never mutated by a tailor run — every patched variant lands in the per-run artifact dir.
- State lives in `tailor_runs` (PENDING → RUNNING → SUCCESS/FAILED, plus a `deleted_at` soft-delete column) and `review_runs` (verdicts: PASS, TAILORED, BASE, FAIL, NO_IMPROVEMENT, PAGE_FIT_FAILED). The DB still carries the legacy `*_yaml_path` columns; Phase 2+ writes `""` to them (they're semantically dead pending a future cleanup PR).
- Preflight requires `tectonic` (the default compiler; `RESUME_COMPILER=latexmk` falls back to the legacy path) and a resolvable database path.
- Generated artifacts land in `<TAILOR_OUTPUT_DIR>/<job_hash>/{base,tailored_v1,tailored_v2}/...` (default `data/tailored_resumes/...`).
- Systemd unit: `deploy/job-tailor-worker.service`.
- Environment knobs: `TAILOR_POLL_INTERVAL_SECONDS`, `TAILOR_MAX_RETRIES`, `TAILOR_CLAIM_LEASE_SECONDS`, `TAILOR_OUTPUT_DIR`, `RESUME_TAILOR_MODEL`, `RESUME_REVIEWER_MODEL`, plus `TAILOR_MODE` / `REVIEW_MODE` for first-boot seeding of the per-stage modes.

## Apply Finisher Worker
- `src/agents/apply_finisher/`: Pydantic AI agent that picks up after Simplify Copilot autofill and drives Greenhouse and Ashby form completion to the point of submission.
- ATS scope: Greenhouse and Ashby only. Other ATSes continue to land `NEEDS_REVIEW` without finisher involvement.
- The agent is equipped with 8 typed BYO Playwright tools: field detection, value injection, file upload, dropdown selection, checkbox/radio handling, form-state snapshot, page-scroll, and submit-click.
- Binary submit gate (evaluated inside `src/agents/apply_worker/browser.py:_run_application_flow`): `all_required_filled AND no_tier3_deferred AND (no_tier2_pending OR all_tier2_drafts >= threshold)`. If the gate fails the apply lands `NEEDS_REVIEW`; the human-review queue at `/human-review` is the canonical approval point.
- Soft cost cap: $0.20 per apply run, log-only (no hard abort).
- `SAFE_MODE=true` env var disables auto-submit globally regardless of gate outcome; the worker still fills forms and writes `apply_handoffs` rows.
- Runtime caches: `config/defer_rules.yaml` (user-tunable Tier-3 regexes), `data/answer_cache.yaml` (machine-mutable, schema_version 1).
- New DB columns: `apply_handoffs.deferred_questions_json`, `apply_handoffs.finisher_diagnostics_json`.
- New REST surface: `POST /api/jobs/{job_hash}/apply` (409 on in-flight conflict), `GET /api/apply-runs/{id}`, `DELETE /api/apply-runs/{id}`.
- Environment knobs: `SAFE_MODE`, `LITELLM_LOCAL_MODEL_COST_MAP`.

## Opt-In API Surface
- `POST /api/jobs/{job_hash}/tailor` enqueues a FastAPI BackgroundTask that runs the same `run_tailor_review_pipeline`. Returns 409 with `code=MODE_AUTONOMOUS` when `tailor_mode=autonomous`, `code=RUN_ALREADY_EXISTS` when a non-deleted active run already exists, or `code=BUDGET_EXCEEDED` when the monthly budget is exhausted.
- `GET /api/tailor-runs/{id}` and `DELETE /api/tailor-runs/{id}` back the JobsPage row's polling and "delete & retry" buttons.
- `GET/PATCH /api/system-settings/automation` drive the Automation card on the Settings page. The worker re-reads the modes on every poll cycle, so flips take effect within one cycle without a restart.

## Autonomy End Goal
- This repository can be cloneable on a home server, configured once, and run autonomously through discovery → gate → tailor → review → apply.
- Per-stage modes (`autonomous | opt_in | both`) let users dial in how much of that pipeline runs without their intervention — power users keep gate=autonomous + tailor=opt_in if they want manual control of the costly stages while letting discovery run on its own.
- Ongoing human involvement should be limited to updating preferences, the base resume, and reference files.
