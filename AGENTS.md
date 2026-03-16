# Agentic Job Applier Guide

## Purpose
- This repository discovers jobs from Greenhouse, Workday, and JobSpy-backed boards, normalizes them into a shared model, stores them in SQLite, and optionally runs an ADK-based apply/skip decision step.
- The project is organized so fetchers gather raw postings, the database layer persists normalized records, and operational scripts expose common workflows for discovery, querying, and agent processing.

## Key Entry Points
- `main.py`: Runs the async discovery cycle, coordinates fetchers, deduplicates results, persists jobs, and updates crawl metrics.
- `src/database/db_manager.py`: Owns SQLite connection management, schema initialization, crawl tracking, and agent-processing persistence.
- `src/models/job_posting.py`: Defines the normalized `JobPosting` model that all fetchers return before persistence.
- `scripts/process_new_jobs.py`: Pulls NEW jobs from the database, builds the agent prompt payload, runs the ADK decider, and records the resulting status.

## Major Subsystems
- `src/fetchers/`: Source-specific integrations for Greenhouse, Workday via Apify, and JobSpy-backed sites.
- `src/utils/`: Cross-cutting logging and deduplication helpers used by the orchestrator and scripts.
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
- Start with `.aqa/spec/index.md` for repo orientation and follow its linked architecture, interface, and data-model documents when behavior is unclear.
- If code and documentation disagree, treat the current source code as authoritative and update surrounding documentation to match.

## Test Flags
- Default deterministic test suite (network-free): `uv run pytest -q`
- Run only deterministic integration coverage: `uv run pytest -q tests/test_scraper_to_agent_integration.py`
- Opt-in live model end-to-end tests: `uv run pytest -q --run-live-agent-e2e -m live_agent_e2e`
- Live model tests require `OPENAI_API_KEY` and are skipped unless `--run-live-agent-e2e` is passed.

## Resume Tailor Worker (Autonomous Runtime)
- `scripts/process_qualified_jobs.py`: Claims QUALIFIED jobs from the database and invokes the pi-mono resume tailor pipeline (`run_resume_tailor_pipeline`) for each one.
- Tracks state in a separate `tailor_runs` table (PENDING → SUCCESS/FAILED) with retry backoff.
- The worker restores `config/resume_content.yaml` to its baseline state after every run (success or failure) so sequential jobs start from a clean YAML.
- Preflight checks validate `pi` command, `latexmk`, and database path availability before entering the loop.
- Generated artifacts land in `data/tailored_resumes/<job_hash>/resume_tailored.{tex,pdf}`.
- Systemd unit: `deploy/job-tailor-worker.service`.
- Environment knobs: `TAILOR_POLL_INTERVAL_SECONDS`, `TAILOR_MAX_RETRIES`, `TAILOR_RETRY_BACKOFF_SECONDS`, `TAILOR_RETRY_BACKOFF_MULTIPLIER`, `TAILOR_CLAIM_LEASE_SECONDS`, `TAILOR_OUTPUT_DIR`.

## Autonomy End Goal
- End goal: this repository should be cloneable on a home server, configured once, and then run autonomously to discover jobs and execute the full workflow through job application.
- The system may run asynchronously or in batches, but it should not require day-to-day operator intervention.
- Ongoing human involvement should be limited to updating preferences, the base resume, and reference files.
