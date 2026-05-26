# FastAPI HTTP API Subsystem Specification

**Date:** 2026-05-25  
**Scope:** Backend HTTP API routers, schemas, services, and integration with the in-process asyncio supervisor  
**Status:** Architectural documentation for dashboard product

---

## 1. Purpose

The FastAPI HTTP API serves as the unified runtime boundary for the agentic job applier dashboard product. It provides:

1. **JSON API endpoints** (`/api/*`) backed by SQLite, delegated to specialized routers
2. **Static React SPA serving** from `dashboard/dist` with client-side routing fallback
3. **In-process asyncio supervisor** that runs discovery, gate, tailor, and apply worker loops
4. **Dashboard-driven user interactions** (manual tailor/apply triggers, human review actions, settings mutations)
5. **Real-time pipeline status** accessible to the browser via health, status, and cost endpoints

The API is single-user, localhost-scoped. No cross-origin auth is enforced; operators who want real authentication deploy a reverse proxy in front.

---

## 2. App Composition

### 2.1 Lifespan and Initialization

**File:** `api/main.py:62`

```python
app = FastAPI(lifespan=_lifespan)
```

The FastAPI lifespan hook (defined in `api/services/migrations.py:_lifespan`) orchestrates:

1. **Startup** (`api/services/migrations.py:67-87`):
   - Run idempotent DB schema migrations (`migrate_agent_schema`, `migrate_tailor_schema`, `migrate_review_schema`, `migrate_apply_schema`, `migrate_cost_schema`)
   - Validate `candidate_profile.yaml` against the `CandidateProfile` schema
   - Boot the `LoopSupervisor` (`api/services/supervisor.py:start_supervisor`) which:
     - Always runs the discovery loop (no LLM spend)
     - Conditionally runs gate/tailor/apply loops based on per-stage automation mode rows
     - Spawns a mode-watcher that reconciles loop state when the autonomous toggle flips

2. **Shutdown** (`api/services/supervisor.py:604-626`):
   - Cancel all supervised tasks (discovery + gated loops + mode watcher)
   - Close the shared database connection

### 2.2 Router Registration

**File:** `api/main.py:67-85`

The following routers are included in execution order:

| Router Module | Prefix | Purpose |
|---|---|---|
| `health_router` | `/api` | Lightweight liveness check |
| `system_router` | `/api/system` | System lifecycle (stop/restart/fetch-jobs) |
| `costs_router` | `/api/costs` | Cost tracking KPIs and trends |
| `dashboard_router` | `/api/dashboard` | Dashboard KPI cards and funnel |
| `failures_router` | `/api/failures` | Unified stage failures + retry |
| `human_review_router` | `/api/human-review` | Handoff queue, complete/dismiss, answer persistence |
| `jobs_router` | `/api/jobs` | Job listing, tailored resume download, manual import |
| `pipeline_router` | `/api/pipeline` | SSE stream for real-time progress (stub) |
| `settings_api_keys_router` | `/api/settings` | API key read/write/validate |
| `settings_budget_router` | `/api/budget` | Monthly budget settings |
| `settings_files_router` | `/api/settings` | Settings file metadata |
| `settings_filters_router` | `/api/settings` | Filters and sources YAML |
| `settings_profile_router` | `/api/settings` | Candidate profile YAML read/write |
| `settings_provider_router` | `/api/settings` | AI provider BYOK (OpenAI only) |
| `settings_resume_router` | `/api/settings` | Resume `.tex` upload/validation/download |
| `status_router` | `/api/settings` / `/api/status` | Autonomous readiness, Chrome status, autonomous mode toggle |
| `system_settings_router` | `/api/system-settings` | Per-stage automation modes |
| `apply_runs_router` | `/api` | Manual apply trigger, polling, soft-delete |
| `tailor_runs_router` | `/api` | Manual tailor trigger, polling, soft-delete, retry |

### 2.3 Static Dashboard Serving

**File:** `api/main.py:64-65, 116-148`

```python
if DASHBOARD_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DASHBOARD_ASSETS_DIR), name="assets")
```

- Assets mounted at `/assets/*` when `dashboard/dist/assets` exists
- Catch-all SPA fallback at `GET /{full_path:path}` serves `index.html` for all non-API routes
- 404 with `DASHBOARD_BUILD_MISSING` when build is absent (returned via `_raise_api_error`)

### 2.4 Exception Handling

**File:** `api/main.py:88-113`

All `HTTPException` raised by routers are normalized to a deterministic JSON shape via `_http_exception_handler`:

```json
{
  "ok": false,
  "code": "ERROR_CODE",
  "message": "Human-readable summary",
  "details": {}
}
```

Error codes are stable machine-readable identifiers (e.g., `MODE_AUTONOMOUS`, `BUDGET_EXCEEDED`, `RUN_ALREADY_EXISTS`).

---

## 3. Comprehensive Endpoint Reference

### 3.1 Full Endpoint Table

