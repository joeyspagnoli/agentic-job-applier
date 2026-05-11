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
- When the mode is `autonomous` or `both` the worker claims one QUALIFIED job and runs `src.agents.resume_tailor_adk.run_tailor_review_pipeline`. When the mode is `opt_in` the worker idles — user-triggered runs from the dashboard are the only way to tailor.
- The ADK pipeline operates only on an in-memory copy of `config/resume_content.yaml`; the on-disk YAML is never mutated by a tailor run.
- State lives in `tailor_runs` (PENDING → RUNNING → SUCCESS/FAILED, plus a `deleted_at` soft-delete column) and `review_runs` (verdicts: PASS, TAILORED, BASE, FAIL, NO_IMPROVEMENT, PAGE_FIT_FAILED).
- Preflight only requires `latexmk` and a resolvable database path; the pi binary is no longer used.
- Generated artifacts land in `<TAILOR_OUTPUT_DIR>/<job_hash>/{base,tailored_v1,tailored_v2}/...` (default `data/tailored_resumes/...`).
- Systemd unit: `deploy/job-tailor-worker.service`.
- Environment knobs: `TAILOR_POLL_INTERVAL_SECONDS`, `TAILOR_MAX_RETRIES`, `TAILOR_CLAIM_LEASE_SECONDS`, `TAILOR_OUTPUT_DIR`, `RESUME_TAILOR_MODEL`, `RESUME_REVIEWER_MODEL`, plus `TAILOR_MODE` / `REVIEW_MODE` for first-boot seeding of the per-stage modes.

## Opt-In API Surface
- `POST /api/jobs/{job_hash}/tailor` enqueues a FastAPI BackgroundTask that runs the same `run_tailor_review_pipeline`. Returns 409 when `tailor_mode=autonomous` or when a non-deleted run already exists.
- `GET /api/tailor-runs/{id}` and `DELETE /api/tailor-runs/{id}` back the JobsPage row's polling and "delete & retry" buttons.
- `GET/PATCH /api/system-settings/automation` drive the Automation card on the Settings page. The worker re-reads the modes on every poll cycle, so flips take effect within one cycle without a restart.

## Autonomy End Goal
- This repository can be cloneable on a home server, configured once, and run autonomously through discovery → gate → tailor → review → apply.
- Per-stage modes (`autonomous | opt_in | both`) let users dial in how much of that pipeline runs without their intervention — power users keep gate=autonomous + tailor=opt_in if they want manual control of the costly stages while letting discovery run on its own.
- Ongoing human involvement should be limited to updating preferences, the base resume, and reference files.
