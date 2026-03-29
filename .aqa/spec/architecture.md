# Architecture

## System Overview

The system is a staged automation pipeline plus an operations control plane.

- Pipeline writes and advances job state in SQLite.
- FastAPI exposes live operational data and mutation endpoints.
- React dashboard consumes API endpoints with polling and explicit mutations.

```mermaid
graph LR
    Discover[Discovery Orchestrator] --> Jobs[(job_postings)]

    Jobs --> Gate[Gate Worker]
    Gate --> Jobs

    Jobs --> Tailor[Tailor Worker]
    Tailor --> TailorRuns[(tailor_runs)]

    TailorRuns --> Review[Review Worker]
    Review --> ReviewRuns[(review_runs)]

    ReviewRuns --> Apply[Apply Worker]
    Apply --> ApplyRuns[(apply_runs)]
    Apply --> Handoffs[(apply_handoffs)]

    Gate --> Cost[(cost_events)]
    Tailor --> Cost
    Review --> Cost
    Apply --> Cost

    API[FastAPI /api/*] --> Jobs
    API --> TailorRuns
    API --> ReviewRuns
    API --> ApplyRuns
    API --> Handoffs
    API --> Cost
    API --> Budget[(budget_settings)]

    UI[React Dashboard] --> API
```

## Runtime Boundaries

### Discovery Boundary

- `main.py` loads config, fetches sources, deduplicates, persists jobs, records crawl metrics.

### Worker Boundaries

- Gate worker (`scripts/process_new_jobs.py`)
- Tailor worker (`scripts/process_qualified_jobs.py`)
- Review worker (`scripts/process_reviewed_resumes.py`)
- Apply worker (`scripts/process_apply_jobs.py`)

Each worker claims work atomically and persists attempt outcomes, retries, and terminal failures.

### API/UI Boundary

- `api/main.py` runs startup migrations and serves `/api/*`.
- Dashboard static build is served by FastAPI assets mount + SPA fallback.
- Dashboard dev mode proxies `/api` to backend via Vite proxy config.

## Deployment Topology

Primary homeserver topology uses systemd timer/services for discovery and continuous workers, plus a dedicated Chrome CDP unit for apply runtime.
