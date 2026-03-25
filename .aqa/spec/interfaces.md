# Interfaces & APIs

## Fetcher Interface
- **BaseFetcher** (83 lines): `fetch_jobs() -> List[JobPosting]` (async abstract), `get_source_name() -> str` (abstract); supports async context manager for setup/teardown; stores `config` dict and `source_name` string in constructor.
- **FetchError** (16 lines): Custom `RuntimeError` subclass in `errors.py` for transport/provider failures.
- **GreenhouseFetcher** (250 lines): `fetch_jobs()` pulls from Greenhouse public API (`boards-api.greenhouse.io`) and returns JobPosting list; handles 404/429 gracefully; constructed with `(company_name, greenhouse_id)`.
- **ApifyWorkdayFetcher** (195 lines): `fetch_jobs()` runs Apify actor via executor bridge and maps dataset items; constructed with `(company_name, workday_url, max_items=100)`; requires `APIFY_API_TOKEN`; raises `FetchError` on failure.
- **JobSpyFetcher** (309 lines): `fetch_jobs()` scrapes via jobspy with `hours_old=72`; constructed with `(site_name: Literal["indeed","glassdoor","linkedin"], search_term, location="Remote", results_wanted=25, country="USA")`; module-level `clean_value`/`clean_str` helpers; raises `FetchError` on scrape failure.

## Data Access (DatabaseManager) — 1784 lines
- Lifecycle: `connect()`, `close()`, async context manager.
- Schema: `create_tables()` executes schema.sql.
- Module-level constants: `DEFAULT_AGENT_CLAIM_LEASE_SECONDS` (900), `DEFAULT_TAILOR_CLAIM_LEASE_SECONDS` (7200), `DEFAULT_REVIEW_CLAIM_LEASE_SECONDS` (7200).
- Job CRUD:
  - `insert_job(job_data) -> bool` (False on duplicate hash)
  - `get_job_by_hash(job_hash) -> Optional[dict]`
  - `get_job_by_id(job_id) -> Optional[dict]`
  - `get_resume_tailor_job_context(*, job_hash=None, job_id=None) -> Optional[dict]` (reduced column set)
  - `get_existing_job_hashes(job_hashes) -> set[str]` (chunked IN-clause, chunk_size=900)
  - `update_job_status(job_hash, status)`
  - `get_jobs_by_status(status, limit=100)`
  - `get_job_count() -> int`
  - `get_jobs_today() -> int`
- Crawl logging: `start_crawl(source, company)` / `complete_crawl(crawl_id, jobs_found, jobs_new, error=None)`
- Daily stats: `update_daily_stats(date, jobs_discovered, jobs_new, jobs_duplicate, sources_crawled, sources_failed)` (INSERT ... ON CONFLICT additive)
- Agent workflow:
  - `get_jobs_pending_agent_processing(limit=100)` — claim-based with BEGIN IMMEDIATE + claim tokens, respects retry backoff and lease (env `AGENT_CLAIM_LEASE_SECONDS`, default 900s)
  - `migrate_agent_schema()` / `_ensure_agent_schema_ready()`
  - `record_agent_decision(*, job_hash, agent_result, status)` — clears failure/retry/claim fields
  - `record_agent_retry(*, job_hash, error, retry_count, next_retry_at)` — clears claim fields
  - `mark_job_agent_terminal_failed(job_hash, error, retry_count=None)` — clears retry/claim fields
  - `mark_job_agent_failed(job_hash, error)` (compat alias)
  - `reset_agent_failure_state(job_hash)` — resets to NEW, clears all agent state
  - `update_job_agent_result(job_hash, agent_result)` — stores result without changing status
- Tailor workflow:
  - `migrate_tailor_schema()` / `_ensure_tailor_schema_ready()`
  - `claim_next_tailor_job(*, max_retries, lease_seconds=7200)` — BEGIN IMMEDIATE, finds QUALIFIED with no SUCCESS run
  - `record_tailor_success(*, run_id, artifact_yaml_path, artifact_tex_path, artifact_pdf_path, page_count)`
  - `record_tailor_failure(*, run_id, error, next_retry_at)`
  - `mark_stale_tailor_runs_failed(*, lease_seconds=7200) -> int`
  - `reset_tailor_failure_state(*, job_hash)` — DELETEs FAILED runs
  - `get_tailor_runs_for_job(job_hash) -> list[dict]`
  - `get_tailor_failure_count(job_hash) -> int`