| Method | Path | Router | Status | Summary | Response Shape | Side Effects |
|--------|------|--------|--------|---------|---|---|
| **HEALTH & LIFECYCLE** |
| GET | `/api/health` | health | 200 | Liveness + polling interval | `{ok, status, polling_seconds}` | None |
| GET | `/api/system/health` | system | 200 | OpenAI key configured signal | `SystemHealthResponse` | None |
| POST | `/api/system/stop` | system | 200 | Dispatch stack stop action | `{ok, action, status, request_id}` | Spawns shell script (`stop_stack.sh`) |
| POST | `/api/system/restart` | system | 200 | Dispatch stack restart action | `{ok, action, status, request_id}` | Spawns shell script (`restart_stack.sh`) |
| POST | `/api/system/fetch-jobs` | system | 200 | Trigger immediate discovery | `{ok, action, status, request_id}` | Spawns shell script (`restart_discovery.sh`) |
| **STATUS & AUTONOMOUS** |
| GET | `/api/status/autonomous-readiness` | status | 200 | Hard requirements for autonomous mode | `AutonomousReadinessResponse` | Probes OpenAI key, resume.tex, profile.yaml |
| GET | `/api/status/chrome?os=mac` | status | 200 | Chrome CDP reachability + launch hint | `ChromeStatusResponse` | Probes Chrome at `CHROME_CDP_URL` |
| GET | `/api/settings/autonomous-mode` | status | 200 | Derived global toggle state | `AutonomousModeResponse` | None |
| POST | `/api/settings/autonomous-mode` | status | 200 | Flip all stages on/off atomically | `AutonomousModeResponse` | Validates requirements, writes DB, notifies supervisor |
| **JOBS & DISCOVERY** |
| GET | `/api/jobs?search=&page=1&status=&source=&has_tailor_run=false` | jobs | 200 | Paginated jobs table | `{ok, page, page_size, total_items, total_pages, items: [...]}` | SQL query joins job_postings + tailor_runs + review_runs + apply_runs |
| GET | `/api/jobs/{job_hash}/resume` | jobs | 200 | Download tailored resume PDF | `FileResponse` (PDF) | None (file read-only) |
| POST | `/api/jobs/import` | jobs | 200 | Manual job posting import | `{ok, job_hash, job_id, duplicate}` | Inserts `job_postings` row (dedup on hash) |
| **TAILOR RUNS** |
| POST | `/api/jobs/{job_hash}/tailor` | tailor_runs | 202 | Enqueue user-triggered tailor | `{ok, tailor_run_id, status, job_hash}` | Insert PENDING row, add BackgroundTask, optionally enqueue apply |
| GET | `/api/tailor-runs/{run_id}` | tailor_runs | 200 | Poll tailor run state | `{ok, tailor_run: {...}}` | SQL read, no write |
| GET | `/api/tailor-runs/{run_id}/plan` | tailor_runs | 200 | Read planner-rationale JSON | `{ok, plan: {...}}` | File read from disk |
| DELETE | `/api/tailor-runs/{run_id}` | tailor_runs | 204 | Soft-delete tailor run | (empty) | Soft-delete row, best-effort artifact cleanup |
| POST | `/api/tailor-runs/{run_id}/retry` | tailor_runs | 202 | Delete & retry atomically | `{ok, retry_via: "worker"|"user", ...}` | Soft-delete, optionally re-enqueue + BackgroundTask |
| **APPLY RUNS** |
| POST | `/api/jobs/{job_hash}/apply` | apply_runs | 200 | Enqueue user-triggered apply | `{ok, apply_run_id, status, job_hash}` | Insert PENDING row, spawn `asyncio.create_task` immediately |
| GET | `/api/apply-runs/{run_id}` | apply_runs | 200 | Poll apply run state | `{ok, apply_run: {...}}` | SQL read, no write |
| DELETE | `/api/apply-runs/{run_id}` | apply_runs | 204 | Soft-delete apply run | (empty) | Soft-delete row only |
| **HUMAN REVIEW** |
| GET | `/api/human-review?search=&page=1&status=` | human_review | 200 | Paginated handoff queue | `{ok, page, page_size, total_items, total_pages, items}` | SQL join apply_handoffs + job_postings |
| POST | `/api/human-review/{handoff_id}/complete` | human_review | 200 | Mark handoff APPROVED | `{ok, handoff: {...}}` | Update handoff_status, reviewed_at; update job status to APPLIED |
| POST | `/api/human-review/{handoff_id}/dismiss` | human_review | 200 | Mark handoff REJECTED | `{ok, handoff: {...}}` | Update handoff_status, reviewed_at; update job status to REJECTED |
| POST | `/api/human-review/{handoff_id}/answers` | human_review | 200 | Persist deferred-question answers | `{ok, user_answers, cache_seeded}` | Write `user_answers_json` to DB, append to durable answer cache |
| POST | `/api/human-review/{handoff_id}/relaunch-apply` | human_review | 200 | Re-enqueue apply with new answers | `{ok, apply_run_id, status, job_hash}` | Insert fresh PENDING apply_runs, flip handoff to APPROVED, spawn task |
| POST | `/api/human-review/by-job/{job_hash}/relaunch-apply` | human_review | 200 | Jobs page apply-relaunch variant | `{ok, apply_run_id, status, job_hash, handoff_id}` | (same as handoff variant) |
| **FAILURES** |
| GET | `/api/failures?search=&stage=&status=&page=1` | failures | 200 | Unified failures feed | `{ok, summary: {...}, page, total_items, items}` | SQL queries across gate/tailor/review/apply tables |
| POST | `/api/failures/{failure_id}/retry` | failures | 200 | Requeue failed stage record | `{ok, failure_id, requeued}` | Stage-specific state reset (gate: `reset_agent_failure_state`, etc.) |
| **DASHBOARD & COSTS** |
| GET | `/api/dashboard/stats` | dashboard | 200 | KPI cards + funnel + source breakdown | `{ok, jobs_discovered_total, ..., pipeline_funnel, applications_over_time}` | Complex SQL aggregations |
| GET | `/api/dashboard/discovery-trend?range=7d` | dashboard | 200 | Discovery trend bars | `{ok, range, points}` | SQL GROUP BY date |
| GET | `/api/costs/stats` | costs | 200 | Cost tracking KPIs | `{ok, total_spend_usd, avg_cost_per_application_usd, api_calls_today}` | SQL aggregations on cost_events |
| GET | `/api/costs/daily-trend?range=7d` | costs | 200 | Spend trend by day/month | `{ok, range, points}` | SQL GROUP BY date/month |
| GET | `/api/costs/by-stage` | costs | 200 | Current-month spend by stage | `{ok, items}` | SQL GROUP BY stage |
| **PIPELINE** |
| GET | `/api/pipeline/progress` | pipeline | 200 | SSE stream (stub) | `StreamingResponse` | Yields heartbeat frames every 30s |
| **SETTINGS: PROFILE** |
| GET | `/api/settings/profile` | settings_profile | 200 | Read candidate profile YAML | `{ok, metadata, yaml_text, ...parsed}` | File read |
| PUT | `/api/settings/profile` | settings_profile | 200 | Update profile from YAML text | `{ok, metadata, yaml_text, ...parsed}` | Backup old file, write new file, clear cache |
| PUT | `/api/settings/profile/structured` | settings_profile | 200 | Update profile from form fields | `{ok, metadata, yaml_text, ...parsed}` | Backup, write, clear cache |
| POST | `/api/settings/profile` | settings_profile | 200 | Upload profile file | `{ok, profile}` | Backup, write, clear cache |
| GET | `/api/settings/profile/download` | settings_profile | 200 | Download profile YAML | `FileResponse` | File read-only |
| **SETTINGS: RESUME** |
| GET | `/api/settings/resume` | settings_resume | 200 | Read resume.tex + contract pass + preview | `{ok, metadata, tex_text, contract_pass, manifest_preview}` | File read, validate contract |
| POST | `/api/settings/resume` | settings_resume | 200 | Upload resume.tex | `{ok, resume, manifest_preview}` | Validate contract, backup, write |
| GET | `/api/settings/resume/download` | settings_resume | 200 | Download resume.tex | `FileResponse` | File read-only |
| PUT | `/api/settings/resume` | settings_resume | 410 | (deprecated) | Error envelope | None |
| PUT | `/api/settings/resume/structured` | settings_resume | 410 | (deprecated) | Error envelope | None |
| POST | `/api/settings/resume/pdf` | settings_resume | 410 | (deprecated) | Error envelope | None |
| POST | `/api/settings/resume/tex` | settings_resume | 410 | (deprecated) | Error envelope | None |
| **SETTINGS: API KEYS** |
| GET | `/api/settings/api-keys` | settings_api_keys | 200 | List configured API key status | `{ok, keys}` | Reads from `.env` (no secrets) |
| PUT | `/api/settings/api-keys/{key_name}` | settings_api_keys | 200 | Upsert one API key | `{ok, keys}` | Write `.env` file |
| DELETE | `/api/settings/api-keys/{key_name}` | settings_api_keys | 200 | Remove one API key | `{ok, keys}` | Write `.env` file |
| POST | `/api/settings/api-keys/validate-adzuna` | settings_api_keys | 200 | Probe Adzuna credentials | `{ok}` | HTTP call to Adzuna API |
| **SETTINGS: BUDGET** |
| GET | `/api/budget` | settings_budget | 200 | Read budget settings + spend | `{ok, monthly_budget_usd, current_spend_usd, ...}` | SQL query cost_events |
| PUT | `/api/budget` | settings_budget | 200 | Update monthly budget | `{ok, ...}` | Write to system_settings table |
| **SETTINGS: FILTERS & SOURCES** |
| GET | `/api/settings/filters` | settings_filters | 200 | Read filters.yaml | `{ok, yaml_text, data, metadata}` | File read |
| PUT | `/api/settings/filters` | settings_filters | 200 | Update filters.yaml | `{ok, metadata}` | Backup, write |
| GET | `/api/settings/sources` | settings_filters | 200 | Read companies.yaml | `{ok, yaml_text, data, metadata}` | File read |
| PUT | `/api/settings/sources` | settings_filters | 200 | Update companies.yaml | `{ok, metadata}` | Backup, write |
| **SETTINGS: PROVIDER & ONBOARDING** |
| POST | `/api/settings/provider` | settings_provider | 200 | Set OpenAI BYOK key | `{ok, mode, provider}` | Write `.env` |
| GET | `/api/settings/onboarding-status` | settings_provider | 200 | Check onboarding completion | `{ok, is_complete, completed_steps, missing_steps}` | File existence checks |
| **SETTINGS: FILES METADATA** |
| GET | `/api/settings/files` | settings_files | 200 | Settings file metadata | `{ok, resume, profile}` | File stat calls |
| **SYSTEM SETTINGS** |
| GET | `/api/system-settings/automation` | system_settings | 200 | Read tailor automation mode | `{ok, tailor_mode}` | SQL read |
| PATCH | `/api/system-settings/automation` | system_settings | 200 | Update tailor automation mode | `{ok, tailor_mode}` | SQL write |

