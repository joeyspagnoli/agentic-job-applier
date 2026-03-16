# Components

## Orchestrator
- **main.py**: Async discovery producer that loads configs (including optional profile/search defaults), fetches sources, deduplicates, inserts NEW jobs, and records stats.

## Data & Persistence
- **DatabaseManager**: Async SQLite wrapper with configurable journal mode, queue reads, decision persistence, retry state transitions, terminal failure state, requeue helper, and tailor-run lifecycle methods.
- **Schema**: job queue + crawl/stats tables plus retry fields (`agent_retry_count`, `agent_next_retry_at`) and `tailor_runs` table (PENDING/SUCCESS/FAILED with claim tokens, artifact paths, retry scheduling).
- **Tailor DB methods** (7 new): `migrate_tailor_schema`, `_ensure_tailor_schema_ready`, `claim_next_tailor_job`, `record_tailor_success`, `record_tailor_failure`, `mark_stale_tailor_runs_failed`, `reset_tailor_failure_state`, `get_tailor_runs_for_job`.

## Models
- **JobPosting (Pydantic)**: Standardized job record with hash property, remote detection, job_type normalization, and DB dict conversion [src/models/job_posting.py:10-103](src/models/job_posting.py:10-103).

## Fetchers
- **BaseFetcher**: Defines async interface and source naming contract [src/fetchers/base_fetcher.py:1-32](src/fetchers/base_fetcher.py:1-32).
- **GreenhouseFetcher**: Calls Greenhouse public API, strips HTML, parses salary hints, maps to JobPosting [src/fetchers/greenhouse_fetcher.py:1-120](src/fetchers/greenhouse_fetcher.py:1-120).
- **ApifyWorkdayFetcher**: Runs Apify Workday actor (requires APIFY_API_TOKEN), fetches dataset items, maps to JobPosting [src/fetchers/apify_fetcher.py:1-110](src/fetchers/apify_fetcher.py:1-110).
- **JobSpyFetcher**: Uses jobspy scrape, cleans NaNs/dates, normalizes salaries to annual cents, builds JobPosting models [src/fetchers/jobspy_fetcher.py:1-200](src/fetchers/jobspy_fetcher.py:1-200).

## Deduplication & Logging
- **Deduplicator**: Filters jobs already present by hash; reports duplicate/new counts [src/utils/deduplicator.py:11-59](src/utils/deduplicator.py:11-59).
- **Logger setup**: Console+file loguru configuration; helpers for crawl/cycle summaries [src/utils/logger.py:9-91](src/utils/logger.py:9-91).

## Agent Layer (Apply/Skip)
- **RootApplyDecider agent**: prompt/parser/model helpers under `src/agents/root_apply_decider/`; candidate context is now profile-driven from config with fallback.
- **Job processor**: `scripts/process_new_jobs.py` runs consumer loop with retry/backoff, terminal failure handling, and ntfy alerts.
- **Notification utility**: `src/utils/notifications.py` publishes optional ntfy alerts.

## Resume Tailor Layer (Pi-Mono)
- **Canonical schema + locks**: `src/agents/resume_tailor_pi/schemas.py` defines YAML model, locked headers/order, non-editable sections, and invocation/result contracts.
- **YAML IO + rendering**: `yaml_io.py` validates read/write and `renderer.py` deterministically emits LaTeX from canonical YAML.
- **Compile/page checks**: `compiler.py` compiles via `latexmk` and extracts page count via `pdfinfo` with LaTeX-log fallback.
- **Runtime loop**: `runtime.py` executes content passes, two readjust retries, bounded layout compression, and explicit failure semantics.
- **Tool surface**: `scripts/resume_tailor_tools.py` exposes DB, YAML, render, compile, and page-count operations as JSON-returning CLI commands.
- **Operational entrypoints**: `scripts/migrate_resume_tex_to_yaml.py` bootstraps canonical YAML from LaTeX; `scripts/run_resume_tailor.py` runs one tailoring job end-to-end.

## Operational Scripts
- **scripts/query_jobs.py**: Query/display jobs with filters (company/title/location/remote/new, limit) [scripts/query_jobs.py:1-109](scripts/query_jobs.py:1-109).
- **scripts/find_greenhouse_id.py**: Try/verify Greenhouse IDs via API helper patterns [scripts/find_greenhouse_id.py:1-108](scripts/find_greenhouse_id.py:1-108).
- **scripts/test_fetchers.py**: Async smoke tests for Greenhouse and JobSpy fetchers [scripts/test_fetchers.py:1-78](scripts/test_fetchers.py:1-78).
- **scripts/decide_job.py**: Run the root decider on a single job hash, optionally persisting status [scripts/decide_job.py:1-80](scripts/decide_job.py:1-80).
- **scripts/run_pipeline_once.py**: One-shot `discovery -> gate-batch` orchestration command.

## Tailor Worker (Autonomous)
- **scripts/process_qualified_jobs.py**: Autonomous daemon that claims QUALIFIED jobs via atomic transactions, invokes `run_resume_tailor_pipeline`, records results in `tailor_runs`, and restores YAML baseline after each run.
- Supports `--once` (one-shot) and `--loop` (persistent daemon) modes.
- Preflight checks: pi-mono command, latexmk, database path.
- Artifacts: `data/tailored_resumes/<job_hash>/resume_tailored.{tex,pdf}`.

## Configuration & Deployment
- **Config**: `companies.yaml`, `search_criteria.yaml`, and `candidate_profile.yaml` drive discovery targeting + gate context.
- **Deployment**: timer+service producer (`job-discovery.*`) plus continuous gate consumer (`job-agent-worker.service`), continuous tailor consumer (`job-tailor-worker.service`), and optional `job-agent-alert@.service`.
