# Architecture

## Overview
The runtime is a producer/consumer pipeline on a shared SQLite queue:
- `main.py` (producer) discovers jobs and inserts rows with `status='NEW'`.
- `scripts/process_new_jobs.py` (consumer) drains NEW backlog, calls the root gate agent, and persists `QUALIFIED`/`FILTERED` decisions.
- Retry metadata (`agent_retry_count`, `agent_next_retry_at`) allows bounded retries before terminal failure (`agent_failed_at`), with optional ntfy alerts.
- `scripts/run_resume_tailor.py` runs an on-demand pi-mono resume tailor loop that reads job context from SQLite, edits `config/resume_content.yaml`, renders `.tex`, compiles PDF, and enforces one-page output.

```mermaid
flowchart TD
    timer["job-discovery.timer"]
    discovery["main.py discovery producer"]
    worker["process_new_jobs.py --loop consumer"]
    tailor["process_qualified_jobs.py --loop tailor"]
    db["SQLite job_postings + tailor_runs"]
    gate["RootApplyDecider (ADK)"]
    pi["pi-mono coding agent"]
    ntfy["ntfy.sh (optional alerts)"]

    timer --> discovery
    discovery -->|insert NEW jobs| db
    worker -->|load pending NEW/retry-ready| db
    worker --> gate
    gate -->|APPLY/SKIP| worker
    worker -->|persist QUALIFIED/FILTERED| db
    worker -->|terminal failure alert| ntfy
    tailor -->|claim QUALIFIED jobs| db
    tailor --> pi
    pi -->|tailored resume| tailor
    tailor -->|record SUCCESS/FAILED| db
    tailor -->|failure alert| ntfy
```

## Discovery Side
- `main.py` loads `companies.yaml` and optional `search_criteria.yaml` + `candidate_profile.yaml`, resolves default board search terms, fetches Greenhouse/Workday/JobSpy jobs, deduplicates, and inserts into SQLite.
- Job board terms are now config-driven with fallback defaults derived from profile/search config rather than hardcoded senior-role terms.

## Queue + Persistence
- `src/database/schema.sql` defines queue and stats tables and now includes retry columns:
  - `agent_retry_count`
  - `agent_next_retry_at`
- `DatabaseManager` owns:
  - queue selection (`get_jobs_pending_agent_processing`)
  - success persistence (`record_agent_decision`)
  - transient retry persistence (`record_agent_retry`)
  - terminal failure marking (`mark_job_agent_terminal_failed`)
  - manual requeue support (`reset_agent_failure_state`)

## Gate Worker
- `scripts/process_new_jobs.py`:
  - processes full pending backlog (bounded by per-cycle `--limit`)
  - retries per job using configurable backoff
  - marks terminal failure after max retries
  - sends optional ntfy alerts for terminal failures and startup config failures
- `scripts/run_pipeline_once.py` provides a one-shot orchestrator (`discovery -> one gate batch`) for operations and testing.

## Resume Tailor Worker (Autonomous)
- `scripts/process_qualified_jobs.py` is the autonomous tailor worker daemon.
- Claims QUALIFIED jobs from SQLite via atomic `BEGIN IMMEDIATE` transactions with claim tokens.
- State tracked in a separate `tailor_runs` table (PENDING -> SUCCESS/FAILED) with retry backoff.
- Invokes `run_resume_tailor_pipeline` from `src/agents/resume_tailor_pi/` for each claimed job.
- Restores `config/resume_content.yaml` to its baseline state after every run (success or failure).
- Preflight checks validate `pi` command, `latexmk`, and database path before entering the loop.
- Generated artifacts land in `data/tailored_resumes/<job_hash>/resume_tailored.{tex,pdf}`.
- Supports both `--once` (one-shot) and `--loop` (persistent daemon) modes.
- Environment knobs: `TAILOR_POLL_INTERVAL_SECONDS`, `TAILOR_MAX_RETRIES`, `TAILOR_RETRY_BACKOFF_SECONDS`, `TAILOR_RETRY_BACKOFF_MULTIPLIER`, `TAILOR_CLAIM_LEASE_SECONDS`, `TAILOR_OUTPUT_DIR`.

## Resume Tailor Pipeline (Pi-Mono)
- Canonical source of truth is `config/resume_content.yaml`; generated `.tex` is an artifact.
- Tools-first command surface lives in `scripts/resume_tailor_tools.py`:
  - `db-get-job-context`
  - `load-resume-yaml` / `save-resume-yaml`
  - `render-resume-tex`
  - `compile-resume`
  - `get-page-count`
- Runtime loop in `src/agents/resume_tailor_pi/runtime.py`:
  - initial content pass
  - exactly two content readjust retries on overflow
  - bounded balanced layout compression fallback
  - explicit failure if output still exceeds one page
- Optional per-run branch isolation is supported through `--create-git-branch`.

## Prompt/Profile
- Gate prompt candidate context is config-backed:
  - primary source: `config/candidate_profile.yaml`
  - optional override: `CANDIDATE_PROFILE_PATH`
  - fallback: built-in context string in prompts module

## Deployment Topology
- `deploy/job-discovery.timer` + `deploy/job-discovery.service` for periodic producer runs.
- `deploy/job-agent-worker.service` for continuous gate queue draining.
- `deploy/job-tailor-worker.service` for continuous tailor queue draining (persistent daemon, `Restart=always`, 30s backoff). Requires pi-mono and latexmk.
- Optional `deploy/job-agent-alert@.service` as a systemd `OnFailure` hook.
