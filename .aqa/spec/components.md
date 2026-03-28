# Components

## Orchestrator
- **`main.py`** (693 lines): async discovery producer that loads config/profile inputs, resolves search terms, fetches source boards, filters titles, deduplicates, inserts NEW rows, and records crawl/daily stats.

## Data & Persistence
- **`DatabaseManager`** (2188 lines): async SQLite wrapper with schema bootstrap, claim-based queue methods, retries, and stage-specific lifecycle helpers.
- **`schema.sql`** (193 lines): defines `job_postings`, `crawl_history`, `daily_stats`, `tailor_runs`, `review_runs`, `apply_runs` plus indexes/check constraints.
- **Gate queue methods**: `get_jobs_pending_agent_processing`, `record_agent_decision`, `record_agent_retry`, `mark_job_agent_terminal_failed`, `reset_agent_failure_state`.
- **Tailor methods**: `claim_next_tailor_job`, `record_tailor_success`, `record_tailor_failure`, `mark_stale_tailor_runs_failed`.
- **Review methods**: `claim_next_review_job`, `record_review_success`, `record_review_failure`, `mark_stale_review_runs_failed`.
- **Apply methods**: `migrate_apply_schema`, `claim_next_apply_job`, `record_apply_success`, `record_apply_failure`, `mark_stale_apply_runs_failed`, `get_apply_failure_count`.

## Models
- **`JobPosting`** (222 lines): normalized posting model with canonical hash generation, remote inference, job-type normalization, and DB serialization.

## Fetchers
- **`base_fetcher.py`** (82 lines): async fetcher interface.
- **`greenhouse_fetcher.py`** (249 lines): Greenhouse API ingestion and normalization.
- **`apify_fetcher.py`** (194 lines): Workday ingestion through Apify actor.
- **`jobspy_fetcher.py`** (308 lines): JobSpy scraping + salary normalization.
- **`errors.py`** (15 lines): `FetchError` runtime classification.

## Utilities
- **`deduplicator.py`** (110 lines): in-batch + DB hash dedup.
- **`logger.py`** (130 lines): loguru setup and cycle summaries.
- **`notifications.py`** (114 lines): ntfy integration.
- **`paths.py`** (54 lines): repo-root and DB path resolution.

## Agent Layers
- **Shared model helper**: `src/agents/shared/model.py` (38 lines) validates credentials and constructs LiteLLM model objects.

### Root Apply/Skip Gate
- `agent.py` (209), `prompts.py` (338), `runtime.py` (132), `schemas.py` (49).
- Consumed by `scripts/process_new_jobs.py` (483).

### Resume Tailor (Pi)
- `schemas.py` (628), `runtime.py` (639), `renderer.py` (321), `compiler.py` (197), `yaml_io.py` (111), `tools.py` (210).
- CLIs: `scripts/run_resume_tailor.py`, `scripts/resume_tailor_tools.py` (250), `scripts/migrate_resume_tex_to_yaml.py` (500).

### Resume Review (Pi)
- `schemas.py` (346), `runtime.py` (334), `prompts.py` (222), `tools.py` (777).
- CLI: `scripts/process_reviewed_resumes.py` (824), `scripts/resume_review_tools.py` (347).

### Browser Apply Worker
- `browser.py` (404): CDP navigation, Simplify detection, resume upload, unresolved field scan, confidence scoring, artifact capture.
- `confidence.py` (278): deterministic weighted checks.
- `field_scanner.py` (266): unresolved-field extraction across frames.
- `resume_upload.py` (197): upload strategy helpers.
- `ats_detection.py` (65), `schemas.py` (222).
- Worker CLI: `scripts/process_apply_jobs.py` (716).

## Operational Scripts
- `scripts/run_pipeline_once.py` (143): one-shot discovery + gate batch.
- `scripts/decide_job.py` (88): single-row gate run.
- `scripts/status.py` (252): job/crawl/daily status summary plus gate retry visibility.
- `scripts/query_jobs.py` (138), `scripts/find_greenhouse_id.py` (140), `scripts/test_fetchers.py` (112).

## Deployment
- Discovery: `deploy/job-discovery.service`, `deploy/job-discovery.timer`.
- Gate: `deploy/job-agent-worker.service`.
- Tailor: `deploy/job-tailor-worker.service`.
- Review: `deploy/job-review-worker.service`.
- Apply: `deploy/job-apply-worker.service` and `deploy/job-apply-chrome.service` (`deploy/start-chrome-cdp.sh`).
- Optional alerts: `deploy/job-agent-alert@.service`.

## Test Surface
- 37 test files under `tests/`, including apply schema parity, apply retry semantics, claim concurrency, tailor/review runtime contracts, and integration pipelines.
