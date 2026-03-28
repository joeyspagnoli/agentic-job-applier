# Interfaces & APIs

## Fetcher Interface
- **Base contract (`src/fetchers/base_fetcher.py`)**
  - `fetch_jobs() -> list[JobPosting]` (async abstract)
  - `get_source_name() -> str` (abstract)
- **Provider implementations**
  - Greenhouse: `GreenhouseFetcher(company_name, greenhouse_id)`
  - Workday: `ApifyWorkdayFetcher(company_name, workday_url, max_items=100)`
  - JobSpy: `JobSpyFetcher(site_name, search_term, location="Remote", results_wanted=25, country="USA")`
- **Error type**: `FetchError` for provider/transport failures.

## Database Interface (`DatabaseManager`, 2188 lines)

### Core Lifecycle
- `connect()`, `close()`, async context manager (`__aenter__`, `__aexit__`)
- `create_tables()`

### Job CRUD + Stats
- `insert_job(job_data) -> bool`
- `get_job_by_hash(job_hash) -> dict | None`
- `get_job_by_id(job_id) -> dict | None`
- `get_resume_tailor_job_context(*, job_hash=None, job_id=None) -> dict | None`
- `get_existing_job_hashes(job_hashes) -> set[str]`
- `update_job_status(job_hash, status) -> None`
- `get_jobs_by_status(status, limit=100) -> list[dict]`
- `get_job_count() -> int`
- `get_jobs_today() -> int`
- `start_crawl(source, company=None) -> int`
- `complete_crawl(crawl_id, jobs_found, jobs_new, error=None) -> None`
- `update_daily_stats(...) -> None`

### Gate Queue
- `migrate_agent_schema()`, `_ensure_agent_schema_ready()`
- `get_jobs_pending_agent_processing(limit=100)` (claim-based; lease via `AGENT_CLAIM_LEASE_SECONDS`)
- `record_agent_decision(*, job_hash, agent_result, status)`
- `record_agent_retry(*, job_hash, error, retry_count, next_retry_at)`
- `mark_job_agent_terminal_failed(job_hash, error, retry_count=None)`
- `mark_job_agent_failed(job_hash, error)` (compat alias)
- `reset_agent_failure_state(job_hash)`
- `update_job_agent_result(job_hash, agent_result)`

### Tailor Queue
- `migrate_tailor_schema()`, `_ensure_tailor_schema_ready()`
- `claim_next_tailor_job(*, max_retries, lease_seconds=7200)`
- `record_tailor_success(...)`
- `record_tailor_failure(...)`
- `mark_stale_tailor_runs_failed(*, lease_seconds=7200) -> int`
- `reset_tailor_failure_state(*, job_hash)`
- `get_tailor_runs_for_job(job_hash) -> list[dict]`
- `get_tailor_failure_count(job_hash) -> int`

### Review Queue
- `migrate_review_schema()`, `_ensure_review_schema_ready()`
- `claim_next_review_job(*, max_retries, lease_seconds=7200)`
- `record_review_success(...)`
- `record_review_failure(...)`
- `mark_stale_review_runs_failed(*, lease_seconds=7200) -> int`
- `get_review_failure_count(tailor_run_id) -> int`
- `get_review_runs_for_tailor_run(tailor_run_id) -> list[dict]`

### Apply Queue
- `migrate_apply_schema()`, `_ensure_apply_schema_ready()`
- `claim_next_apply_job(*, max_retries, lease_seconds=1800)`
  - Eligible source rows: `review_runs.status='SUCCESS'` and verdict in `PASS|TAILORED|BASE`
  - Suppresses rows with successful apply run or active non-stale `PENDING` claim
- `record_apply_success(...)`
- `record_apply_failure(...)`
- `mark_stale_apply_runs_failed(*, lease_seconds=1800) -> int`
- `get_apply_failure_count(review_run_id) -> int`

## Agent Interfaces

### Shared Model Bootstrap
- `src/agents/shared/model.py`: `build_openai_litellm_model(model_name)`

### Root Gate Agent
- Public exports from `src/agents/root_apply_decider/`:
  - `build_root_agent`, `run_decider_for_job`, `parse_gate_response`, `map_decision_to_status`
  - `get_decider_model`, `get_decider_model_name`, `get_decider_provider`
  - `ApplyDecision`, `GateRunResult`, `GateDebugInfo`

### Tailor Runtime
- Entry: `run_resume_tailor_pipeline(invocation: TailorInvocationContract) -> TailorRunResult`
- Tool CLI: `scripts/resume_tailor_tools.py`
  - `db-get-job-context`, `load-resume-yaml`, `save-resume-yaml`, `backup-resume-yaml`, `restore-resume-yaml`, `render-resume-tex`, `compile-resume`, `get-page-count`

### Review Runtime
- Entry: `run_resume_review_pipeline(invocation: ReviewInvocationContract) -> ReviewRunResult`
- Tool CLI: `scripts/resume_review_tools.py`
  - Tailor-equivalent commands plus `analyze-pdf-geometry`, `compare-pdf-to-base`, `analyze-latex-log`, `extract-pdf-text-signals`, `write-review-report`

### Browser Apply Runtime
- Entry: `apply_to_job(...) -> ApplyRunResult` (`src/agents/apply_worker/browser.py`)
- Helpers: ATS detection, confidence scoring, unresolved field scan, resume upload.
- Worker script: `scripts/process_apply_jobs.py`
  - `--loop` / `--once`
  - `--output-dir`, `--database-path`, `--cdp-url`, `--dry-run`, `--no-dry-run`

## Operational CLIs
- `python main.py` (discovery)
- `python -m scripts.run_pipeline_once [--limit N]`
- `python -m scripts.process_new_jobs [--loop|--once] [--limit N]`
- `python -m scripts.process_qualified_jobs [--loop|--once] ...`
- `python -m scripts.process_reviewed_resumes [--loop|--once] ...`
- `python -m scripts.process_apply_jobs [--loop|--once] ...`
- `python -m scripts.status`
- `python -m scripts.query_jobs ...`
- `python -m scripts.decide_job --job-hash <hash> [--save]`

## Deployment Interfaces
- Discovery units: `job-discovery.service`, `job-discovery.timer`
- Worker units: `job-agent-worker.service`, `job-tailor-worker.service`, `job-review-worker.service`, `job-apply-worker.service`
- Apply browser host: `job-apply-chrome.service` + `start-chrome-cdp.sh`
