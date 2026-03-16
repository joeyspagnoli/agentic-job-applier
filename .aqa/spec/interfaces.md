# Interfaces & APIs

## Fetcher Interface
- **BaseFetcher**: `fetch_jobs() -> List[JobPosting]` (async), `get_source_name() -> str`; supports async context manager for setup/teardown [src/fetchers/base_fetcher.py:1-32](src/fetchers/base_fetcher.py:1-32).
- **GreenhouseFetcher**: `fetch_jobs()` pulls from Greenhouse public API and returns JobPosting list; constructed with `(company_name, greenhouse_id)` [src/fetchers/greenhouse_fetcher.py:24-87](src/fetchers/greenhouse_fetcher.py:24-87).
- **ApifyWorkdayFetcher**: `fetch_jobs()` runs Apify actor and maps dataset items; constructed with `(company_name, workday_url, max_items=100)` and requires `APIFY_API_TOKEN` [src/fetchers/apify_fetcher.py:21-86](src/fetchers/apify_fetcher.py:21-86).
- **JobSpyFetcher**: `fetch_jobs()` scrapes via jobspy; constructed with `(site_name, search_term, location="Remote", results_wanted=25, country="USA")` [src/fetchers/jobspy_fetcher.py:28-96](src/fetchers/jobspy_fetcher.py:28-96).

## Data Access (DatabaseManager)
- Lifecycle: `connect()`, `close()`, async context manager [src/database/db_manager.py:18-63](src/database/db_manager.py:18-63).
- Schema: `create_tables()` executes schema.sql [src/database/db_manager.py:65-78](src/database/db_manager.py:65-78).
- CRUD/helpers:
  - `insert_job(job_data) -> bool` (False on duplicate hash) [src/database/db_manager.py:80-112](src/database/db_manager.py:80-112).
  - `get_job_by_hash(job_hash)` [src/database/db_manager.py:114-129](src/database/db_manager.py:114-129).
  - `get_job_by_id(job_id)` and `get_resume_tailor_job_context(job_hash|job_id)` for tailor DB lookups.
  - `update_job_status(job_hash, status)` [src/database/db_manager.py:131-147](src/database/db_manager.py:131-147).
  - `get_jobs_by_status(status, limit=100)` and `get_jobs_pending_agent_processing(limit=100)` (includes retry-ready NEW rows) [src/database/db_manager.py](../../src/database/db_manager.py).
  - Crawl logging: `start_crawl(source, company)` / `complete_crawl(crawl_id, jobs_found, jobs_new, error=None)` [src/database/db_manager.py:185-220](src/database/db_manager.py:185-220).
  - Daily stats: `update_daily_stats(date, jobs_discovered, jobs_new, jobs_duplicate, sources_crawled, sources_failed)` [src/database/db_manager.py:222-249](src/database/db_manager.py:222-249).
  - Agent workflow:
    - `migrate_agent_schema()`
    - `record_agent_decision(job_hash, agent_result, status)`
    - `record_agent_retry(job_hash, error, retry_count, next_retry_at)`
    - `mark_job_agent_terminal_failed(job_hash, error, retry_count=None)`
    - `mark_job_agent_failed(job_hash, error)` (compat alias)
    - `reset_agent_failure_state(job_hash)`
    - `update_job_agent_result(job_hash, agent_result)`
  - Metrics: `get_job_count()`, `get_jobs_today()` [src/database/db_manager.py:323-349](src/database/db_manager.py:323-349).
  - Tailor workflow:
    - `migrate_tailor_schema()`
    - `claim_next_tailor_job(max_retries, lease_seconds)`
    - `record_tailor_success(run_id, artifact_yaml_path, artifact_tex_path, artifact_pdf_path, page_count)`
    - `record_tailor_failure(run_id, error, next_retry_at)`
    - `mark_stale_tailor_runs_failed(lease_seconds)`
    - `reset_tailor_failure_state(job_hash)`
    - `get_tailor_runs_for_job(job_hash)`
  - Review workflow:
    - `migrate_review_schema()`
    - `claim_next_review_job(max_retries, lease_seconds)`
    - `record_review_success(run_id, verdict, selected_yaml_path, selected_tex_path, selected_pdf_path, review_report_json, agent_stdout, agent_stderr)`
    - `record_review_failure(run_id, error, next_retry_at, agent_stdout, agent_stderr, fallback_base_yaml_path, fallback_base_tex_path, fallback_base_pdf_path)`
    - `mark_stale_review_runs_failed(lease_seconds)`
    - `get_review_failure_count(tailor_run_id)`
    - `get_review_runs_for_tailor_run(tailor_run_id)`

