# Worker Findings

- Worker: src-3
- Completed: 2026-03-12T04:50:51.838Z
- Task: QA explore: models, utils, schema, configs, CLI scripts

## Summary
Reviewed the standardized job posting model (`src/models/job_posting.py:13-103`), the SQLite schema definitions (`src/database/schema.sql:2-53`), the query/utility scripts (`scripts/query_jobs.py:30-105`, `scripts/find_greenhouse_id.py`, `scripts/test_fetchers.py`, `scripts/decide_job.py`), logging/deduplication helpers (`src/utils/logger.py`, `src/utils/deduplicator.py`), deployment docs/timer (`deploy/README.md`, `deploy/job-discovery.timer`), configuration (`config/search_criteria.yaml`), environment template (`.env.example:4-21`), and packaging metadata (`pyproject.toml`). These cover the requested models, utilities, schema, configs, and CLI scripts.

## Findings
- `scripts/query_jobs.py` always opens `data/jobs.db` (hard-coded path) and never reads `DATABASE_PATH` from the environment, so when the app is configured to use a custom database path via `.env` the query script is unable to target that database and will report “Database not found.” (`scripts/query_jobs.py:30-84`, `.env.example:4-6`)

## Evidence
1. `scripts/query_jobs.py:30-84` – The query helper hardcodes `db_path = .../data/jobs.db` and never checks environment variables before connecting.
2. `.env.example:4-6` – The documented configuration exposes `DATABASE_PATH=data/jobs.db`, indicating that other parts of the app expect the path to be configurable; the CLI should mirror that behavior.

## Recommendations
- Update `scripts/query_jobs.py` to resolve its database path via `os.getenv("DATABASE_PATH", Path(...)/"data"/"jobs.db")` (or similar) so it respects the user’s `.env` configuration and can query the same database used by the main application (`.env.example:4-6` provides the expected env variable name).
