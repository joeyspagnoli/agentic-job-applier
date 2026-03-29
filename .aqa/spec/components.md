# Components

## Component Catalog

### 1) Discovery Orchestrator (`main.py`)

- Loads config/env and runs source fetch cycles.
- Deduplicates normalized `JobPosting` records.
- Persists new rows + crawl/day metrics.

### 2) Fetcher Adapters (`src/fetchers/*`)

- Greenhouse API fetcher
- Apify Workday fetcher
- JobSpy board fetcher

All adapters normalize to the shared `JobPosting` model.

### 3) Persistence Layer (`src/database/db_manager.py` + `schema.sql`)

- Owns SQLite lifecycle and migration helpers.
- Implements claim/retry semantics for all stages.
- Implements cost schema + budget helpers.
- Implements mutation helpers used by API routes (handoff transitions and stage resets).

### 4) Agent Subsystems (`src/agents/*`)

- Gate decider (apply/skip)
- Resume tailor runtime
- Resume review runtime
- Browser apply worker runtime

### 5) Stage Worker Scripts (`scripts/process_*.py`)

- `process_new_jobs.py`
- `process_qualified_jobs.py`
- `process_reviewed_resumes.py`
- `process_apply_jobs.py`

They execute stage logic, persist run status, and now record cost events via `src/utils/cost_tracking.py`.

### 6) API Runtime (`api/main.py`)

- Serves deterministic JSON endpoints for dashboard pages.
- Serves settings file upload/download routes.
- Applies startup migrations (including cost schema).
- Mounts built dashboard static assets and SPA fallback routes.

### 7) Frontend Dashboard (`dashboard/`)

- Page-level views: Dashboard, Jobs, Human Review, Failures, Cost Tracking.
- Shared typed API client and DTO adapters (`dashboard/src/lib/api/*`).
- React Query query client with global polling.
- Top bar sync trigger (`invalidateQueries`) and live sync status.

### 8) Deployment Assets (`deploy/`)

- Systemd units for discovery + workers + Chrome CDP runtime.
- Deployment documentation and alert unit templates.