- Review workflow:
  - `migrate_review_schema()` / `_ensure_review_schema_ready()`
  - `claim_next_review_job(*, max_retries, lease_seconds=7200)` — BEGIN IMMEDIATE, joins tailor_runs + job_postings
  - `record_review_success(*, run_id, verdict, selected_yaml_path, selected_tex_path, selected_pdf_path, review_report_json, agent_stdout, agent_stderr)`
  - `record_review_failure(*, run_id, error, next_retry_at, agent_stdout, agent_stderr, fallback_base_yaml_path, fallback_base_tex_path, fallback_base_pdf_path)`
  - `mark_stale_review_runs_failed(*, lease_seconds=7200) -> int`
  - `get_review_failure_count(tailor_run_id) -> int`
  - `get_review_runs_for_tailor_run(tailor_run_id) -> list[dict]`

## Deduplication
- **Deduplicator** (111 lines): `filter_new_jobs(jobs)` performs in-batch dedup then DB lookup via `get_existing_job_hashes`; `get_stats(jobs)` returns `{total, new, duplicate}` counts.

## Path Resolution
- **paths.py** (55 lines): `resolve_repo_root()` walks up parents for `pyproject.toml`/`.git`/`AGENTS.md`; `resolve_database_path()` loads `.env` and resolves `DATABASE_PATH` (default `data/jobs.db`).

## Agent Interfaces (ADK + LiteLLM)
- **Shared model helper**: `build_openai_litellm_model(model_name)` in `src/agents/shared/model.py`; validates `OPENAI_API_KEY`, imports `LiteLlm` from google.adk.
- **RootApplyDecider agent**: built via `build_root_agent(model=...)` using `openai/gpt-5.1-codex-mini`.
- **Runtime** in `src/agents/root_apply_decider/runtime.py`: `run_decider_for_job(*, agent, job) -> GateRunResult` executes ADK runner with fresh `InMemorySessionService` per job, captures final text, parses via `parse_gate_response`.
- **Exports** from `src/agents/root_apply_decider/`: `build_root_agent`, `parse_gate_response`, `build_gate_payload`, `run_decider_for_job`, `extract_event_text`, `map_decision_to_status`, `get_decider_model`/`get_decider_model_name`/`get_decider_provider`, `ApplyDecision`, `GateDebugInfo`, `GateRunResult`.
- Candidate context input is config-driven (`config/candidate_profile.yaml`, optional `CANDIDATE_PROFILE_PATH` override).
- Gate decision parsing requires recoverable JSON with `decision` field; no text-only fallback.

## Resume Tailor Interfaces (Pi-Mono)
- **Invocation contract**: `TailorInvocationContract` with `job_ref`, database/YAML/artifact paths, page limit, retry counts, layout profile, pi model/command/timeout/env config, optional branch settings.
- **Run result contract**: `TailorRunResult` with success flag, failure reason, final page count, per-attempt phase history, active git branch.
- **Tool contracts** (`scripts/resume_tailor_tools.py`):
  - `db-get-job-context --job-hash|--job-id [--database-path]`
  - `load-resume-yaml --path`
  - `save-resume-yaml --path (--content-json|--content-file)`
  - `backup-resume-yaml --path --snapshot-path`
  - `restore-resume-yaml --path --snapshot-path`
  - `render-resume-tex --yaml-path --tex-out`
  - `compile-resume --tex-path --pdf-out`
  - `get-page-count --pdf-path [--log-path]`
- **Tailor runner**: `scripts/run_resume_tailor.py --job-hash|--job-id ...` executes one-page loop via `run_resume_tailor_pipeline`.
- **Migration utility**: `scripts/migrate_resume_tex_to_yaml.py --tex-path --yaml-out [--seed-inactive-slots|--no-seed-inactive-slots]`.