### 3.2 Status Codes Semantics

Standard HTTP codes with domain-specific error codes:

| HTTP | Error Code | Meaning | Example Endpoint |
|------|---|---|---|
| 200 | (success) | Request succeeded | Most reads/writes |
| 202 | (success) | Accepted for async processing | POST /tailor, POST /apply |
| 204 | (no content) | Success, no response body | DELETE /tailor-runs/{id} |
| 400 | `INVALID_YAML`, `MISSING_API_KEY` | Malformed request or config | PUT /filters (bad YAML) |
| 401 | `ADZUNA_AUTH_FAILED` | Authentication failed | POST /api-keys/validate-adzuna |
| 404 | `JOB_NOT_FOUND`, `FILE_NOT_FOUND`, `TAILOR_RUN_NOT_FOUND` | Resource missing | GET /tailor-runs/{missing_id} |
| 409 | `MODE_AUTONOMOUS`, `RUN_ALREADY_EXISTS`, `BUDGET_EXCEEDED`, `HANDOFF_ALREADY_RESOLVED` | Conflict (state constraint) | POST /tailor when autonomous mode ON |
| 410 | `ENDPOINT_REMOVED` | Endpoint retired | PUT /resume (YAML variant) |
| 422 | `NO_REVIEW_RUN`, `INVALID_RESUME_TEX`, `BASE_COMPILE_FAILED` | Unprocessable entity | POST /apply without review |
| 500 | `SYSTEM_ACTION_DISPATCH_FAILED`, `ANSWER_CACHE_SEED_FAILED` | Server error | POST /stop with shell error |
| 502 | `ADZUNA_UNREACHABLE`, `ADZUNA_ERROR` | External service error | POST /validate-adzuna when Adzuna down |

**409 Conflict Semantics** (key to understand):

