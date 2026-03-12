# Workflows

## Job Discovery Cycle
```mermaid
sequenceDiagram
    participant Timer as systemd timer
    participant Main as main.py
    participant Fetchers as Greenhouse/Apify/JobSpy
    participant Dedup as Deduplicator
    participant DB as DatabaseManager

    Timer->>Main: Exec main.py
    Main->>DB: create_tables(), migrate_agent_schema()
    Main->>Fetchers: fetch jobs per source
    Fetchers-->>Main: JobPosting list
    Main->>Dedup: filter_new_jobs(jobs)
    Dedup-->>Main: new_jobs
    Main->>DB: insert_job(new_jobs)
    Main->>DB: start/complete crawl, update_daily_stats
    Main->>Main: log summaries
```
- Trigger: systemd timer every 30 minutes (oneshot service) [deploy/job-discovery.timer:1-12](deploy/job-discovery.timer:1-12).
- Steps: load env/logging, load company configs, fetch per source, dedup and insert, record crawl history and daily stats, log cycle summary [main.py:24-168](main.py:24-168).

## Agent Decision Loop (Phase 2)
```mermaid
sequenceDiagram
    participant Runner as process_new_jobs.py
    participant DB as DatabaseManager
    participant Agent as RootApplyDecider (ADK)

    Runner->>DB: get_jobs_pending_agent_processing(limit)
    DB-->>Runner: NEW jobs
    Runner->>Agent: run per job with profile prompt
    Agent-->>Runner: RootApplyDeciderOutput
    Runner->>DB: record_agent_decision / mark_job_agent_failed
```
- Entry: `scripts/process_new_jobs.py --loop|--once`; loads env, candidate profile, ADK model (stub), processes NEW jobs [scripts/process_new_jobs.py:130-200](scripts/process_new_jobs.py:130-200).
- Model requirement: `get_decider_model()` stub must be implemented; otherwise jobs are skipped with a warning [src/agents/root_apply_decider.py:51-74](src/agents/root_apply_decider.py:51-74) [scripts/process_new_jobs.py:156-164](scripts/process_new_jobs.py:156-164).

## Utility CLIs
- **Query jobs**: filter by company/title/location/remote/new, display results [scripts/query_jobs.py:21-105](scripts/query_jobs.py:21-105).
- **Find/verify Greenhouse ID**: try common patterns or verify an ID [scripts/find_greenhouse_id.py:19-105](scripts/find_greenhouse_id.py:19-105).
- **Smoke-test fetchers**: async checks for Greenhouse (Stripe) and JobSpy (Indeed) [scripts/test_fetchers.py:18-78](scripts/test_fetchers.py:18-78).
- **Single-job decider**: run agent against one job hash, optionally persist [scripts/decide_job.py:32-79](scripts/decide_job.py:32-79).

## Deployment Flow
- Install deps with uv, copy .env, edit systemd service placeholders (User, WorkingDirectory, PATH, ExecStart), install service+timer, enable and verify [deploy/README.md:7-54](deploy/README.md:7-54) [deploy/job-discovery.service:5-17](deploy/job-discovery.service:5-17).
- Timer runs main.py every 30 minutes with randomized delay to avoid thundering herd [deploy/job-discovery.timer:4-12](deploy/job-discovery.timer:4-12).