## Resume Review Interfaces (Pi-Mono)
- **Invocation contract**: `ReviewInvocationContract` with job/tailor refs, tailored and base artifact paths (yaml/tex/pdf/log), report path, max self-edit iterations, and pi subprocess config.
- **Run result contract**: `ReviewRunResult` with `success`, `hard_failure`, agent verdict, validated report, selected refs, and stdout/stderr diagnostics.
- **Tool contracts** (`scripts/resume_review_tools.py`):
  - Tailor-equivalent commands: `db-get-job-context`, `load-resume-yaml`, `save-resume-yaml`, `backup-resume-yaml`, `restore-resume-yaml`, `render-resume-tex`, `compile-resume`, `get-page-count`
  - Review-specific commands: `analyze-pdf-geometry`, `compare-pdf-to-base`, `analyze-latex-log`, `extract-pdf-text-signals`, `write-review-report`
- **Review runtime**: `run_resume_review_pipeline(invocation)` invokes pi once and treats missing report/invalid schema/missing selected refs/timeouts as hard runtime failures.

## CLI / Operational Interfaces
- **Discovery cycle**: `python main.py` (reads env, sets up logger, runs async discovery with title filtering).
- **One-shot pipeline**: `python -m scripts.run_pipeline_once [--limit N]`.
- **Job query**: `scripts/query_jobs.py --company/--title/--location/--remote/--new --limit N`.
- **Greenhouse helper**: `scripts/find_greenhouse_id.py <company> [--verify]`.
- **Fetcher smoke tests**: `scripts/test_fetchers.py` (no args).
- **Single-job decider**: `scripts/decide_job.py --job-hash <hash> [--save]`.
- **Agent batch processor**: `scripts/process_new_jobs.py [--loop|--once] [--limit N]` with retry/backoff env controls and claim-based processing.
- **Resume tailor processor**: `scripts/run_resume_tailor.py` for one job at a time with optional per-run branch creation.
- **Resume review processor**: `scripts/process_reviewed_resumes.py [--loop|--once]` for autonomous post-tailor review queue processing.
- **Database status**: `scripts/status.py` prints terminal summary of job counts, crawl history, tailor/review run statistics.

## Configuration Inputs
- `config/companies.yaml`: source targets + board search terms.
- `config/search_criteria.yaml`: targeting signals/default titles, include title patterns.
- `config/candidate_profile.yaml`: gate profile + default board-search terms + title include patterns.
- `config/resume_content.yaml`: YAML-canonical resume source.
- `config/resume_base.tex` / `config/resume_base.pdf`: pre-compiled base resume reference artifacts.
- Environment variables from `.env.example` include:
  - discovery/runtime: `DATABASE_PATH`, `LOG_LEVEL`, `LOG_FILE`, `SQLITE_JOURNAL_MODE`
  - gate retry: `AGENT_BATCH_SIZE`, `AGENT_POLL_INTERVAL_SECONDS`, `AGENT_MAX_RETRIES`, `AGENT_RETRY_BACKOFF_SECONDS`, `AGENT_RETRY_BACKOFF_MULTIPLIER`, `AGENT_CLAIM_LEASE_SECONDS`
  - alerts: `NTFY_TOPIC`, `NTFY_SERVER`, `NTFY_TOKEN`, `NTFY_PRIORITY`
  - profile path override: `CANDIDATE_PROFILE_PATH`
  - tailor worker: `TAILOR_POLL_INTERVAL_SECONDS`, `TAILOR_MAX_RETRIES`, `TAILOR_RETRY_BACKOFF_SECONDS`, `TAILOR_RETRY_BACKOFF_MULTIPLIER`, `TAILOR_CLAIM_LEASE_SECONDS`, `TAILOR_OUTPUT_DIR`
  - review worker: `REVIEW_POLL_INTERVAL_SECONDS`, `REVIEW_MAX_RETRIES`, `REVIEW_RETRY_BACKOFF_SECONDS`, `REVIEW_RETRY_BACKOFF_MULTIPLIER`, `REVIEW_CLAIM_LEASE_SECONDS`, `REVIEW_OUTPUT_DIR`, `REVIEW_BASE_RESUME_YAML_PATH`, `REVIEW_BASE_RESUME_TEX_PATH`, `REVIEW_BASE_RESUME_PDF_PATH`, `RESUME_REVIEW_MODEL`
  - pi command: `PI_CODING_AGENT_COMMAND`, `PI_CODING_AGENT_COMMAND_ARGV`

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