- `MODE_AUTONOMOUS` — User clicked [Tailor] but `system_settings.tailor_mode = 'autonomous'`; buttons disabled in UI
- `RUN_ALREADY_EXISTS` — User clicked [Tailor] but a non-deleted PENDING/RUNNING tailor_runs row already exists for this job
- `BUDGET_EXCEEDED` — User clicked [Tailor/Apply] but monthly cost spend has hit the limit
- `APPLY_RUN_IN_FLIGHT` — User clicked [Apply] but a non-deleted PENDING apply_runs row exists for this job
- `AUTONOMOUS_REQUIREMENTS_NOT_MET` — User toggled autonomous ON via settings but OpenAI key / profile / resume missing
- `HANDOFF_ALREADY_RESOLVED` — User tried to complete/dismiss/relaunch a handoff marked APPROVED/REJECTED already

---

## 4. Cross-Cutting Concerns

### 4.1 Error Model

**File:** `api/errors.py`

All errors follow the deterministic shape:

```python
def _error_response(
    *, code: str, message: str, details: dict[str, object] | None = None
) -> dict[str, object]:
    return {
        "ok": False,
        "code": code,
        "message": message,
        "details": details or {},
    }
```

Raised via `_raise_api_error(status_code: int, code: str, message: str, details: dict)` which throws an `HTTPException`.

### 4.2 Database Connection Management

**File:** `api/routers/*.py`

Every router handler that touches the database follows this pattern:

```python
from api import main as _main  # late import for monkeypatch in tests

db_path = str(_main.resolve_database_path())
async with DatabaseManager(db_path) as db:
    await db.create_tables()
    await db.migrate_*_schema()  # per-endpoint needs
    # ... handler logic
```

**Why:** Late import allows tests to monkeypatch `resolve_database_path()`. Each `DatabaseManager` context opens a fresh connection (SQLite supports concurrent readers), while the supervisor maintains a single long-lived shared connection.

### 4.3 409 Conflict: Mode & Slot Constraints

#### Mode Constraint: `MODE_AUTONOMOUS`

When `system_settings.{gate|tailor|apply}_mode = 'autonomous'`:
- The dashboard UI **disables** the [Tailor] and [Apply] buttons
- If a POST reaches the endpoint despite UI disable, it rejects with 409 `MODE_AUTONOMOUS`

**File:** `api/routers/tailor_runs.py:266-276`, `api/routers/apply_runs.py` (no explicit check, rely on UI)

```python
mode = await db.get_automation_mode(TAILOR_MODE_KEY)
if mode == AUTONOMOUS_MODE:
    _raise_api_error(
        status_code=409,
        code="MODE_AUTONOMOUS",
        message="Manual tailor runs are disabled while automation mode is set to autonomous.",
    )
```

#### Slot Constraint: `RUN_ALREADY_EXISTS`

The tailor and apply workers enforce a per-job single-slot constraint: only one non-deleted PENDING/RUNNING run per job at a time.

**File:** `api/routers/tailor_runs.py:289-302`

```python
claim_result = await db.insert_user_triggered_tailor_run(job_hash=validated_hash, apply_after_completion=apply_after)
if claim_result is None:
    _raise_api_error(
        status_code=409,
        code="RUN_ALREADY_EXISTS",
        message="An active tailor run already exists for this job. Delete it before re-tailoring.",
    )
```

When a user deletes a failed run and re-enqueues, the POST handler soft-deletes the old row (removing it from the single-slot check) **within the same database transaction**, then inserts a fresh PENDING row.

### 4.4 Background Task Lifecycle

#### Tailor Background Task

**File:** `api/routers/tailor_runs.py:63-125, 306-314`

```python
async def _run_pipeline_background(
    *, db_path: str, tailor_run_id: int, job_hash: str,
    output_dir: Path, apply_after: bool = False
) -> None:
    # Opens own DatabaseManager — request's context is already closed
    async with DatabaseManager(db_path) as db:
        result = await run_tailor_review_pipeline(...)
        pipeline_succeeded = bool(getattr(result, "success", False))
    
    if apply_after and pipeline_succeeded:
        await _enqueue_apply_after_tailor(db_path=db_path, job_hash=job_hash)

# In enqueue_tailor_run:
background_tasks.add_task(
    _run_pipeline_background,
    db_path=db_path, tailor_run_id=tailor_run_id, ...
)
```

- BackgroundTask added to the request (returned 202)
- Runs **after** the HTTP response is sent
- Opens its own `DatabaseManager` because request's is closed
- On success with `apply_after=True`, enqueues an apply run via `_enqueue_apply_after_tailor()`
  - That uses `asyncio.create_task()` to spawn the apply background task immediately (no wait for polling loop)
  - Catches `ApplyRunInFlightError` and logs it (best-effort)

#### Apply Background Task

**File:** `api/routers/apply_runs.py:48-115, 146-274`

```python
async def _spawn_user_apply_task(*, db_path: str, merged_row: dict[str, Any]) -> None:
    # Spawned with asyncio.create_task() — detached, non-blocking
    # Reads supervisor config or falls back to env
    supervisor = get_active_supervisor()
    if supervisor is not None:
        output_dir = supervisor.apply_output_dir
        cdp_url = supervisor.apply_cdp_url
    else:
        config = build_config_from_env()
        output_dir = config.apply_output_dir
        cdp_url = config.apply_cdp_url
    
    async with DatabaseManager(db_path) as db:
        await _process_apply_row(db=db, output_base_dir=output_dir, cdp_url=cdp_url, ...)

# In enqueue_apply_run:
asyncio.create_task(_spawn_user_apply_task(db_path=db_path, merged_row=merged_row))
```

- **Note:** Comment at line 256 says "Bug 4: kick the browser flow off immediately instead of waiting for the autonomous poll loop"
- Uses `asyncio.create_task()` (not `BackgroundTasks`) — task is **detached** and survives the request
- Reads supervisor config to get the apply output directory and CDP URL (same endpoint the apply loop probes)
- Reads supervisor's dry-run mode via `safe_mode_from_env()`

### 4.5 Settings Persistence & Cache Invalidation

**File:** `api/routers/settings_profile.py:72-76`

After writing profile YAML:

```python
_main._backup_settings_file(profile_path, file_label="Profile")
profile_path.parent.mkdir(parents=True, exist_ok=True)
profile_path.write_text(payload.yaml_text, encoding="utf-8")
load_candidate_context.cache_clear()  # Clear LLM prompt cache
```

