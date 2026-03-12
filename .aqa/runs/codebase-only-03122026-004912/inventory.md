# Inventory

## Repository Overview
- Root: /Users/josephspagnoli/Projects/agentic-job-applier
- Primary purpose: Python 3.11 job discovery pipeline fetching from Greenhouse, Workday (Apify), JobSpy; stores in SQLite; optional ADK agent for apply/skip.
- Notable large auxiliary content: `refs/` and `claude_notes/` contain external examples and transcripts; excluded from analysis scope.

## Languages & Frameworks
- Python 3.11 (core services, fetchers, scripts)
- YAML (configs under `config/`)
- Systemd unit/timer (deployment under `deploy/`)
- Markdown documentation (README, QUICKSTART, IMPLEMENTATION docs)

## Key Entry Points
- `main.py` — orchestrates fetch/dedup/stats cycle.
- `scripts/status.py` — status dashboard (CLI) for current DB state.
- `scripts/query_jobs.py` — ad-hoc query CLI.
- `scripts/process_new_jobs.py` — agent apply/skip processor (Phase 2).
- `scripts/decide_job.py`, `scripts/find_greenhouse_id.py`, `scripts/test_fetchers.py` — utility CLIs.

## Dependency Manifests
- `pyproject.toml` — project metadata and dependencies (aiosqlite, httpx, apify-client, python-jobspy, loguru, pydantic, pytest, google-adk, etc.).
- `uv.lock` — present at repo root (very large due to vendored refs; not reviewed here).

## Configuration Files
- `.env.example` — documents env vars (APIFY_API_TOKEN, DATABASE_PATH, LOG_LEVEL/FILE, agent keys, RUN_INTERVAL_MINUTES, AGENT_BATCH_SIZE).
- `config/companies.yaml` — target companies/boards (Greenhouse, Workday, job boards) with priorities and search params.
- `config/search_criteria.yaml` — desired titles/locations/salary/keywords for later filtering.
- `.gitignore` — excludes .env, data/, logs/ and typical Python artifacts.

## Database / Data Models
- `src/database/schema.sql` — tables job_postings, crawl_history, daily_stats + indexes.
- `src/models/job_posting.py` — Pydantic job model, hash, normalization helpers.
- `src/database/db_manager.py` — async SQLite manager (WAL, busy_timeout, CRUD, crawl logging, daily stats, agent migrations).

## Fetchers & Utilities
- `src/fetchers/` — base interface + Greenhouse, Apify Workday, JobSpy fetchers.
- `src/utils/deduplicator.py` — duplicate filter.
- `src/utils/logger.py` — loguru setup and summaries.

## Deployment
- `deploy/job-discovery.service` — systemd oneshot service (placeholders for user/path/venv).
- `deploy/job-discovery.timer` — systemd timer (30-minute cadence).
- `deploy/README.md` — deployment steps (uv sync, env, service install, verification).

## Tests
- `tests/test_integration.py` — pytest-based coverage for DatabaseManager, Deduplicator, crawl tracking, JobPosting hashing/normalization.

## Notable Non-Standard Structure
- Massive `refs/` directory with external agent examples and lockfiles; core application resides in root/src/scripts/config/deploy/tests. Analysis focused on core directories above.
