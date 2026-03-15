# Codebase Info

## Overview
- Name: agentic-job-applier
- Primary language: Python 3.11+ (`.python-version` pins 3.11; `pyproject.toml` requires >=3.11) [.python-version:1](.python-version:1) [pyproject.toml:1-18](pyproject.toml:1-18)
- Purpose: Discover job postings from multiple sources (Greenhouse, Workday via Apify, JobSpy), deduplicate, store in SQLite, and optionally run an ADK agent to decide whether to apply.

## Key Directories
- `src/`: core library
  - `agents/`: ADK decision agents organized as per-agent packages (`root_apply_decider/`, plus shared helpers) [src/agents/root_apply_decider/__init__.py](../../src/agents/root_apply_decider/__init__.py)
  - `fetchers/`: source-specific fetchers (`greenhouse_fetcher.py`, `apify_fetcher.py`, `jobspy_fetcher.py`) plus `base_fetcher.py` [src/fetchers/base_fetcher.py:1-32](src/fetchers/base_fetcher.py:1-32)
  - `database/`: SQLite manager and schema [src/database/db_manager.py:1-210](src/database/db_manager.py:1-210) [src/database/schema.sql:1-89](src/database/schema.sql:1-89)
  - `models/`: shared Pydantic models (JobPosting) [src/models/job_posting.py:1-103](src/models/job_posting.py:1-103)
  - `utils/`: logging, deduplication, path resolution, ntfy notification helper
- `scripts/`: operational CLIs (query/find/test/decide/process) plus one-shot pipeline command `run_pipeline_once.py`
- `config/`: `companies.yaml`, `search_criteria.yaml`, `candidate_profile.yaml`
- `deploy/`: producer timer/service, consumer worker service, optional alert hook, deployment README

## Tooling & Dependencies
- Runtime: Python >=3.11 (.python-version, pyproject) [.python-version:1](.python-version:1) [pyproject.toml:1-18](pyproject.toml:1-18)
- Key deps: aiosqlite, httpx, apify-client, python-jobspy, loguru, pydantic, apscheduler, google-adk, dotenv, pyyaml, pytest/pytest-asyncio [pyproject.toml:5-18](pyproject.toml:5-18)
- Package manager: uv (noted in deploy docs) [deploy/README.md:7-18](deploy/README.md:7-18)

## Config & Environment
- `.env.example` documents source credentials, gate model keys, retry/backoff settings, ntfy settings, profile override, and journal mode override.
- `config/companies.yaml` lists target Greenhouse boards, Workday URLs, and JobSpy board settings [config/companies.yaml:1-120](config/companies.yaml:1-120)
- `config/search_criteria.yaml` captures desired/undesired titles, locations, salary/experience bounds, keywords (used mainly for future filtering) [config/search_criteria.yaml:1-70](config/search_criteria.yaml:1-70)

## Data & Persistence
- SQLite schema for `job_postings`, `crawl_history`, `daily_stats`; queue retry fields and indexes are migrated automatically by `DatabaseManager`.

## Execution Entrypoints
- Discovery orchestrator: `main.py` (async cycle over sources, dedup, stats, logging) [main.py:1-168](main.py:1-168)
- Agent processor: `scripts/process_new_jobs.py` (pull NEW/retry-ready jobs, run ADK decider, persist success/retry/terminal failure state)
- One-shot pipeline: `scripts/run_pipeline_once.py` (discovery then one gate batch)
- Utility CLIs: query, find IDs, test fetchers, single-job decider [scripts/query_jobs.py:1-109](scripts/query_jobs.py:1-109) [scripts/find_greenhouse_id.py:1-108](scripts/find_greenhouse_id.py:1-108) [scripts/test_fetchers.py:1-78](scripts/test_fetchers.py:1-78) [scripts/decide_job.py:1-80](scripts/decide_job.py:1-80)

## Deployment
- systemd producer timer/service (`job-discovery.*`) + continuous worker (`job-agent-worker.service`) for autonomous runtime.
