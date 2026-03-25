# Components

## Orchestrator
- **main.py** (693 lines): Async discovery producer that loads configs (including optional profile/search defaults), resolves board search terms, fetches sources, applies title include-pattern filtering, deduplicates via `Deduplicator`, inserts NEW jobs, and records stats.

## Data & Persistence
- **DatabaseManager** (1784 lines): Async SQLite wrapper with configurable journal mode (env `SQLITE_JOURNAL_MODE`, default WAL), claim-based queue reads, decision persistence, retry state transitions, terminal failure state, requeue helper, tailor/review run lifecycle methods, and batch dedup helpers.
- **Schema** (148 lines): job queue + crawl/stats tables plus retry fields (`agent_retry_count`, `agent_next_retry_at`), claim fields (`agent_claim_token`, `agent_claimed_at`), `tailor_runs`, and `review_runs` tables.
- **Core job CRUD**: `insert_job`, `get_job_by_hash`, `get_job_by_id`, `get_existing_job_hashes`, `update_job_status`, `get_jobs_by_status`, `get_job_count`, `get_jobs_today`.
- **Agent queue methods**: `get_jobs_pending_agent_processing` (claim-based with BEGIN IMMEDIATE), `migrate_agent_schema`, `_ensure_agent_schema_ready`, `record_agent_decision`, `record_agent_retry`, `mark_job_agent_terminal_failed`, `mark_job_agent_failed` (compat alias), `reset_agent_failure_state`, `update_job_agent_result`.
- **Tailor DB methods**: `migrate_tailor_schema`, `_ensure_tailor_schema_ready`, `claim_next_tailor_job`, `record_tailor_success`, `record_tailor_failure`, `mark_stale_tailor_runs_failed`, `reset_tailor_failure_state`, `get_tailor_runs_for_job`, `get_tailor_failure_count`.
- **Review DB methods**: `migrate_review_schema`, `_ensure_review_schema_ready`, `claim_next_review_job`, `record_review_success`, `record_review_failure`, `mark_stale_review_runs_failed`, `get_review_failure_count`, `get_review_runs_for_tailor_run`.
- **Tailor context**: `get_resume_tailor_job_context` (reduced column set by hash or id).

## Models
- **JobPosting (Pydantic)** (223 lines): Standardized job record with canonicalized hash property (8 identity parts including URL canonicalization and content sub-hashes), remote detection, job_type normalization, `to_db_dict()` serialization, and extra fields ignored via `ConfigDict(extra="ignore")`.

## Fetchers
- **BaseFetcher** (83 lines): Defines async interface (`fetch_jobs`, `get_source_name`), async context manager, and stores `config`/`source_name` in constructor.
- **GreenhouseFetcher** (250 lines): Calls Greenhouse public API, strips HTML via `_clean_html`, parses salary hints via `_extract_salary`, handles 404/429 gracefully, manages `httpx.AsyncClient`, maps to JobPosting.
- **ApifyWorkdayFetcher** (195 lines): Runs Apify Workday actor (requires `APIFY_API_TOKEN`), bridges sync actor call via executor, fetches dataset items, maps to JobPosting. Does not populate salary fields.
- **JobSpyFetcher** (309 lines): Uses jobspy `scrape_jobs` with `hours_old=72`, cleans NaNs/dates via module-level `clean_value`/`clean_str` helpers, normalizes salaries to annual cents with interval multipliers, builds JobPosting models. Raises `FetchError` on scrape failures.
- **FetchError** (16 lines): Custom `RuntimeError` subclass in `errors.py` differentiating transport/provider failures from valid empty-result crawls.

## Deduplication & Logging
- **Deduplicator** (111 lines): Filters jobs by hash with both in-batch dedup (`seen_in_batch` set) and database lookup (`get_existing_job_hashes`); `filter_new_jobs` returns only unseen jobs; `get_stats` returns `{total, new, duplicate}` counts.
- **Logger setup** (131 lines): Console+file loguru configuration with rotation/retention; helpers `log_crawl_summary` and `log_cycle_summary`.

## Path Resolution
- **paths.py** (55 lines): `resolve_repo_root()` walks up to find `pyproject.toml`/`.git`/`AGENTS.md`; `resolve_database_path()` loads `.env` and resolves `DATABASE_PATH` (default `data/jobs.db`).

## Notifications
- **notifications.py** (115 lines): `is_ntfy_enabled()` checks `NTFY_TOPIC` env var; `send_ntfy_notification()` async-posts to ntfy.sh with configurable server/token/priority/tags via `httpx.AsyncClient`.

## Agent Layer - Shared
- **shared/model.py**: `build_openai_litellm_model(model_name)` centralizes OpenAI credential validation (`OPENAI_API_KEY`) and LiteLLM import handling for all ADK agent packages.

## Agent Layer - Apply/Skip Gate
- **RootApplyDecider agent** (`src/agents/root_apply_decider/`): prompt/parser/model helpers; candidate context is profile-driven from config with fallback; strict structured JSON parsing for final decisions (no text-only fallback).
- **agent.py** (210 lines): `build_root_agent`, `parse_gate_response`, `get_decider_model`/`get_decider_model_name`/`get_decider_provider` for model `openai/gpt-5.1-codex-mini`.
- **runtime.py** (133 lines): `run_decider_for_job` executes ADK runner with fresh InMemorySessionService per job, `extract_event_text`, `map_decision_to_status`.
- **prompts.py** (339 lines): `build_gate_payload`, `load_candidate_context`, `_render_candidate_context_from_profile`; includes prompt-safety rules and salary formatting.
- **schemas.py** (50 lines): `ApplyDecision` enum, `GateDebugInfo`, `GateRunResult`.
- **Job processor**: `scripts/process_new_jobs.py` runs consumer loop calling `run_decider_for_job` with retry/backoff, terminal failure handling, claim-based atomic processing, and ntfy alerts.

