# Worker Findings

- Worker: root-1
- Completed: 2026-03-12T04:50:58.187Z
- Task: QA explore: db/core entrypoints and service config

## Summary
Reviewed the orchestration and DB entry points driving the job discovery pipeline (`main.py` and `src/database/db_manager.py`), confirmed the base fetcher interface that every source implements (`src/fetchers/base_fetcher.py`), and checked the placeholder systemd service unit plus Python runtime pinning (`deploy/job-discovery.service`, `.python-version`). Together these files show how config loading, fetch scheduling, deduplication, stats, and deployment glue are wired up for Python 3.11 [main.py:208-322][src/database/db_manager.py:30-335][src/fetchers/base_fetcher.py:1-32][deploy/job-discovery.service:1-17][.python-version:1].

## Findings
- **`run_job_discovery()` seals the end-to-end cycle via config load, DB init, per-source fetches, deduplication, crawl logging, and daily stats before summarizing totals.** [main.py:208-322]
- **`DatabaseManager` centralizes SQLite access (connection setup with WAL/busy timeout, insert/get/update helpers, crawl history logging, daily stats aggregation, and automatic agent-related schema migration/indexing).** [src/database/db_manager.py:30-335]
- **The provided systemd service unit still uses placeholder values for `User`, `WorkingDirectory`, `PATH`, and invokes `python main.py` without sourcing the project’s venv or .env, so it cannot run as-is on the target host.** [deploy/job-discovery.service:5-17]

## Evidence
1. `main.py:208-322` – documents `run_job_discovery()` reading `config/companies.yaml`, initializing `DatabaseManager`, invoking each fetcher with deduplication, updating `daily_stats`, and logging totals before exiting.
2. `src/database/db_manager.py:30-335` – shows async connection setup, schema creation, insert/duplicate handling, crawl history recording, stats updates, agent column migrations, and context-manager support.
3. `deploy/job-discovery.service:5-17` – reveals placeholders for user/path/environment variables and a bare `python main.py` invocation, plus no `EnvironmentFile` or virtualenv activation.

## Recommendations
1. **Maintain the orchestrator as-is but ensure the expected config and env files exist before scheduling.** The pipeline already handles retries, deduplication, and stats, so document prerequisites such as creating `config/companies.yaml`, setting `DATABASE_PATH`, and defining `APIFY_API_TOKEN` to keep the cycle healthy [main.py:208-322].
2. **Continue using `DatabaseManager` for all DB access since it already protects concurrency, deduplication, crawl tracking, and agent metadata via `migrate_agent_schema()`.** No immediate changes required unless upstream schema evolves [src/database/db_manager.py:30-335].
3. **Update `deploy/job-discovery.service` with the real system user/path values and load the project’s `.env` or virtualenv before running `main.py`.** For example, set `User=agentic`, point `WorkingDirectory`/`Environment` to the repo location, and use `ExecStart=/path/to/.venv/bin/python -m uv run python src/main.py` (or switch to `uv run`) so the service can execute with the correct runtime and secrets [deploy/job-discovery.service:5-17].