Settings changes are **durable** (written to disk immediately). The gate worker re-reads settings files on each poll cycle, and the supervisor re-reads automation modes each time the mode-changed event fires.

### 4.6 Soft-Delete and Audit Trail

**File:** `api/routers/tailor_runs.py:451-492`, `api/routers/apply_runs.py:310-359`

Tailor and apply runs are soft-deleted (row remains with `deleted_at IS NOT NULL`):

```python
await db.soft_delete_tailor_run(run_id)
_cleanup_tailor_artifacts(run_id, row)  # Best-effort file cleanup
```

- Query filters active runs with `WHERE deleted_at IS NULL` or `WHERE tr.deleted_at IS NULL`
- Single-slot constraint only counts non-deleted rows
- Soft-delete **frees the per-job slot** without losing audit history

---

## 5. Background-Task Triggers & Worker Loop Integration

### 5.1 How Dashboard Buttons Interact with Worker Loops

The system has **two paths** for running each stage:

1. **Autonomous loops** (supervisor-owned)
   - Run continuously when `automation_mode = 'autonomous'` or `'both'`
   - Poll the database for PENDING/READY work every ~30s (tunable per stage)
   - Called from `api/services/supervisor.py` factories

2. **User-triggered tasks** (dashboard buttons)
   - `POST /jobs/{hash}/tailor` spawns a BackgroundTask
   - `POST /jobs/{hash}/apply` spawns an `asyncio.create_task()` (not BackgroundTask)
   - **Do not bypass** the worker loops; they insert DB rows and let the supervisor/background task claim them

### 5.2 Tailor Pipeline Trigger

**File:** `api/routers/tailor_runs.py:219-321`

```python
@router.post("/jobs/{job_hash}/tailor", status_code=202)
async def enqueue_tailor_run(job_hash: str, background_tasks: BackgroundTasks, ...) -> dict:
    # Validate mode: reject if AUTONOMOUS
    mode = await db.get_automation_mode(TAILOR_MODE_KEY)
    if mode == AUTONOMOUS_MODE:
        _raise_api_error(status_code=409, code="MODE_AUTONOMOUS", ...)
    
    # Check budget
    if not await check_budget_before_claim(db=db, stage=PIPELINE_STAGE_TAILOR):
        _raise_api_error(status_code=409, code="BUDGET_EXCEEDED", ...)
    
    # Insert PENDING row (claim the per-job slot)
    claim_result = await db.insert_user_triggered_tailor_run(
        job_hash=validated_hash,
        apply_after_completion=apply_after,
    )
    if claim_result is None:
        _raise_api_error(status_code=409, code="RUN_ALREADY_EXISTS", ...)
    
    tailor_run_id = claim_result["id"]
    
    # Enqueue BackgroundTask
    background_tasks.add_task(
        _run_pipeline_background,
        db_path=db_path,
        tailor_run_id=tailor_run_id,
        job_hash=validated_hash,
        output_dir=TAILORED_RESUME_DIR / validated_hash,
        apply_after=apply_after,
    )
    
    return {
        "ok": True,
        "tailor_run_id": tailor_run_id,
        "status": "PENDING",
        "job_hash": validated_hash,
    }
```

**Flow:**
1. User clicks [Tailor resume] in JobsPage
2. POST /tailor inserts PENDING tailor_runs row
3. BackgroundTask runs after HTTP 202 response
4. BackgroundTask executes the full tailor pipeline (gate → tailor → review)
5. If `apply_after=True` and pipeline succeeds, enqueue apply run (best-effort)

**Interaction with supervisor:**
- The supervisor's tailor loop also polls for PENDING rows
- Both paths (user-triggered BackgroundTask and autonomous loop) can try to claim the same job
- **Resolution:** Whichever claims it first updates the `claimed_at` timestamp; the other skips (worker framework handles this)

### 5.3 Apply Pipeline Trigger

**File:** `api/routers/apply_runs.py:146-274`

```python
@router.post("/jobs/{job_hash}/apply", status_code=200)
async def enqueue_apply_run(job_hash: str, body: Optional[EnqueueApplyRunBody] = Body(None)) -> dict:
    resume_mode = (body or EnqueueApplyRunBody()).resume_mode
    
    if resume_mode == "base":
        # Compile base resume on demand
        base_pdf_path = await compile_base_resume_pdf(tex_path=SETTINGS_RESUME_PATH)
        merged_row = await db.enqueue_apply_run_with_base_resume(
            job_hash=validated_hash,
            base_pdf_path=str(base_pdf_path),
        )
    else:
        # Default: require a SUCCESS review run
        merged_row = await db.enqueue_apply_run_for_job(job_hash=validated_hash)
    
    # Bug 4: kick off immediately instead of waiting for loop
    asyncio.create_task(_spawn_user_apply_task(db_path=db_path, merged_row=merged_row))
    
    return {
        "ok": True,
        "run_id": run_id,
        "apply_run_id": run_id,
        "status": status,
        "job_hash": validated_hash,
    }
```

**Key differences from tailor:**
- **Does NOT use `BackgroundTasks.add_task()`** — uses `asyncio.create_task()` directly
- Returns 200 (not 202) immediately after spawning the task
- Task is **detached** and can outlive the request lifetime
- Does not wait for the autonomous loop; kicks the browser off immediately

**Resume modes:**
- `resume_mode='tailored'` (default): Requires a SUCCESS review_runs row; fails 422 `NO_REVIEW_RUN` otherwise
- `resume_mode='base'`: Compiles the user's base resume on demand, synthesizes tailor + review rows, applies against base PDF; fails 422 on compile error

---

## 6. Settings Endpoints & Worker Loop Integration

### 6.1 Automation Mode Settings

**File:** `api/routers/system_settings.py`

```python
@router.get("/automation")
async def get_automation_settings() -> dict[str, object]:
    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        tailor_mode = await db.get_automation_mode(TAILOR_MODE_KEY)
    return {"ok": True, "tailor_mode": tailor_mode}

@router.patch("/automation")
async def patch_automation_settings(payload: AutomationModePatch) -> dict[str, object]:
    # ... update DB ...
    # (no explicit supervisor notification here; global autonomous toggle handles it)
```

