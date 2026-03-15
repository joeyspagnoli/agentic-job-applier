# Workflows

## Autonomous Producer/Consumer Runtime
```mermaid
sequenceDiagram
    participant Timer as job-discovery.timer
    participant Discovery as main.py
    participant DB as SQLite job_postings
    participant Worker as process_new_jobs.py --loop
    participant Gate as RootApplyDecider
    participant Alert as ntfy.sh

    Timer->>Discovery: run every 30 minutes
    Discovery->>DB: insert NEW jobs
    loop every poll interval
        Worker->>DB: get NEW + retry-ready jobs
        Worker->>Gate: run decision per job
        alt success
            Worker->>DB: record_agent_decision (QUALIFIED/FILTERED)
        else transient failure
            Worker->>DB: record_agent_retry (count + next_retry_at)
        else retry limit reached
            Worker->>DB: mark_job_agent_terminal_failed
            Worker->>Alert: send terminal failure notification
        end
    end
```

- Producer: `main.py` via `job-discovery.timer`.
- Consumer: `scripts/process_new_jobs.py --loop` via `job-agent-worker.service`.
- Queue boundary: `job_postings` rows in status `NEW`.

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
- Trigger: systemd timer every 30 minutes.
- Steps: load configs (`companies`, optional `search_criteria` + `candidate_profile`), fetch per source, dedup, insert NEW rows, update crawl and daily stats.

## One-shot Pipeline Workflow
- Command: `python -m scripts.run_pipeline_once [--limit N]`.
- Sequence:
  1. run one discovery cycle
  2. run one gate-processing batch against current NEW/retry-ready backlog
- Intended for local ops/debug and deterministic integration tests.

## Utility CLIs
- **Query jobs**: filter by company/title/location/remote/new, display results [scripts/query_jobs.py:21-105](scripts/query_jobs.py:21-105).
- **Find/verify Greenhouse ID**: try common patterns or verify an ID [scripts/find_greenhouse_id.py:19-105](scripts/find_greenhouse_id.py:19-105).
- **Smoke-test fetchers**: async checks for Greenhouse (Stripe) and JobSpy (Indeed) [scripts/test_fetchers.py:18-78](scripts/test_fetchers.py:18-78).
- **Single-job decider**: run agent against one job hash, optionally persist [scripts/decide_job.py:32-79](scripts/decide_job.py:32-79).

## Deployment Flow
- Install deps and configure `.env`.
- Configure and install:
  - `job-discovery.service`
  - `job-discovery.timer`
  - `job-agent-worker.service`
  - optional `job-agent-alert@.service`
- Enable both autonomous units:
  - `job-discovery.timer`
  - `job-agent-worker.service`