## Deduplication
- **Deduplicator.filter_new_jobs(jobs)** returns only unseen jobs by hash and logs duplicates; **get_stats(jobs)** returns counts without filtering [src/utils/deduplicator.py:11-59](src/utils/deduplicator.py:11-59).

## Agent Interfaces (ADK)
- **RootApplyDecider agent**: built via `build_root_agent(model=...)`; package-local prompt utilities and schemas live under `src/agents/root_apply_decider/`.
- **Runner usage** in `scripts/process_new_jobs.py`: `_run_decider_for_job(agent, job)` executes ADK runner and parses raw text into `GateRunResult`.
- Candidate context input is config-driven (`config/candidate_profile.yaml`, optional `CANDIDATE_PROFILE_PATH` override).
- Gate decision parsing no longer accepts text-only fallback; `parse_gate_response` requires recoverable JSON with `decision`.

## Resume Tailor Interfaces (Pi-Mono)
- **Invocation contract**: `TailorInvocationContract` with `job_ref`, YAML/artifact paths, page limit, retry counts, layout profile, optional branch settings.
- **Run result contract**: `TailorRunResult` with success flag, failure reason, final page count, and per-attempt phase history.
- **Tool contracts** (`scripts/resume_tailor_tools.py`):
  - `db-get-job-context --job-hash|--job-id [--database-path]`
  - `load-resume-yaml --path`
  - `save-resume-yaml --path (--content-json|--content-file)`
  - `render-resume-tex --yaml-path --tex-out`
  - `compile-resume --tex-path --pdf-out`
  - `get-page-count --pdf-path [--log-path]`
- **Tailor runner**: `scripts/run_resume_tailor.py --job-hash|--job-id ...` executes one-page loop via `run_resume_tailor_pipeline`.
- **Migration utility**: `scripts/migrate_resume_tex_to_yaml.py --tex-path --yaml-out [--seed-inactive-slots|--no-seed-inactive-slots]`.

## Resume Review Interfaces (Pi-Mono)
- **Invocation contract**: `ReviewInvocationContract` with job/tailor refs, tailored and base artifact paths, report path, max self-edit iterations, and pi subprocess settings.
- **Run result contract**: `ReviewRunResult` with `success`, `hard_failure`, agent verdict, validated report, selected refs, and stdout/stderr diagnostics.
- **Tool contracts** (`scripts/resume_review_tools.py`):
  - Tailor-equivalent commands: `db-get-job-context`, `load-resume-yaml`, `save-resume-yaml`, `backup-resume-yaml`, `restore-resume-yaml`, `render-resume-tex`, `compile-resume`, `get-page-count`
  - Review-specific commands: `analyze-pdf-geometry`, `compare-pdf-to-base`, `analyze-latex-log`, `extract-pdf-text-signals`, `write-review-report`
- **Review runtime**: `run_resume_review_pipeline(invocation)` invokes pi once and treats missing report/invalid schema/missing selected refs/timeouts as hard runtime failures.