**Autonomous Toggle** (`status_router`):

**File:** `api/routers/status.py:293-383`

```python
@router.post("/settings/autonomous-mode", response_model=AutonomousModeResponse)
async def set_autonomous_mode(payload: AutonomousModePatch) -> AutonomousModeResponse:
    if payload.enabled:
        requirements = _build_requirements()
        missing = [item.name for item in requirements if not item.satisfied]
        if missing:
            _raise_api_error(status_code=409, code="AUTONOMOUS_REQUIREMENTS_NOT_MET", ...)
    
    target_mode = _AUTONOMOUS_ON_MODE if payload.enabled else _AUTONOMOUS_OFF_MODE
    # _AUTONOMOUS_ON_MODE = "both"
    # _AUTONOMOUS_OFF_MODE = "opt_in"
    
    async with DatabaseManager(db_path) as db:
        for stage_key in (GATE_MODE_KEY, TAILOR_MODE_KEY, APPLY_MODE_KEY):
            await db.set_automation_mode(stage_key, target_mode)
        enabled = await _read_global_autonomous_state(db)
    
    supervisor = get_active_supervisor()
    if supervisor is not None:
        supervisor.notify_mode_changed()  # Wakes mode watcher
    
    return AutonomousModeResponse(enabled=enabled)
```

**Hard Requirements** (gated toggle):

1. **OPENAI_API_KEY configured** — Checked at `api/routers/status.py:44-60`; rejects placeholder values from `.env.example`
2. **candidate_profile.yaml exists** — File existence check
3. **resume.tex passes contract** — Calls `validate_resume_tex()` with `run_compile_check=False`

