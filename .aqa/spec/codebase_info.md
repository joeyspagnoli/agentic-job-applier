# Codebase Info

## Overview
- Name: agentic-job-applier
- Primary language: Python 3.11+ (`.python-version` pins 3.11; `pyproject.toml` requires >=3.11) [.python-version:1](.python-version:1) [pyproject.toml:1-18](pyproject.toml:1-18)
- Purpose: Discover job postings from multiple sources (Greenhouse, Workday via Apify, JobSpy), deduplicate, store in SQLite, and optionally run an ADK agent to decide whether to apply.

## Key Directories
- `src/`: core library
  - `agents/`: ADK decision agent stub and builder (`root_apply_decider.py`) [src/agents/root_apply_decider.py:1-105](src/agents/root_apply_decider.py:1-105)
  - `fetchers/`: source-specific fetchers (`greenhouse_fetcher.py`, `apify_fetcher.py`, `jobspy_fetcher.py`) plus `base_fetcher.py` [src/fetchers/base_fetcher.py:1-32](src/fetchers/base_fetcher.py:1-32)
  - `database/`: SQLite manager and schema [src/database/db_manager.py:1-210](src/database/db_manager.py:1-210) [src/database/schema.sql:1-89](src/database/schema.sql:1-89)
  - `models/`: shared Pydantic models (JobPosting) [src/models/job_posting.py:1-103](src/models/job_posting.py:1-103)
  - `utils/`: logging and deduplication helpers [src/utils/logger.py:1-91](src/utils/logger.py:1-91) [src/utils/deduplicator.py:1-59](src/utils/deduplicator.py:1-59)
- `scripts/`: operational CLIs (query jobs, find Greenhouse IDs, test fetchers, run decider) [scripts/query_jobs.py:1-109](scripts/query_jobs.py:1-109) [scripts/find_greenhouse_id.py:1-108](scripts/find_greenhouse_id.py:1-108) [scripts/test_fetchers.py:1-78](scripts/test_fetchers.py:1-78) [scripts/decide_job.py:1-80](scripts/decide_job.py:1-80) [scripts/process_new_jobs.py:1-200](scripts/process_new_jobs.py:1-200)
- `config/`: discovery targets and search criteria [config/companies.yaml:1-120](config/companies.yaml:1-120) [config/search_criteria.yaml:1-70](config/search_criteria.yaml:1-70)
- `deploy/`: systemd units and deployment guide [deploy/job-discovery.service:1-20](deploy/job-discovery.service:1-20) [deploy/job-discovery.timer:1-14](deploy/job-discovery.timer:1-14) [deploy/README.md:1-95](deploy/README.md:1-95)

## Tooling & Dependencies
- Runtime: Python >=3.11 (.python-version, pyproject) [.python-version:1](.python-version:1) [pyproject.toml:1-18](pyproject.toml:1-18)
- Key deps: aiosqlite, httpx, apify-client, python-jobspy, loguru, pydantic, apscheduler, google-adk, dotenv, pyyaml, pytest/pytest-asyncio [pyproject.toml:5-18](pyproject.toml:5-18)
- Package manager: uv (noted in deploy docs) [deploy/README.md:7-18](deploy/README.md:7-18)

## Config & Environment
- `.env.example` documents required env vars: APIFY_API_TOKEN, DATABASE_PATH, LOG_LEVEL/FILE, scheduler interval, agent keys, AGENT_BATCH_SIZE [ .env.example:1-20](.env.example:1-20)
- `config/companies.yaml` lists target Greenhouse boards, Workday URLs, and JobSpy board settings [config/companies.yaml:1-120](config/companies.yaml:1-120)
- `config/search_criteria.yaml` captures desired/undesired titles, locations, salary/experience bounds, keywords (used mainly for future filtering) [config/search_criteria.yaml:1-70](config/search_criteria.yaml:1-70)

## Data & Persistence
- SQLite schema for job_postings, crawl_history, daily_stats defined in `schema.sql`; agent fields added via runtime migration [src/database/schema.sql:1-89](src/database/schema.sql:1-89) [src/database/db_manager.py:118-205](src/database/db_manager.py:118-205)

## Execution Entrypoints
- Discovery orchestrator: `main.py` (async cycle over sources, dedup, stats, logging) [main.py:1-168](main.py:1-168)
- Agent processor: `scripts/process_new_jobs.py` (pull NEW jobs, run ADK decider, persist results) [scripts/process_new_jobs.py:1-200](scripts/process_new_jobs.py:1-200)
- Utility CLIs: query, find IDs, test fetchers, single-job decider [scripts/query_jobs.py:1-109](scripts/query_jobs.py:1-109) [scripts/find_greenhouse_id.py:1-108](scripts/find_greenhouse_id.py:1-108) [scripts/test_fetchers.py:1-78](scripts/test_fetchers.py:1-78) [scripts/decide_job.py:1-80](scripts/decide_job.py:1-80)

## Deployment
- systemd oneshot service & 30-minute timer; deploy README covers setup/edit placeholders and enablement [deploy/job-discovery.service:1-20](deploy/job-discovery.service:1-20) [deploy/job-discovery.timer:1-14](deploy/job-discovery.timer:1-14) [deploy/README.md:1-95](deploy/README.md:1-95)
