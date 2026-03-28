# Codebase Info

## Overview
- Name: agentic-job-applier
- Primary language: Python 3.11+ (`requires-python = ">=3.11"`)
- Purpose: discover jobs, decide apply/skip, tailor resume, review tailored output, and run browser-based apply attempts with captured diagnostics.
- Current scope: full queued runtime exists, but final browser submit remains human-review-first.

## Key Directories
- `src/`
  - `agents/`
    - `root_apply_decider/`: ADK gate (`APPLY` or `SKIP`)
    - `resume_tailor_pi/`: YAML-canonical one-page resume tailoring loop
    - `resume_review_pi/`: post-tailor review and report validation
    - `apply_worker/`: Playwright CDP browser automation + Simplify integration + confidence/field diagnostics
    - `shared/`: shared LiteLLM model bootstrap helper
  - `database/`: SQLite schema and async manager
  - `fetchers/`: Greenhouse, Workday(Apify), JobSpy fetchers
  - `models/`: normalized `JobPosting`
  - `utils/`: deduplication, logging, notifications, path resolution
- `scripts/`: operational CLIs and long-running workers
- `config/`: source targeting, profile/config inputs, canonical resume YAML, optional base resume artifacts
- `deploy/`: systemd units and helper scripts
- `tests/`: 37 Python test files

## Notable Line Counts
- `main.py`: 693
- `src/database/db_manager.py`: 2188
- `src/database/schema.sql`: 193
- `src/models/job_posting.py`: 222
- `scripts/process_new_jobs.py`: 483
- `scripts/process_qualified_jobs.py`: 712
- `scripts/process_reviewed_resumes.py`: 824
- `scripts/process_apply_jobs.py`: 716
- `src/agents/apply_worker/browser.py`: 404

## Runtime Stages
1. Discovery producer inserts `job_postings` rows with `status='NEW'`.
2. Gate worker claims NEW/retry-ready rows and sets `QUALIFIED` or `FILTERED`.
3. Tailor worker claims QUALIFIED jobs and writes `tailor_runs`.
4. Review worker claims successful tailor runs and writes `review_runs`.
5. Apply worker claims successful review runs and writes `apply_runs` (currently dry-run/no submit).

## Deployment Assets
- Producer: `deploy/job-discovery.service` + `deploy/job-discovery.timer`
- Gate worker: `deploy/job-agent-worker.service`
- Tailor worker: `deploy/job-tailor-worker.service`
- Review worker: `deploy/job-review-worker.service`
- Apply worker: `deploy/job-apply-worker.service`
- Chrome CDP host for apply worker: `deploy/job-apply-chrome.service` + `deploy/start-chrome-cdp.sh`
- Optional alert hook: `deploy/job-agent-alert@.service`

## Current Reality Check
- Core queue orchestration is implemented.
- Apply stage currently records `NEEDS_REVIEW` outcomes and diagnostics; auto-submit path is not implemented yet.
- `scripts/status.py` does not yet report tailor/review/apply table summaries.