## CLI / Operational Interfaces
- **Discovery cycle**: `python main.py` (reads env, sets up logger, runs async discovery) [main.py:105-167](main.py:105-167).
- **One-shot pipeline**: `python -m scripts.run_pipeline_once [--limit N]`.
- **Job query**: `scripts/query_jobs.py --company/--title/--location/--remote/--new --limit N` [scripts/query_jobs.py:21-105](scripts/query_jobs.py:21-105).
- **Greenhouse helper**: `scripts/find_greenhouse_id.py <company> [--verify]` [scripts/find_greenhouse_id.py:19-105](scripts/find_greenhouse_id.py:19-105).
- **Fetcher smoke tests**: `scripts/test_fetchers.py` (no args) [scripts/test_fetchers.py:18-78](scripts/test_fetchers.py:18-78).
- **Single-job decider**: `scripts/decide_job.py --job-hash <hash> [--save]` [scripts/decide_job.py:32-79](scripts/decide_job.py:32-79).
- **Agent batch processor**: `scripts/process_new_jobs.py [--loop|--once] [--limit N]` with retry/backoff env controls.
- **Resume tailor processor**: `scripts/run_resume_tailor.py` for one job at a time with optional per-run branch creation.
- **Resume review processor**: `scripts/process_reviewed_resumes.py [--loop|--once]` for autonomous post-tailor review queue processing.

## Configuration Inputs
- `config/companies.yaml`: source targets + board search terms.
- `config/search_criteria.yaml`: targeting signals/default titles.
- `config/candidate_profile.yaml`: gate profile + default board-search terms.
- Environment variables from `.env.example` include:
  - discovery/runtime: `DATABASE_PATH`, `LOG_LEVEL`, `LOG_FILE`, `SQLITE_JOURNAL_MODE`
  - gate retry: `AGENT_BATCH_SIZE`, `AGENT_POLL_INTERVAL_SECONDS`, `AGENT_MAX_RETRIES`, `AGENT_RETRY_BACKOFF_SECONDS`, `AGENT_RETRY_BACKOFF_MULTIPLIER`
  - alerts: `NTFY_TOPIC`, `NTFY_SERVER`, `NTFY_TOKEN`, `NTFY_PRIORITY`
- profile path override: `CANDIDATE_PROFILE_PATH`
  - review worker: `REVIEW_POLL_INTERVAL_SECONDS`, `REVIEW_MAX_RETRIES`, `REVIEW_RETRY_BACKOFF_SECONDS`, `REVIEW_RETRY_BACKOFF_MULTIPLIER`, `REVIEW_CLAIM_LEASE_SECONDS`, `REVIEW_OUTPUT_DIR`, `REVIEW_BASE_RESUME_YAML_PATH`, `REVIEW_BASE_RESUME_TEX_PATH`, `REVIEW_BASE_RESUME_PDF_PATH`, `RESUME_REVIEW_MODEL`

## Tailor Worker Interfaces
- **Autonomous daemon**: `scripts/process_qualified_jobs.py [--once|--loop]`
  - Claims QUALIFIED jobs atomically via `claim_next_tailor_job` (BEGIN IMMEDIATE + claim token)
  - Invokes `run_resume_tailor_pipeline` per job
  - Records success/failure in `tailor_runs` table
  - Uses per-run YAML work-copy artifact instead of mutating canonical baseline

## Review Worker Interfaces
- **Autonomous daemon**: `scripts/process_reviewed_resumes.py [--once|--loop]`
  - Claims successful tailor runs atomically via `claim_next_review_job`
  - Invokes `run_resume_review_pipeline` per run
  - Records success/failure in `review_runs`
  - Persists base fallback refs on hard runtime failure

## Deployment Interfaces
- `deploy/job-discovery.service` + `deploy/job-discovery.timer` (producer)
- `deploy/job-agent-worker.service` (gate consumer)
- `deploy/job-tailor-worker.service` (tailor consumer, persistent daemon)
- `deploy/job-review-worker.service` (review consumer, persistent daemon)
- optional `deploy/job-agent-alert@.service` (systemd OnFailure alert hook)
- Deployment steps in `deploy/README.md` and `QUICKSTART.md`
