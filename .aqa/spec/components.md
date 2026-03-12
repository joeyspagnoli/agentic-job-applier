# Components

## Orchestrator
- **main.py**: Async entrypoint that loads configs, initializes DB and deduplicator, runs Greenhouse/Workday/JobSpy fetch pipelines, records crawl and daily stats, and logs cycle summaries [main.py:24-168](main.py:24-168).

## Data & Persistence
- **DatabaseManager**: Async SQLite wrapper with WAL tuning, schema creation, dedup-safe inserts, crawl logging, daily stats upsert, agent result/failed markers, and counters [src/database/db_manager.py:14-205](src/database/db_manager.py:14-205).
- **Schema**: Tables job_postings (dedup hash, status, salary, raw JSON), crawl_history, daily_stats; agent columns added via runtime migration [src/database/schema.sql:1-89](src/database/schema.sql:1-89).

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
- **RootApplyDecider agent**: ADK agent definition; `build_root_agent` sets JSON schema instruction, `get_decider_model` is a stub requiring injection [src/agents/root_apply_decider.py:1-105](src/agents/root_apply_decider.py:1-105).
- **Job processor**: `scripts/process_new_jobs.py` loads candidate profile, fetches NEW jobs, runs agent, and records decisions or failures [scripts/process_new_jobs.py:1-200](scripts/process_new_jobs.py:1-200).

## Operational Scripts
- **scripts/query_jobs.py**: Query/display jobs with filters (company/title/location/remote/new, limit) [scripts/query_jobs.py:1-109](scripts/query_jobs.py:1-109).
- **scripts/find_greenhouse_id.py**: Try/verify Greenhouse IDs via API helper patterns [scripts/find_greenhouse_id.py:1-108](scripts/find_greenhouse_id.py:1-108).
- **scripts/test_fetchers.py**: Async smoke tests for Greenhouse and JobSpy fetchers [scripts/test_fetchers.py:1-78](scripts/test_fetchers.py:1-78).
- **scripts/decide_job.py**: Run the root decider on a single job hash, optionally persisting status [scripts/decide_job.py:1-80](scripts/decide_job.py:1-80).

## Configuration & Deployment
- **Config**: Target companies/boards and search criteria for discovery [config/companies.yaml:1-120](config/companies.yaml:1-120) [config/search_criteria.yaml:1-70](config/search_criteria.yaml:1-70).
- **Deployment**: systemd oneshot service and 30-minute timer; deployment README with setup steps and placeholder edits [deploy/job-discovery.service:1-20](deploy/job-discovery.service:1-20) [deploy/job-discovery.timer:1-14](deploy/job-discovery.timer:1-14) [deploy/README.md:1-95](deploy/README.md:1-95).
