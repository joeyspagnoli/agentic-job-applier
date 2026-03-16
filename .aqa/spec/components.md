# Components

## Orchestrator
- **main.py**: Async discovery producer that loads configs (including optional profile/search defaults), fetches sources, deduplicates, inserts NEW jobs, and records stats.

## Data & Persistence
- **DatabaseManager**: Async SQLite wrapper with configurable journal mode, queue reads, decision persistence, retry state transitions, terminal failure state, requeue helper, and tailor/review run lifecycle methods.
- **Schema**: job queue + crawl/stats tables plus retry fields (`agent_retry_count`, `agent_next_retry_at`), `tailor_runs`, and `review_runs` tables.
- **Tailor DB methods**: `migrate_tailor_schema`, `_ensure_tailor_schema_ready`, `claim_next_tailor_job`, `record_tailor_success`, `record_tailor_failure`, `mark_stale_tailor_runs_failed`, `reset_tailor_failure_state`, `get_tailor_runs_for_job`.
- **Review DB methods**: `migrate_review_schema`, `_ensure_review_schema_ready`, `claim_next_review_job`, `record_review_success`, `record_review_failure`, `mark_stale_review_runs_failed`, `get_review_failure_count`, `get_review_runs_for_tailor_run`.

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
- **RootApplyDecider agent**: prompt/parser/model helpers under `src/agents/root_apply_decider/`; candidate context is now profile-driven from config with fallback and strict structured JSON parsing for final decisions.
- **Job processor**: `scripts/process_new_jobs.py` runs consumer loop with retry/backoff, terminal failure handling, and ntfy alerts.
- **Notification utility**: `src/utils/notifications.py` publishes optional ntfy alerts.

## Resume Tailor Layer (Pi-Mono)
- **Canonical schema + locks**: `src/agents/resume_tailor_pi/schemas.py` defines YAML model, locked headers/order, non-editable sections, and invocation/result contracts.
- **YAML IO + rendering**: `yaml_io.py` validates read/write and `renderer.py` deterministically emits LaTeX from canonical YAML.
- **Compile/page checks**: `compiler.py` compiles via `latexmk` and extracts page count via `pdfinfo` with LaTeX-log fallback.
- **Runtime loop**: `runtime.py` executes content passes, two readjust retries, bounded layout compression, and explicit failure semantics.
- **Tool surface**: `scripts/resume_tailor_tools.py` exposes DB, YAML, render, compile, and page-count operations as JSON-returning CLI commands.
- **Operational entrypoints**: `scripts/migrate_resume_tex_to_yaml.py` bootstraps canonical YAML from LaTeX; `scripts/run_resume_tailor.py` runs one tailoring job end-to-end.

## Resume Review Layer (Pi-Mono)
- **Review contracts**: `src/agents/resume_review_pi/schemas.py` defines invocation, strict report schema, verdict enum, and geometry/log/text payload models.
- **Review prompt/runtime**: `prompts.py` enforces self-loop workflow and explicit `write-review-report` completion; `runtime.py` enforces hard-error-only boundaries.
- **Review analysis tools**: `src/agents/resume_review_pi/tools.py` provides deterministic PDF geometry, compare-to-base, log parsing, text signals, and report writing helpers.
- **Review CLI surface**: `scripts/resume_review_tools.py` exposes tailor-equivalent tools plus review-specific analysis/report commands as deterministic JSON.

## Operational Scripts
- **scripts/query_jobs.py**: Query/display jobs with filters (company/title/location/remote/new, limit) [scripts/query_jobs.py:1-109](scripts/query_jobs.py:1-109).
- **scripts/find_greenhouse_id.py**: Try/verify Greenhouse IDs via API helper patterns [scripts/find_greenhouse_id.py:1-108](scripts/find_greenhouse_id.py:1-108).
- **scripts/test_fetchers.py**: Async smoke tests for Greenhouse and JobSpy fetchers [scripts/test_fetchers.py:1-78](scripts/test_fetchers.py:1-78).
- **scripts/decide_job.py**: Run the root decider on a single job hash, optionally persisting status [scripts/decide_job.py:1-80](scripts/decide_job.py:1-80).
- **scripts/run_pipeline_once.py**: One-shot `discovery -> gate-batch` orchestration command.

## Tailor Worker (Autonomous)
- **scripts/process_qualified_jobs.py**: Autonomous daemon that claims QUALIFIED jobs via atomic transactions, invokes `run_resume_tailor_pipeline`, records results in `tailor_runs`, and writes a per-run YAML work copy artifact.
- Supports `--once` (one-shot) and `--loop` (persistent daemon) modes.
- Preflight checks: pi-mono command, latexmk, database path.
- Artifacts: `data/tailored_resumes/<job_hash>/resume_tailored.{tex,pdf}` and `resume_content_work.yaml`.

## Review Worker (Autonomous)
- **scripts/process_reviewed_resumes.py**: Autonomous daemon that claims successful tailor runs, invokes `run_resume_review_pipeline`, records verdict/failure diagnostics in `review_runs`, and persists base fallback refs on hard runtime failures.
- Supports `--once` and `--loop` modes.
- Preflight checks: pi-mono command, latexmk, `pdfinfo`, `pdftotext`, `pdftoppm`, database path.
- Report artifact: `data/tailored_resumes/<job_hash>/review_report.json`.

## Configuration & Deployment
- **Config**: `companies.yaml`, `search_criteria.yaml`, and `candidate_profile.yaml` drive discovery targeting + gate context.
- **Deployment**: timer+service producer (`job-discovery.*`) plus continuous gate consumer (`job-agent-worker.service`), continuous tailor consumer (`job-tailor-worker.service`), continuous review consumer (`job-review-worker.service`), and optional `job-agent-alert@.service`.
