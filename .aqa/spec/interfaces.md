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

## Deduplication
- **Deduplicator.filter_new_jobs(jobs)** returns only unseen jobs by hash and logs duplicates; **get_stats(jobs)** returns counts without filtering [src/utils/deduplicator.py:11-59](src/utils/deduplicator.py:11-59).

## Agent Interfaces (ADK)
- **RootApplyDecider agent**: built via `build_root_agent(model=...)`; package-local prompt utilities and schemas live under `src/agents/root_apply_decider/`.
- **Runner usage** in `scripts/process_new_jobs.py`: `_run_decider_for_job(agent, job)` executes ADK runner and parses raw text into `GateRunResult`.
- Candidate context input is config-driven (`config/candidate_profile.yaml`, optional `CANDIDATE_PROFILE_PATH` override).

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

## CLI / Operational Interfaces
- **Discovery cycle**: `python main.py` (reads env, sets up logger, runs async discovery) [main.py:105-167](main.py:105-167).
- **One-shot pipeline**: `python -m scripts.run_pipeline_once [--limit N]`.
- **Job query**: `scripts/query_jobs.py --company/--title/--location/--remote/--new --limit N` [scripts/query_jobs.py:21-105](scripts/query_jobs.py:21-105).
- **Greenhouse helper**: `scripts/find_greenhouse_id.py <company> [--verify]` [scripts/find_greenhouse_id.py:19-105](scripts/find_greenhouse_id.py:19-105).
- **Fetcher smoke tests**: `scripts/test_fetchers.py` (no args) [scripts/test_fetchers.py:18-78](scripts/test_fetchers.py:18-78).
- **Single-job decider**: `scripts/decide_job.py --job-hash <hash> [--save]` [scripts/decide_job.py:32-79](scripts/decide_job.py:32-79).
- **Agent batch processor**: `scripts/process_new_jobs.py [--loop|--once] [--limit N]` with retry/backoff env controls.
- **Resume tailor processor**: `scripts/run_resume_tailor.py` for one job at a time with optional per-run branch creation.

## Configuration Inputs
- `config/companies.yaml`: source targets + board search terms.
- `config/search_criteria.yaml`: targeting signals/default titles.
- `config/candidate_profile.yaml`: gate profile + default board-search terms.
- Environment variables from `.env.example` include:
  - discovery/runtime: `DATABASE_PATH`, `LOG_LEVEL`, `LOG_FILE`, `SQLITE_JOURNAL_MODE`
  - gate retry: `AGENT_BATCH_SIZE`, `AGENT_POLL_INTERVAL_SECONDS`, `AGENT_MAX_RETRIES`, `AGENT_RETRY_BACKOFF_SECONDS`, `AGENT_RETRY_BACKOFF_MULTIPLIER`
  - alerts: `NTFY_TOPIC`, `NTFY_SERVER`, `NTFY_TOKEN`, `NTFY_PRIORITY`
  - profile path override: `CANDIDATE_PROFILE_PATH`

## Tailor Worker Interfaces
- **Autonomous daemon**: `scripts/process_qualified_jobs.py [--once|--loop]`
  - Claims QUALIFIED jobs atomically via `claim_next_tailor_job` (BEGIN IMMEDIATE + claim token)
  - Invokes `run_resume_tailor_pipeline` per job
  - Records success/failure in `tailor_runs` table
  - Restores YAML baseline after each run
- **DatabaseManager tailor methods**:
  - `migrate_tailor_schema()` — idempotent schema bootstrap
  - `claim_next_tailor_job(max_retries, lease_seconds)` — atomic claim with lease
  - `record_tailor_success(run_id, artifact_tex_path, artifact_pdf_path, page_count)`
  - `record_tailor_failure(run_id, error, next_retry_at)`
  - `mark_stale_tailor_runs_failed(lease_seconds)` — crash recovery
  - `reset_tailor_failure_state(job_hash)` — operator requeue
  - `get_tailor_runs_for_job(job_hash)` — attempt history

## Deployment Interfaces
- `deploy/job-discovery.service` + `deploy/job-discovery.timer` (producer)
- `deploy/job-agent-worker.service` (gate consumer)
- `deploy/job-tailor-worker.service` (tailor consumer, persistent daemon)
- optional `deploy/job-agent-alert@.service` (systemd OnFailure alert hook)
- Deployment steps in `deploy/README.md` and `QUICKSTART.md`
