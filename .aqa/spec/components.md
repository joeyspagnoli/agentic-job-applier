# Components

## Component catalog

### 1) Discovery orchestrator (`main.py`)

- Loads config, runs source fetches, deduplicates results, writes new jobs and crawl/day metrics (`main.py:220-278`, `main.py:1039-1266`).
- Falls back to default JobSpy search terms when profile/search criteria are empty (`main.py:160-206`, `main.py:1067-1070`).

### 2) Fetcher adapters (`src/fetchers/*`)

- Core sources: Greenhouse, Workday via Apify, JobSpy (`src/fetchers/greenhouse_fetcher.py:157-188`, `src/fetchers/apify_fetcher.py:157-209`, `src/fetchers/jobspy_fetcher.py:17-333`).
- Additional sources/monitors: Ashby, Lever, LinkedIn, GitHub listings repo, career-page URL watcher (`src/fetchers/ashby_fetcher.py:72-233`, `src/fetchers/lever_fetcher.py:74-233`, `src/fetchers/linkedin_fetcher.py:127-234`, `src/fetchers/github_repo_fetcher.py:112-305`, `src/fetchers/career_page_watcher.py:117-194`).

### 3) Persistence and schema manager (`src/database/db_manager.py` + `src/database/schema.sql`)

- Owns DB init/migrations and stage claim/finalize/retry helpers (`src/database/db_manager.py:79-139`, `src/database/db_manager.py:1089-1255`, `src/database/db_manager.py:1793-1866`).
- Implements run tables, handoffs, cost/budget settings, and service-tier persistence (`src/database/schema.sql:99-148`, `src/database/db_manager.py:2430-2648`).

### 4) Stage workers (`scripts/process_*.py`)

- Gate worker: decisions + retry backoff + notifications (`scripts/process_new_jobs.py:266-345`).
- Tailor worker: claim → copy baseline YAML → tailor pipeline → persist outcomes (`scripts/process_qualified_jobs.py:404-534`).
- Review worker: claim tailored artifacts → review runtime → verdict/report/fallback metadata (`scripts/process_reviewed_resumes.py:360-457`, `scripts/process_reviewed_resumes.py:493-694`).
- Apply worker: browser automation with preflight/CDP checks and handoff creation (`scripts/process_apply_jobs.py:191-273`, `scripts/process_apply_jobs.py:437-859`).

### 5) Agent/tool subsystems (`src/agents/*`, `scripts/*_tools.py`)

- Root apply-decider prompt/runtime with cached candidate context and strict JSON output contract (`src/agents/root_apply_decider/prompts.py:351-507`, `src/agents/root_apply_decider/runtime.py:80-126`).
- Apply worker browser helpers and unresolved-field scanner (`src/agents/apply_worker/browser.py:88-164`, `src/agents/apply_worker/field_scanner.py:20-264`).
- Resume tailor/review tool CLIs with deterministic JSON envelopes (`scripts/resume_tailor_tools.py:30-247`, `scripts/resume_review_tools.py:35-344`).

### 6) API runtime (`api/main.py`)

- Serves operational endpoints, settings file routes, and dashboard SPA/static assets (`api/main.py:1479-2630`, `api/main.py:2938-3659`, `api/main.py:3663-3695`).

### 7) Dashboard runtime (`dashboard/src/*`)

- Jobs page: server-backed query + debounced search + expansion diagnostics (`dashboard/src/pages/JobsPage.tsx:76-247`, `dashboard/src/pages/JobsPage.tsx:295-386`).
- Human review and failures pages: queue/retry actions with query invalidation (`dashboard/src/pages/HumanReviewPage.tsx:382-545`, `dashboard/src/pages/FailuresPage.tsx:204-347`).
- Settings page: guided/raw/file editing for profile/resume/filters/sources, with tier gating for resume tooling (`dashboard/src/pages/SettingsPage.tsx:2344-3244`).
- Cost page: budget-aware spend analytics and stage/failure views (`dashboard/src/pages/CostTrackingPage.tsx:80-223`).

### 8) Ops/deployment scripts (`deploy/`, `scripts/docker/`)

- Compose profiles and worker orchestration wrappers (`docker-compose.yml:29-126`, `scripts/docker/run_workers.sh:15-72`).
- Chrome CDP startup helper for browser automation runtime (`deploy/start-chrome-cdp.sh:1-40`).