## Resume Tailor Layer (Pi-Mono)
- **Canonical schema + locks**: `src/agents/resume_tailor_pi/schemas.py` (629 lines) defines YAML model (`ResumeContent`), locked headers/order, non-editable sections, `TailorInvocationContract`, `TailorRunResult`, `TailorAttemptRecord`, and lock validation/snapshot helpers.
- **YAML IO + rendering**: `yaml_io.py` (112 lines) validates read/write with `load_resume_yaml`, `save_resume_yaml`, plus dict variants. `renderer.py` (322 lines) deterministically emits LaTeX from canonical YAML.
- **Compile/page checks**: `compiler.py` (198 lines) compiles via `latexmk` and extracts page count via `pdfinfo` with LaTeX-log fallback.
- **Runtime loop**: `runtime.py` (640 lines) executes content passes with fit-score analysis (skip if >= 8), two readjust retries, bounded layout compression, explicit failure semantics, and optional git branch isolation.
- **Tool surface**: `tools.py` (211 lines) plus `scripts/resume_tailor_tools.py` expose DB, YAML, render, compile, page-count, backup, and restore operations as JSON-returning CLI commands.
- **Operational entrypoints**: `scripts/migrate_resume_tex_to_yaml.py` bootstraps canonical YAML from LaTeX; `scripts/run_resume_tailor.py` runs one tailoring job end-to-end.

## Resume Review Layer (Pi-Mono)
- **Review contracts**: `src/agents/resume_review_pi/schemas.py` (347 lines) defines `ReviewInvocationContract`, strict `ReviewReport` schema, `ReviewVerdict` enum, `ReviewJobRef`, `ReviewProfileLabel` enum, `PdfGeometryMetrics`, `PdfComparisonResult`, `LatexLogAnalysis`, `PdfTextSignals`, and `ReviewRunResult`.
- **Review prompt/runtime**: `prompts.py` (223 lines) enforces self-loop workflow and explicit `write-review-report` completion; `runtime.py` (335 lines) enforces hard-error-only boundaries.
- **Review analysis tools**: `tools.py` (778 lines) provides deterministic PDF geometry (raster-based margin/ink analysis), compare-to-base with profile labels, log parsing, text signals, and report writing helpers.
- **Review CLI surface**: `scripts/resume_review_tools.py` exposes tailor-equivalent tools plus review-specific analysis/report commands as deterministic JSON.

## Operational Scripts
- **scripts/query_jobs.py** (138 lines): Query/display jobs with filters (company/title/location/remote/new, limit).
- **scripts/find_greenhouse_id.py** (140 lines): Try/verify Greenhouse IDs via API helper patterns.
- **scripts/test_fetchers.py** (112 lines): Async smoke tests for Greenhouse and JobSpy fetchers.
- **scripts/decide_job.py** (88 lines): Run the root decider on a single job hash, optionally persisting status.
- **scripts/run_pipeline_once.py** (143 lines): One-shot `discovery -> gate-batch` orchestration command.
- **scripts/status.py** (252 lines): Terminal summary of database state including job counts by status, recent crawls, tailor/review run statistics, and failure diagnostics.

## Tailor Worker (Autonomous)
- **scripts/process_qualified_jobs.py** (712 lines): Autonomous daemon that claims QUALIFIED jobs via atomic transactions, invokes `run_resume_tailor_pipeline`, records results in `tailor_runs`, and writes a per-run YAML work copy artifact.
- Supports `--once` (one-shot) and `--loop` (persistent daemon) modes.
- Preflight checks: pi-mono command, latexmk, database path.
- Artifacts: `data/tailored_resumes/<job_hash>/resume_tailored.{tex,pdf}` and `resume_content_work.yaml`.

## Review Worker (Autonomous)
- **scripts/process_reviewed_resumes.py** (824 lines): Autonomous daemon that claims successful tailor runs, invokes `run_resume_review_pipeline`, records verdict/failure diagnostics in `review_runs`, and persists base fallback refs on hard runtime failures.
- Supports `--once` and `--loop` modes.
- Preflight checks: pi-mono command, latexmk, `pdfinfo`, `pdftotext`, `pdftoppm`, database path.
- Report artifact: `data/tailored_resumes/<job_hash>/review_report.json`.

## Configuration & Deployment
- **Config**: `companies.yaml`, `search_criteria.yaml`, `candidate_profile.yaml`, and `resume_content.yaml` drive discovery targeting + gate context. `resume_base.tex` and `resume_base.pdf` are pre-compiled base references.
- **Deployment**: timer+service producer (`job-discovery.*`) plus continuous gate consumer (`job-agent-worker.service`), continuous tailor consumer (`job-tailor-worker.service`), continuous review consumer (`job-review-worker.service`), and optional `job-agent-alert@.service`.

## Test Suite
- 33 test files in `tests/` covering: unit tests for models/fetchers/dedup, agent worker resilience, apply decider parsing, tailor/review runtime and tool contracts, CLI preflight, concurrent claim behavior, input validation, e2e pipeline flows, security/hygiene checks, and status command robustness.