When toggling ON, the endpoint re-validates every requirement server-side (the UI's disabled state cannot be bypassed by out-of-band POST).

### 6.2 Per-Stage Automation Modes

The system has three per-stage rows in `system_settings`:

| Key | Description |
|-----|---|
| `gate_mode` | Gate (job qualification) |
| `tailor_mode` | Tailor (resume personalization) |
| `apply_mode` | Apply (browser-based application) |

Valid values: `'autonomous'`, `'both'`, `'opt_in'`

- `'autonomous'` — Loop runs only; dashboard buttons disabled
- `'both'` — Loop runs AND dashboard buttons enabled
- `'opt_in'` — Loop paused; dashboard buttons enabled

The global autonomous toggle flips **all three** between `'both'` (ON) and `'opt_in'` (OFF).

### 6.3 Worker Loop Re-Read Semantics

**File:** `api/services/supervisor.py:461-488`

The mode watcher polls the database continuously:

```python
async def _mode_watcher_factory(self) -> None:
    while True:
        try:
            await asyncio.wait_for(
                self._mode_changed.wait(),
                timeout=MODE_WATCH_POLL_SECONDS,  # 30s
            )
            self._mode_changed.clear()
        except asyncio.TimeoutError:
            pass
        # Reconcile gated loops (start or cancel based on new modes)
        await self._reconcile_gated_loops()
        await asyncio.sleep(_MODE_WATCH_EVENT_TIMEOUT_SECONDS)  # 1.5s
```

When the autonomous toggle is flipped:
1. Router calls `supervisor.notify_mode_changed()` (sets event)
2. Mode watcher wakes **within ~1.5s** (event timeout)
3. Reconciles loops: starts gate/tailor/apply loops if mode is `'autonomous'` or `'both'`; cancels if `'opt_in'`
4. Falls back to periodic 30s poll for external mutations (SQL/CLI edits)

---

## 7. Schemas & Services Layout

### 7.1 Schemas

**File:** `api/schemas/`

| Module | Contents |
|--------|----------|
| `common.py` | Cross-cutting Pydantic models: `ReviewerActionRequest`, `BudgetUpdateRequest`, `YamlTextUpdateRequest`, `ApiKeyUpsertRequest`, `AdzunaValidateRequest`, `JobImportRequest` |
| `candidate.py` | Profile-specific models: `ProfileStructuredUpdateRequest` (guided form fields) |

### 7.2 Services

**File:** `api/services/`

| Module | Purpose |
|--------|---------|
| `migrations.py` | Startup DB migrations + FastAPI lifespan hook |
| `supervisor.py` | In-process asyncio loop manager; re-reads modes, coordinates loops |
| `env_keys.py` | Read/write/build responses for API keys in `.env` |
| `tailored_resume.py` | Resolve tailored resume PDF paths, validate job hashes |
| `yaml_files.py` | Generic YAML file read/write/backup/metadata |
| `sources.py` | Job source label mapping (Adzuna → "Adzuna", etc.) |
| `salary.py` | Parse gate results, salary display, deferred-field extraction |
| `failure_records.py` | Collect failures across all stages for the failures page |
| `answer_cache_seeding.py` | Persist human-review answers to the finisher's durable cache |
| `system_scripts.py` | Dispatch shell scripts (stop/restart/fetch-jobs) |

---

## 8. Status & Lifecycle Endpoints

### 8.1 Health Check

**File:** `api/routers/health.py:12-28`

```python
@router.get("/health")
async def health_check() -> dict[str, object]:
    return {
        "ok": True,
        "status": "healthy",
        "polling_seconds": DEFAULT_POLLING_SECONDS,  # 30
    }
```

Lightweight; no database access. Used by load balancers and external probes.

### 8.2 System Health

**File:** `api/routers/system.py:63-81`

```python
@router.get("/health", response_model=SystemHealthResponse)
async def system_health() -> SystemHealthResponse:
    return SystemHealthResponse(
        ok=True,
        openai_key_configured=_is_openai_key_configured(),
    )
```

Returns whether OpenAI key is set. Dashboard uses this to show a "missing key" banner.

### 8.3 Autonomous Readiness

**File:** `api/routers/status.py:251-266`

```python
@router.get("/status/autonomous-readiness", response_model=AutonomousReadinessResponse)
async def get_autonomous_readiness() -> AutonomousReadinessResponse:
    requirements = _build_requirements()
    ready = all(item.satisfied for item in requirements)
    return AutonomousReadinessResponse(ready=ready, requirements=requirements)
```

Drives the toggle's disabled state in the top bar. Each requirement is a `{name, satisfied, fix}` tuple.

### 8.4 Chrome Status

**File:** `api/routers/status.py:269-290`

```python
@router.get("/status/chrome", response_model=ChromeStatusResponse)
async def get_chrome_status(os: str | None = None) -> ChromeStatusResponse:
    cdp_url = _resolve_cdp_url()
    reachable = await check_chrome_reachable(cdp_url)
    return ChromeStatusResponse(
        reachable=reachable,
        checked_at=datetime.now(tz=timezone.utc).isoformat(),
        cdp_url=cdp_url,
        command_hint=_command_hint_for(os),
    )
```

Probes the Chrome debugging protocol endpoint. Optional `?os=mac|linux|windows` query returns appropriate launch command.

### 8.5 Pipeline Progress (SSE)

**File:** `api/routers/pipeline.py:15-44`

```python
@router.get("/progress")
async def pipeline_progress_sse() -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        yield f"data: {json.dumps({'stage': 'idle', ...})}\n\n"
        while True:
            await asyncio.sleep(30)
            yield ": heartbeat\n\n"
    
    return StreamingResponse(event_stream(), media_type="text/event-stream", ...)
```

**Stub implementation** — yields initial idle frame and heartbeats every 30s. Real implementation would poll supervisor or DB for live progress.

---

## 9. Risks & Gotchas

### 9.1 Race Condition: Autonomous Loop vs. User Button

**Risk:** Dashboard user clicks [Tailor], and the autonomous loop simultaneously tries to claim the same job.

**Mitigation:** The database layer (`insert_user_triggered_tailor_run`) enforces per-job single-slot constraint. Whichever claims first wins; the other's insert returns `None` and the caller raises 409 `RUN_ALREADY_EXISTS`.

**Gotcha:** If the user deletes a failed run and re-enqueues within the same request, the delete and re-insert must happen in the same DB transaction to avoid a race.

### 9.2 409 Conflict Semantics Are Mode-Dependent

**Risk:** User toggles autonomous OFF (mode → `'opt_in'`), but the tailor endpoint still rejects with 409 if `mode == AUTONOMOUS_MODE`.

**This is NOT a risk** — the endpoint checks `mode == 'autonomous'` specifically. Values `'both'` and `'opt_in'` both allow buttons.

### 9.3 Soft-Delete Audit Trail Can Confuse Slot Counting

**Risk:** Dashboard shows "tailor in progress" but the row is soft-deleted; user clicks [Tailor] again and gets 409 `RUN_ALREADY_EXISTS`.

**This is intentional** — soft-delete frees the per-job slot immediately. If a row is still soft-deleted (not yet garbage-collected), it should not block new runs. However, queries **do** filter `WHERE deleted_at IS NULL`, so a soft-deleted row is invisible and the slot is free.

**If you see 409 after deletion:** The new run was inserted, but before you can click again, the same row is still being processed somewhere. Query the DB to confirm `deleted_at IS NULL`.

### 9.4 Background Task Error Handling

**Risk:** Tailor BackgroundTask crashes, but the HTTP response was already 202.

**Mitigation:** `_run_pipeline_background` catches all exceptions and logs them. Errors are **not** reflected in the response; the dashboard must poll `GET /tailor-runs/{id}` to see the failure.

**Gotcha:** If the task crashes before writing failure state to the DB, the run hangs in PENDING forever. Monitor logs.

### 9.5 Localhost-Only Resume Download Token

**File:** `api/routers/jobs.py:342-384`

```python
@router.get("/{job_hash}/resume")
async def download_tailored_resume(job_hash: str) -> FileResponse:
    # No auth check. App is single-user local deployment.
    validated_hash = _validate_job_hash(job_hash)
    resume_pdf_path = await _resolve_latest_tailored_resume_pdf_path(validated_hash)
    return FileResponse(resume_pdf_path, media_type="application/pdf", ...)
```

**Risk:** No authentication or token validation on PDF download.

**Justification:** The codebase is a single-user local deployment. Operators who want real auth must place a reverse proxy in front. The endpoint does not impose a gate; security is the operator's responsibility.

### 9.6 Budget Check Races with Accept

**Risk:** User clicks [Apply], budget check passes, but by the time the apply row is inserted, another apply has drained the remaining budget.

**Mitigation:** Budget check is advisory only (soft constraint). The cost-tracking layer records spend after the fact. No hard rejection of applies once inserted.

### 9.7 Settings File Backup Rotation

**File:** `api/config.py:49`

```python
SETTINGS_BACKUP_FILE_LIMIT = 10
```

Only the last 10 backups are kept. Older backups are removed automatically. If a user reverts to an older profile 11+ saves ago, the old version is lost.

---

## 10. Comprehensive Endpoint Flow Diagrams

### 10.1 Tailor Button → Autonomous Loop Interaction

```
Dashboard User
    |
    v [Click Tailor Resume]
POST /api/jobs/{hash}/tailor
    |
    +---> Validate mode (reject if 'autonomous')
    |
    +---> Check budget
    |
    +---> INSERT PENDING tailor_runs row [slot claimed]
    |
    +---> Return 202 {run_id, status}
    |
    +---> HTTP response sent
    |
    +---> BackgroundTask spawned (async)
    |
    v (after response)
User polls GET /tailor-runs/{id}
    |
    +---> Read tailor_runs row [may be PENDING, RUNNING, SUCCESS, FAILED]
    |
    v
(Meanwhile in supervisor)
Autonomous tailor loop polls DB
    |
    +---> See PENDING row
    |
    +---> Try to claim row (update claimed_at if null)
    |
    +---> If BackgroundTask already running, race for claim
    |
    +---> One wins; other skips this cycle
    |
    v
Pipeline executes (gate → tailor → review)
    |
    v
User sees final state (SUCCESS or FAILED)
```

### 10.2 Apply Button → Browser Flow

```
Dashboard User (or auto-apply after tailor)
    |
    v [Click Apply OR apply_after=true in tailor]
POST /api/jobs/{hash}/apply
    |
    +---> INSERT PENDING apply_runs row
    |
    +---> Spawn asyncio.create_task(_spawn_user_apply_task)
    |
    +---> Return 200 {run_id, status}
    |
    v (task is detached, runs in background)
asyncio.create_task(_spawn_user_apply_task)
    |
    +---> Open own DatabaseManager
    |
    +---> Resolve output_dir, cdp_url from supervisor (or env)
    |
    +---> Call _process_apply_row (browser automation)
    |
    +---> Update apply_runs row with outcome
    |
    v
Dashboard polls GET /apply-runs/{id}
    |
    v [sees PENDING → RUNNING → SUCCESS/FAILED]
On SUCCESS:
    |
    +---> Insert apply_handoffs row (for human review)
    |
    v [Human Review page shows new entry]
On human reviewer action:
    |
    +---> POST /human-review/{id}/complete or /dismiss
    |
    +---> Update handoff_status, job status
    |
    v
```

### 10.3 Autonomous Toggle Flow

```
Dashboard user
    |
    v [Toggle ON]
POST /api/settings/autonomous-mode {enabled: true}
    |
    +---> Validate requirements (OpenAI, profile, resume)
    |
    +---> If missing: return 409 AUTONOMOUS_REQUIREMENTS_NOT_MET
    |
    +---> Set all stages to mode='both' in system_settings
    |
    +---> supervisor.notify_mode_changed() [signal event]
    |
    v
Supervisor mode watcher (woken by event)
    |
    +---> await asyncio.wait_for(self._mode_changed.wait(), timeout=30s)
    |
    +---> Read all stage modes from DB
    |
    +---> For each gated stage:
    |         if mode in ('autonomous', 'both'): start loop
    |         else: cancel loop
    |
    v
Gate/Tailor/Apply loops now running
    |
    v [Dashboard shows "autonomous" badge]
```

---

## 11. Summary Table: All Routes by Prefix

| Prefix | Router Module | Count | Key Endpoints |
|--------|---|---|---|
| `/api/health` | health | 1 | GET /health |
| `/api/system` | system | 4 | GET /health, POST /stop, POST /restart, POST /fetch-jobs |
| `/api/status` | status | 3 | GET /autonomous-readiness, GET /chrome, POST /settings/autonomous-mode |
| `/api/settings` | status | 1 | GET /autonomous-mode |
| `/api/costs` | costs | 3 | GET /stats, GET /daily-trend, GET /by-stage |
| `/api/dashboard` | dashboard | 2 | GET /stats, GET /discovery-trend |
| `/api/jobs` | jobs | 3 | GET / (list), GET /{hash}/resume, POST /import |
| `/api/tailor-runs` | tailor_runs | 5 | POST /{hash}/tailor, GET /{id}, GET /{id}/plan, DELETE /{id}, POST /{id}/retry |
| `/api/apply-runs` | apply_runs | 3 | POST /{hash}/apply, GET /{id}, DELETE /{id} |
| `/api/human-review` | human_review | 6 | GET / (queue), POST /{id}/complete, POST /{id}/dismiss, POST /{id}/answers, POST /{id}/relaunch-apply, POST /by-job/{hash}/relaunch-apply |
| `/api/failures` | failures | 2 | GET / (list), POST /{id}/retry |
| `/api/pipeline` | pipeline | 1 | GET /progress (SSE) |
| `/api/settings` | (multiple) | 18+ | profile, resume, api-keys, filters, sources, files, provider, onboarding-status |
| `/api/budget` | settings_budget | 2 | GET /, PUT / |
| `/api/system-settings` | system_settings | 2 | GET /automation, PATCH /automation |

**Total:** ~60+ HTTP endpoints across 16 routers.

---

## 12. Key Files & Line References

| File | Purpose | Key Lines |
|------|---------|-----------|
| `api/main.py` | App bootstrap, router registration, exception handler | 62, 67-85, 88-113, 116-148 |
| `api/config.py` | Constants, paths, patterns | 16-18, 25-34, 44-45, 47-49, 86-92 |
| `api/errors.py` | Error model, raising | 18-42, 45-69 |
| `api/routers/tailor_runs.py` | Tailor lifecycle (enqueue, poll, delete, retry) | 219-321, 324-355, 451-492, 496-619 |
| `api/routers/apply_runs.py` | Apply lifecycle (enqueue, poll, delete) | 48-115, 146-274, 277-308, 310-359 |
| `api/routers/human_review.py` | Handoff queue, actions, answer persistence | 80-217, 220-327, 330-434, 551-658 |
| `api/routers/status.py` | Autonomous readiness, Chrome status, mode toggle | 251-266, 269-290, 312-333, 335-383 |
| `api/routers/jobs.py` | Job listing, resume download, manual import | 66-339, 342-384, 387-457 |
| `api/services/supervisor.py` | Loop supervisor, mode watcher, start/stop | 198-641 |
| `api/services/migrations.py` | Lifespan, startup migrations | 67-87, 89-130 |
| `api/schemas/common.py` | Cross-cutting Pydantic models | 17-98 |

---

## Conclusion

The FastAPI HTTP API is a **tightly integrated** system where:

1. **User buttons** (tailor/apply) insert DB rows and spawn background tasks to bypass polling delays
2. **Autonomous loops** (supervisor) poll the same DB rows and run continuously when enabled
3. **Race resolution** is handled by the DB layer (single-slot constraint, claimed_at timestamp)
4. **Settings changes** are durable (written to disk) and re-read by workers on each poll or mode-change event
5. **Error semantics** are stable (409 conflicts have precise meanings for mode vs. slot constraints)
6. **Soft-delete** frees slots and preserves audit history simultaneously

The API is **single-user, localhost-scoped**, and relies on the operator to add reverse-proxy auth if needed. The supervisor's **mode watcher** ensures that autonomous toggle flips take effect within ~1-2 seconds, making the UI feel responsive.

