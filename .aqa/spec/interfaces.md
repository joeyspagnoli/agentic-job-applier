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
  - `update_job_status(job_hash, status)` [src/database/db_manager.py:131-147](src/database/db_manager.py:131-147).
  - `get_jobs_by_status(status, limit=100)` and `get_jobs_pending_agent_processing(limit=100)` [src/database/db_manager.py:149-183](src/database/db_manager.py:149-183).
  - Crawl logging: `start_crawl(source, company)` / `complete_crawl(crawl_id, jobs_found, jobs_new, error=None)` [src/database/db_manager.py:185-220](src/database/db_manager.py:185-220).
  - Daily stats: `update_daily_stats(date, jobs_discovered, jobs_new, jobs_duplicate, sources_crawled, sources_failed)` [src/database/db_manager.py:222-249](src/database/db_manager.py:222-249).
  - Agent workflow: `migrate_agent_schema()`, `record_agent_decision(job_hash, agent_result, status)`, `mark_job_agent_failed(job_hash, error)`, `update_job_agent_result(job_hash, agent_result)` [src/database/db_manager.py:251-321](src/database/db_manager.py:251-321).
  - Metrics: `get_job_count()`, `get_jobs_today()` [src/database/db_manager.py:323-349](src/database/db_manager.py:323-349).

## Deduplication
- **Deduplicator.filter_new_jobs(jobs)** returns only unseen jobs by hash and logs duplicates; **get_stats(jobs)** returns counts without filtering [src/utils/deduplicator.py:11-59](src/utils/deduplicator.py:11-59).

## Agent Interfaces (ADK)
- **RootApplyDecider agent**: built via `build_root_agent(model=...)`, outputs JSON adhering to RootApplyDeciderOutput schema; `get_decider_model()` stub must be implemented/injected [src/agents/root_apply_decider.py:24-103](src/agents/root_apply_decider.py:24-103).
- **Runner usage** in `scripts/process_new_jobs.py`: `_run_decider_for_job(agent, job, candidate_profile)` executes ADK runner and reads `DECIDER_OUTPUT_KEY` from session state [scripts/process_new_jobs.py:77-149](scripts/process_new_jobs.py:77-149).

## CLI / Operational Interfaces
- **Discovery cycle**: `python main.py` (reads env, sets up logger, runs async discovery) [main.py:105-167](main.py:105-167).
- **Job query**: `scripts/query_jobs.py --company/--title/--location/--remote/--new --limit N` [scripts/query_jobs.py:21-105](scripts/query_jobs.py:21-105).
- **Greenhouse helper**: `scripts/find_greenhouse_id.py <company> [--verify]` [scripts/find_greenhouse_id.py:19-105](scripts/find_greenhouse_id.py:19-105).
- **Fetcher smoke tests**: `scripts/test_fetchers.py` (no args) [scripts/test_fetchers.py:18-78](scripts/test_fetchers.py:18-78).
- **Single-job decider**: `scripts/decide_job.py --job-hash <hash> [--save]` [scripts/decide_job.py:32-79](scripts/decide_job.py:32-79).
- **Agent batch processor**: `scripts/process_new_jobs.py [--loop] [--limit N]` with env-controlled intervals [scripts/process_new_jobs.py:130-200](scripts/process_new_jobs.py:130-200).

## Configuration Inputs
- `config/companies.yaml`: lists Greenhouse boards, Workday URLs, JobSpy settings; each section keyed by source [config/companies.yaml:1-120](config/companies.yaml:1-120).
- `config/search_criteria.yaml`: target/exclusion patterns, locations, salary/experience bounds, keyword signals [config/search_criteria.yaml:1-70](config/search_criteria.yaml:1-70).
- Environment variables from `.env.example`: APIFY_API_TOKEN, DATABASE_PATH, LOG_LEVEL/FILE, agent keys, scheduler interval, AGENT_BATCH_SIZE [ .env.example:1-20](.env.example:1-20).

## Deployment Interfaces
- systemd oneshot unit `deploy/job-discovery.service` (requires path/user substitution) [deploy/job-discovery.service:1-17](deploy/job-discovery.service:1-17).
- systemd timer `deploy/job-discovery.timer` (30-minute cadence, randomized delay) [deploy/job-discovery.timer:1-12](deploy/job-discovery.timer:1-12).
- Deployment steps in `deploy/README.md` (uv sync, env, service/timer install, verification) [deploy/README.md:1-95](deploy/README.md:1-95).
