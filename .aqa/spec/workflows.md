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
    Discovery->>DB: insert NEW jobs (after title filtering + dedup)
    loop every poll interval
        Worker->>DB: claim NEW + retry-ready jobs (BEGIN IMMEDIATE + claim token)
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
- Queue boundary: `job_postings` rows in status `NEW`, claimed via atomic tokens.

## Job Discovery Cycle
```mermaid
sequenceDiagram
    participant Timer as systemd timer
    participant Main as main.py
    participant Fetchers as Greenhouse/Apify/JobSpy
    participant Filter as Title filter
    participant Dedup as Deduplicator
    participant DB as DatabaseManager

    Timer->>Main: Exec main.py
    Main->>DB: create_tables(), migrate_agent_schema()
    Main->>Fetchers: fetch jobs per source
    Fetchers-->>Main: JobPosting list
    Main->>Filter: _filter_by_title_patterns(jobs)
    Filter-->>Main: filtered_jobs
    Main->>Dedup: filter_new_jobs(jobs)
    Dedup-->>Main: new_jobs
    Main->>DB: insert_job(new_jobs)
    Main->>DB: start/complete crawl, update_daily_stats
    Main->>Main: log summaries
```
- Trigger: systemd timer every 30 minutes.
- Steps: load configs (`companies`, optional `search_criteria` + `candidate_profile`), resolve board search terms, fetch per source, apply title include-pattern filtering, dedup (in-batch + DB lookup), insert NEW rows, update crawl and daily stats.

## One-shot Pipeline Workflow
- Command: `python -m scripts.run_pipeline_once [--limit N]`.
- Sequence:
  1. run one discovery cycle
  2. run one gate-processing batch against current NEW/retry-ready backlog
- Intended for local ops/debug and deterministic integration tests.

## Utility CLIs
- **Query jobs**: filter by company/title/location/remote/new, display results.
- **Find/verify Greenhouse ID**: try common patterns or verify an ID.
- **Smoke-test fetchers**: async checks for Greenhouse (Stripe) and JobSpy (Indeed).
- **Single-job decider**: run agent against one job hash, optionally persist.
- **Resume migration**: convert LaTeX source to canonical YAML (`scripts/migrate_resume_tex_to_yaml.py`).
- **Resume tailor tools**: DB/YAML/render/compile/page-count/backup/restore commands (`scripts/resume_tailor_tools.py`).
- **Resume review tools**: tailor-equivalent commands plus geometry/log/text/report commands (`scripts/resume_review_tools.py`).
- **Resume tailor runner**: one-job pi-mono tailoring loop with one-page enforcement (`scripts/run_resume_tailor.py`).
- **Database status**: terminal summary of pipeline state (`scripts/status.py`).

## Resume Tailor Workflow (On-Demand)
```mermaid
sequenceDiagram
    participant Operator as run_resume_tailor.py
    participant DB as SQLite
    participant Pi as pi-coding-agent
    participant YAML as resume_content.yaml
    participant Build as renderer/compiler

    Operator->>DB: db-get-job-context (job_hash|job_id)
    Operator->>Pi: fit-score analysis (score 1-10)
    alt score >= 8
        Operator-->>Operator: TAILORING_SKIPPED
    else score < 8
        Operator->>Pi: content pass prompt + tool commands
        Pi->>YAML: targeted listing/bullet edits below Education
        Operator->>Build: render .tex + compile PDF + page count
        alt page_count <= 1
            Operator-->>Operator: success
        else overflow
            loop max 2 content readjust retries
                Operator->>Pi: content retry prompt
                Pi->>YAML: shorter targeted edits / listing swaps
                Operator->>Build: render + compile + count
            end
            alt still overflow
                Operator->>YAML: apply balanced layout compression bounds
                Operator->>Build: render + compile + count
                alt still overflow
                    Operator-->>Operator: explicit failure
                else fit
                    Operator-->>Operator: success
                end
            else fit
                Operator-->>Operator: success
            end
        end
    end
```

## Autonomous Tailor Worker
```mermaid
sequenceDiagram
    participant Worker as process_qualified_jobs.py --loop
    participant DB as SQLite tailor_runs
    participant Pi as pi-mono coding agent
    participant Baseline as config/resume_content.yaml
    participant YAML as resume_content_work.yaml
    participant Build as renderer/compiler
    participant Alert as ntfy.sh

    loop every poll interval
        Worker->>DB: claim_next_tailor_job (BEGIN IMMEDIATE)
        alt no eligible job
            Worker->>Worker: sleep(poll_interval)
        else claimed
            Worker->>Baseline: copy to per-run work YAML
            Worker->>Pi: run_resume_tailor_pipeline
            Pi->>YAML: targeted edits
            Worker->>Build: render .tex + compile PDF
            alt success (1 page)
                Worker->>DB: record_tailor_success (yaml/tex/pdf paths, page count)
            else failure
                Worker->>DB: record_tailor_failure (error, next_retry_at)
                Worker->>Alert: send failure notification
            end
        end
    end
```

- Worker: `scripts/process_qualified_jobs.py --loop` via `job-tailor-worker.service`.
- Queue boundary: `job_postings` rows in status `QUALIFIED` without a SUCCESS tailor_run.
- State: `tailor_runs` table tracks per-attempt PENDING/SUCCESS/FAILED with claim lease.

## Autonomous Review Worker
```mermaid
sequenceDiagram
    participant Worker as process_reviewed_resumes.py --loop
    participant DB as SQLite review_runs
    participant Pi as pi-mono coding agent
    participant Tools as resume_review_tools.py
    participant Base as resume_base.{tex,pdf}
    participant Alert as ntfy.sh

    loop every poll interval
        Worker->>DB: claim_next_review_job (BEGIN IMMEDIATE)
        alt no eligible run
            Worker->>Worker: sleep(poll_interval)
        else claimed
            Worker->>Base: ensure base reference artifacts exist
            Worker->>Pi: run_resume_review_pipeline
            Pi->>Tools: analyze geometry/log/text + optional edits + write-review-report
            alt runtime hard failure
                Worker->>DB: record_review_failure (error + stdout/stderr + base fallback refs)
                Worker->>Alert: send terminal failure notification when retries exhausted
            else runtime success
                Worker->>DB: record_review_success (verdict + selected refs + report json)
            end
        end
    end
```

- Worker: `scripts/process_reviewed_resumes.py --loop` via `job-review-worker.service`.
- Queue boundary: successful `tailor_runs` rows without a successful `review_runs` row.
- State: `review_runs` tracks PENDING/SUCCESS/FAILED, verdicts, report payloads, retry scheduling, and base fallback references.

## Deployment Flow
- Install deps and configure `.env`.
- Install system dependencies: texlive-full, latexmk (for tailor worker).
- Configure and install:
  - `job-discovery.service`
  - `job-discovery.timer`
  - `job-agent-worker.service`
  - `job-tailor-worker.service`
  - `job-review-worker.service`
  - optional `job-agent-alert@.service`
- Enable all autonomous units:
  - `job-discovery.timer`
  - `job-agent-worker.service`
  - `job-tailor-worker.service`
  - `job-review-worker.service`
