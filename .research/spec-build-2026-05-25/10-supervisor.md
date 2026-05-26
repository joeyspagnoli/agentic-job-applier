# In-Process Asyncio Supervisor Architecture

## 1. Purpose

The agentic-job-applier runs as a **single-container service** (issue #61 in docker-compose.yml:2) where the FastAPI API server, React dashboard, and all four pipeline worker loops coexist in one process. The In-Process Asyncio Supervisor (`api/services/supervisor.py:LoopSupervisor`) owns the lifecycle of these worker loops, replacing a separate worker-container architecture.

This unified design:
- Eliminates container orchestration complexity for worker scaling (each stage runs 0-1 concurrent task per process).
- Unifies the database connection across all loops, reducing file-lock contention vs. per-process SQLite connections.
- Allows the dashboard's autonomous toggle to immediately control loop execution via mode-change notifications rather than pod restarts.
- Requires discovery to always run (no LLM spend), while gate/tailor/apply loops respond to per-stage automation modes read on every poll cycle.

## 2. Lifespan Composition

### 2.1 Startup Sequence

```mermaid
sequenceDiagram
    participant uvicorn as uvicorn (main thread)
    participant lifespan as _lifespan()
    participant migrations as _run_startup_migrations()
    participant supervisor as start_supervisor()
    participant loopsupervisor as LoopSupervisor
    participant discovery_loop as discovery_loop
    participant mode_watcher as mode_watcher
    participant gated_loops as gate/tailor/apply

    uvicorn->>lifespan: FastAPI startup hook
    lifespan->>lifespan: _validate_candidate_profile_on_startup()
    lifespan->>migrations: Create all tables & run migrations
    migrations->>migrations: create_tables(), migrate_agent_schema(),<br/>migrate_tailor_schema(), migrate_review_schema(),<br/>migrate_apply_schema(), migrate_cost_schema()
    migrations-->>lifespan: All schemas ready
    lifespan->>supervisor: start_supervisor()
    supervisor->>loopsupervisor: LoopSupervisor(db, config)
    supervisor->>loopsupervisor: supervisor.start()
    loopsupervisor->>loopsupervisor: _spawn("discovery", _discovery_factory)
    loopsupervisor->>discovery_loop: run_discovery_loop(interval_minutes=30)
    discovery_loop-->>loopsupervisor: Running unconditionally
    loopsupervisor->>loopsupervisor: _reconcile_gated_loops()
    loopsupervisor->>loopsupervisor: Read all 3 automation modes from DB
    loopsupervisor->>gated_loops: Start gate/tailor/apply if mode in<br/>{autonomous, both}
    loopsupervisor->>loopsupervisor: _spawn("mode_watcher", _mode_watcher_factory)
    loopsupervisor->>mode_watcher: Poll modes every 30s,<br/>react to notify_mode_changed() < 2s
    mode_watcher-->>loopsupervisor: Watching
    supervisor-->>lifespan: _active_supervisor & _active_db set
    lifespan-->>uvicorn: Yield control; serve requests
```

**Code evidence:**
- `api/main.py:62` — `app = FastAPI(lifespan=_lifespan)`
- `api/services/migrations.py:89-113` — `_lifespan()` calls `_run_startup_migrations()` then `start_supervisor()`
- `api/services/migrations.py:24-65` — `_validate_candidate_profile_on_startup()` at line 107
- `api/services/supervisor.py:566-601` — `start_supervisor()` creates `LoopSupervisor(db, config)` and calls `supervisor.start()`
- `api/services/supervisor.py:276-299` — `LoopSupervisor.start()` spawns discovery, reconciles gated loops, spawns mode_watcher

### 2.2 Shutdown Sequence

When Docker sends SIGTERM (or user presses Ctrl+C), FastAPI's lifespan context exits:

```python
# api/services/migrations.py:110-113
try:
    yield  # Server handles requests here
finally:
    await stop_supervisor()  # SIGTERM/shutdown reaches here
```

`stop_supervisor()` at `api/services/supervisor.py:604-626`:
1. Sets `_stopped = True` and `_active_supervisor = None` (prevents restart logic)
2. Cancels all tasks via `task.cancel()` (graceful asyncio cancellation)
3. Awaits all tasks with `return_exceptions=True` (waits for cancellation handlers)
4. Closes the shared DB connection via `db.__aexit__()` (releases SQLite lock)

Each loop catches `asyncio.CancelledError` and re-raises it cleanly:
- `scripts/process_new_jobs.py:460-461` — gate loop
- `scripts/process_qualified_jobs.py:409-410` — tailor loop
- `scripts/process_apply_jobs.py:902-903` — apply loop
- `main.py:82-83` — discovery loop

**Gotcha:** Mid-flight LLM calls (Claude API via litellm) are not interrupted by task cancellation. They complete and return, then the loop re-checks for cancellation and exits. Mid-flight browser sessions in the apply loop are similarly not force-closed; the Playwright context cleanup runs in the finally block.

## 3. Per-Loop Entry Points & Configuration

All four loops run as `asyncio.Task` instances created by `LoopSupervisor._spawn()`. They receive configuration through `SupervisorConfig`, built once at startup and immutable:

### 3.1 Discovery Loop

**Entry point:** `main.py:58-86` → `run_discovery_loop()`

**Supervisor wiring:** `api/services/supervisor.py:490-504` → `_discovery_factory()`

**Parameters:**
- `interval_minutes` — defaults to 30; overridable via `RUN_INTERVAL_MINUTES` env var (resolved in `build_config_from_env()` at supervisor.py:164-167)
- Always runs; never gated on automation mode
- No LLM calls, no user input required

**Behavior:**
```python
while True:
    try:
        await run_job_discovery()  # Fetch jobs from all sources, deduplicate, insert
    except asyncio.CancelledError:
        raise  # Clean exit
    except Exception as exc:
        logger.exception("Discovery cycle failed: {}", exc)  # Log and continue
    await asyncio.sleep(interval_seconds)
```

### 3.2 Gate Loop (Process NEW Jobs)

**Entry point:** `scripts/process_new_jobs.py:410-466` → `run_gate_loop()`

**Supervisor wiring:** `api/services/supervisor.py:506-519` → `_gate_factory()`

**Parameters from env (supervisor.py uses defaults):**
- `poll_interval_seconds` = 60 (env: `AGENT_POLL_INTERVAL_SECONDS`)
- `limit` = 25 (env: `AGENT_BATCH_LIMIT` or `AGENT_BATCH_SIZE`)
- `max_retries` = 3 (env: `AGENT_MAX_RETRIES`)
- `backoff_seconds` = 300 (env: `AGENT_RETRY_BACKOFF_SECONDS`)
- `backoff_multiplier` = 3 (env: `AGENT_RETRY_BACKOFF_MULTIPLIER`)

**Behavior:**
```python
while True:
    try:
        if await _is_gate_mode_active(db):  # Read automation.gate_mode each cycle
            processed = await _process_once(db, limit, provider, max_retries, ...)
            logger.info("Gate batch complete: processed={}", processed)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Gate polling cycle failed: {}", exc)
    await asyncio.sleep(poll_interval_seconds)
```

**Mode gating:** `scripts/process_new_jobs.py:349-370` → `_is_gate_mode_active()`
- Reads `automation.gate_mode` from DB
- Returns `True` for `{autonomous, both}`
- Returns `False` for `opt_in` (logs debug message, skips batch)
- Returns `False` for unknown values (logs warning, treats as opt_in)

### 3.3 Tailor Loop (Process QUALIFIED Jobs)

**Entry point:** `scripts/process_qualified_jobs.py:362-416` → `run_tailor_loop()`

**Supervisor wiring:** `api/services/supervisor.py:521-540` → `_tailor_factory()`

**Parameters from env:**
- `poll_interval_seconds` = 30 (env: `TAILOR_POLL_INTERVAL_SECONDS`)
- `max_retries` = 2 (env: `TAILOR_MAX_RETRIES`)
- `lease_seconds` = 7200 (env: `TAILOR_CLAIM_LEASE_SECONDS`; used both for claim TTL and stale-run threshold)
- `output_base_dir` — resolved to `data/tailored_resumes` by default (env: `TAILOR_OUTPUT_DIR`)
- `resume_tex_path` — resolved to `config/resume.tex` (env: `TAILOR_RESUME_TEX_PATH`)
- `candidate_profile_yaml_path` — resolved to `config/candidate_profile.yaml` (env: `CANDIDATE_PROFILE_YAML_PATH`)

**Behavior per cycle:** `scripts/process_qualified_jobs.py:279-325` → `_run_one_cycle()`
1. Always sweep stale PENDING runs: `mark_stale_tailor_runs_failed(lease_seconds=7200)` (runs every cycle, regardless of mode)
2. Read `automation.tailor_mode` from DB
3. If mode is `opt_in`, return 0 (idle)
4. If mode is `{autonomous, both}`, claim one QUALIFIED job and run the tailor pipeline
5. Pipeline persists `tailor_runs` rows and `review_runs` rows atomically

**Mode gating:** `scripts/process_qualified_jobs.py:309-315`
- Same pattern as gate loop

### 3.4 Apply Loop (Process REVIEWED Jobs)

**Entry point:** `scripts/process_apply_jobs.py:826-907` → `run_apply_loop()`

**Supervisor wiring:** `api/services/supervisor.py:542-559` → `_apply_factory()`

**Parameters from env:**
- `poll_interval_seconds` = 60 (env: `APPLY_POLL_INTERVAL_SECONDS`)
- `max_retries` = 2 (env: `APPLY_MAX_RETRIES`)
- `lease_seconds` = 1800 (env: `APPLY_CLAIM_LEASE_SECONDS`; browser ops are slower than agent cycles)
- `backoff_seconds` = 1800 (env: `APPLY_RETRY_BACKOFF_SECONDS`)
- `backoff_multiplier` = 2 (env: `APPLY_RETRY_BACKOFF_MULTIPLIER`)
- `output_base_dir` — resolved to `data/apply_runs` (env: `APPLY_OUTPUT_DIR`)
- `cdp_url` — resolved to `http://host.docker.internal:9222` (env: `CHROME_CDP_URL`; docker-compose.yml:34 defaults it on startup)
- `dry_run` — resolved from `SAFE_MODE=true` env var (defaults to `True` for safety; auto-submit is disabled in current release)

**Behavior per cycle:**
```python
while True:
    try:
        if not await _is_apply_mode_active(db):
            await asyncio.sleep(poll_interval_seconds)
            continue
        chrome_reachable = await check_chrome_reachable(cdp_url)
        if not chrome_reachable:
            logger.debug("Chrome unreachable; sleeping without claim")
            await asyncio.sleep(poll_interval_seconds)
            continue
        processed = await _apply_once(db, output_dir, cdp_url, max_retries, lease, ...)
        if processed == 0:
            await asyncio.sleep(poll_interval_seconds)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Apply polling cycle failed: {}", exc)
        await asyncio.sleep(poll_interval_seconds)
```

**Mode gating:** `scripts/process_apply_jobs.py:803-823`
- Same pattern as gate/tailor
- **Extra guard:** Chrome reachability check (`check_chrome_reachable(cdp_url)`)
  - If Chrome is not reachable, loop sleeps without claiming (prevents FAILED rows when browser is down)

**Safe-mode behavior:** `scripts/process_apply_jobs.py:864-865`
- `dry_run = safe_mode_from_env()` if not explicitly passed
- When `dry_run=True`, forms are filled but never submitted (forwarded to `apply_to_job()` in line 661)
- Default is `True` per `src/agents/apply_worker/finisher_integration.py`

## 4. Mode Gating & Race Conditions

### 4.1 Per-Stage Automation Modes

Stored in `system_settings` table (key/value pairs):
- `automation.gate_mode` (GATE_MODE_KEY)
- `automation.tailor_mode` (TAILOR_MODE_KEY)
- `automation.apply_mode` (APPLY_MODE_KEY)

Valid values: `{autonomous, opt_in, both}`
- `autonomous` — loop claims and processes jobs
- `opt_in` — loop idles; only user-triggered actions via API buttons
- `both` — loop claims + user buttons both active (not currently used, reserved for future)

Default on first boot: `opt_in` (safe default; user explicitly enables automation)

**Seeding from environment:**
`api/services/supervisor.py:566-601` → `start_supervisor()` calls `db.seed_automation_defaults_from_env()`:
- Reads `GATE_MODE`, `TAILOR_MODE`, `APPLY_MODE` env vars
- Applies only to unset rows (one-time seed, does not override existing DB values on restart)
- Uses `_normalize_mode_or_none()` to reject invalid values

### 4.2 Mode Polling & Change Notification

**Supervisor watcher loop:** `api/services/supervisor.py:461-488` → `_mode_watcher_factory()`

```python
while True:
    try:
        await asyncio.wait_for(
            self._mode_changed.wait(),  # Wait for explicit notify_mode_changed() signal
            timeout=MODE_WATCH_POLL_SECONDS,  # 30s safety-net poll
        )
        self._mode_changed.clear()
    except asyncio.TimeoutError:
        pass  # Timeout is normal; fall through to reconcile
    
    await self._reconcile_gated_loops()  # Read DB, start/cancel tasks
    await asyncio.sleep(_MODE_WATCH_EVENT_TIMEOUT_SECONDS)  # 1.5s
```

**Each worker loop:** Reads automation mode on every poll cycle (not at startup)
- `scripts/process_new_jobs.py:449-459` — gate loop reads `_is_gate_mode_active()` before `_process_once()`
- `scripts/process_qualified_jobs.py:400-408` — tailor loop reads mode in `_run_one_cycle()` before claim
- `scripts/process_apply_jobs.py:877-890` — apply loop reads mode before claim

### 4.3 Race Between Dashboard Toggle and Loop Poll

**Scenario:** User clicks autonomous toggle while gate loop is mid-batch.

1. User clicks toggle in dashboard → `PATCH /api/system-settings/automation` (api/routers/system_settings.py)
2. Router writes new mode to DB, calls `supervisor.notify_mode_changed()`
3. `notify_mode_changed()` sets the asyncio.Event (wakes the mode_watcher)
4. Mode watcher reads updated modes, calls `_reconcile_gated_loops()`
5. If mode changed to `opt_in`, watcher calls `_cancel_task("gate")`, which:
   - Removes "gate" from `_tasks` dict
   - Calls `task.cancel()` on the gate task
   - Awaits the task (blocks until cancellation is acknowledged)
6. Meanwhile, gate loop at the top of its while loop checks `_is_gate_mode_active()`:
   - If watcher has already written new mode to DB, `_is_gate_mode_active()` returns `False`
   - Gate loop logs debug message and skips batch
   - On next iteration, if watcher sent CancelledError, it's caught and re-raised, exiting cleanly
   - If no CancelledError yet (race), loop just idles

**Timing windows:**
- Toggle → mode_watcher reconciliation: < 2 seconds (uses asyncio.wait_for timeout of 1.5s)
- Next loop poll cycle: typically 30-60 seconds (POLL_INTERVAL_SECONDS)
- Race: If toggle happens 1s before gate loop's mode check, the loop sees the new mode and idles gracefully

**Gotcha:** A batch mid-flight when mode changes to `opt_in`:
- Already-claimed jobs continue processing (claim is atomic; mode check is only on new cycles)
- Worker finishes the batch, then idles until next mode change
- This is acceptable (one batch of processing is small)

## 5. Race-Safe Claim Semantics

All claims use **atomic database transactions** with `BEGIN IMMEDIATE` to ensure no double-claiming across workers:

### 5.1 Claim Transaction Structure

**Gate jobs:** Database lookup → claim (worker batches up to 25 at once; no explicit claim row)

**Tailor jobs:** `src/database/_mixins/tailor.py` → `claim_next_tailor_job()`
- Reads one QUALIFIED job that is not marked FILTERED, QUALIFIED_PASSED, etc.
- Inserts a PENDING `tailor_runs` row in one transaction
- Returns job merged with `_tailor_run_id` (the inserted row ID) and `_claim_token` (random hex string)
- If a second worker tries to claim the same job in parallel, INSERT fails with constraint violation or row is already locked
- Lease timeout: `next_retry_at = now + lease_seconds` (default 7200s = 2 hours)

**Apply jobs:** `src/database/_mixins/apply.py` → `claim_next_apply_job()`
- Reads one SUCCESS `review_runs` row not yet applied
- Inserts a PENDING `apply_runs` row with `claim_token` (random hex)
- Lease timeout: 1800s = 30 minutes (browser ops are slower)
- Returns merged row with `_apply_run_id`, `_apply_claim_token`, job metadata

### 5.2 Stale-Run Sweeps

**Tailor loop:** Every cycle, unconditionally:
```python
stale_count = await db.mark_stale_tailor_runs_failed(lease_seconds=lease_seconds)
# Converts any PENDING run where `started_at + 7200s < now` to FAILED status
```

**Apply loop:** On startup and every cycle:
```python
stale_count = await db.mark_stale_apply_runs_failed(lease_seconds=lease_seconds)
# Converts any PENDING run where `started_at + 1800s < now` to FAILED status
```

**Purpose:** Reapers for crashed or stuck workers. If a process dies mid-apply without releasing its claim, the lease timer resets the run to FAILED after 30 minutes, allowing the next restart to claim and retry.

### 5.3 ClaimOwnershipError on Concurrent Writes

When a worker tries to update a `tailor_runs` or `apply_runs` row it no longer owns:

```python
try:
    await db.record_apply_success(run_id, claim_token, ...)
except ClaimOwnershipError as exc:
    logger.warning("Skipping stale apply success write for run_id={}: {}", run_id, exc)
    return 1  # Do not crash; log and move on
```

**Trigger:** Row was already completed by another process (e.g., restart happened, new worker claimed same job and finished it first).

**Handling:** Best-effort logging; no side effects. The latest write to the database wins.

### 5.4 Parallel Container Restarts

**Scenario:** Docker container restarts while a tailor run is PENDING.

1. Old process dies; asyncio task is forcefully killed (no graceful exit)
2. PENDING `tailor_runs` row is now orphaned
3. New process starts, supervisor calls `mark_stale_tailor_runs_failed(lease_seconds=7200)`
4. Stale sweep finds the row (started > 2 hours ago), marks it FAILED
5. Next claim reads FAILED row, skips it (max_retries exceeded)
6. No double-processing

**Improvement:** If the lease is 7200s but the container restarts in 30s, the PENDING row blocks the job for 2 hours. Operators can manually mark it FAILED in the dashboard or run SQL to reset it.

## 6. Cancellation & Graceful Shutdown

### 6.1 Signal Flow

```
SIGTERM (from docker compose down)
  ↓
uvicorn receives SIGTERM
  ↓
uvicorn calls lifespan.__aexit__()
  ↓
finally block at api/services/migrations.py:112 → await stop_supervisor()
  ↓
LoopSupervisor.stop() at supervisor.py:301-318:
  1. Set _stopped = True
  2. Loop through _tasks.values() and call task.cancel()
  3. await asyncio.gather(*_tasks.values(), return_exceptions=True)
  ↓
Each task's asyncio.CancelledError is caught:
  - Gate: scripts/process_new_jobs.py:460-461
  - Tailor: scripts/process_qualified_jobs.py:409-410
  - Apply: scripts/process_apply_jobs.py:902-903
  - Discovery: main.py:82-83
  ↓
Task exits cleanly; CancelledError is re-raised and swallowed by gather()
```

### 6.2 Mid-Flight LLM Call Behavior

When a gate or tailor worker is processing a job and `CancelledError` arrives:

1. If LLM call is in flight (litellm waiting for Claude API response):
   - Task cancellation does NOT interrupt the HTTP request (litellm + aiohttp handle that separately)
   - LLM call completes and returns (or times out after ~60s)
   - Worker checks for `CancelledError` and re-raises on next `await`
   - Row status is persisted (QUALIFIED if gate succeeded, SUCCESS if tailor succeeded)

2. If worker has not yet made an LLM call:
   - `CancelledError` is caught immediately
   - Row remains in its current status (typically NEW for gate)

**Implication:** Docker `down` may take 10-30 seconds if a worker is mid-LLM-call. Uvicorn's default stop grace period is 0; set `stop_grace_period: 60s` in compose if needed.

### 6.3 Mid-Flight Browser Session Cleanup

Apply worker with Playwright:

```python
async def apply_to_job(...):
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp_url)
        # ... fill forms, take screenshots, etc.
        # If CancelledError arrives here:
        # - The async context manager's __aexit__ is called
        # - Browser connection is closed (not ungracefully killed)
        # - Screenshots/snapshots are flushed to disk
```

The async context manager ensures cleanup runs. However, if the browser connection is held open and the task is force-killed, the CDP connection is dropped without a close handshake.

**Mitigation:** The apply loop checks `check_chrome_reachable()` before claiming. If Chrome is not responsive, the loop sleeps. If Chrome crashes mid-apply, the browser context cleanup still runs (async with block), and the PENDING row is eventually reaped by stale-run sweep.

## 7. Failure-Signal Handling

### 7.1 Worker Crash with Bounded Backoff Restart

Each supervised task is wrapped by `LoopSupervisor._spawn()` (supervisor.py:418-459):

```python
async def _supervised() -> None:
    backoff_seconds = _RESTART_BACKOFF_INITIAL_SECONDS  # 5 seconds
    while not self._stopped:
        try:
            await factory()  # Run the loop
        except asyncio.CancelledError:
            raise  # Exit gracefully on shutdown
        except Exception as exc:
            logger.exception("Supervisor: {} loop crashed: {}; restarting in {}s",
                             name, exc, backoff_seconds)
            await asyncio.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, _RESTART_BACKOFF_MAX_SECONDS)  # Cap at 300s
```

**Behavior:**
- First crash: restart after 5s
- Second crash: restart after 10s
- Third crash: restart after 20s
- ... up to 300s (5 minutes)

**Why not fire immediately?**
- Prevents restart loops if the failure is transient (DB lock, API rate limit)
- Gives upstream services (DB, LLM provider) time to recover
- Logs every crash with the exception, so operators are aware

**When does restart happen?**
- Unexpected exception escapes the per-cycle try/except
- Example: Import error when loading a module, or an unhandled asyncio.Task exception
- Per-cycle exceptions are caught and logged; loops continue (e.g., gate batch fails, loop sleeps and retries)

### 7.2 Failure Signal Paths

**Gate worker terminal failure:**
- `scripts/process_new_jobs.py:300-316` — retry count exhausted
- Calls `_notify_terminal_failure()` → sends ntfy notification to operator
- Logs error and marks job as terminal-failed in DB
- Continues with next batch

**Tailor worker terminal failure:**
- `scripts/process_qualified_jobs.py:264-275` — failure count >= max_retries after pipeline completes
- Calls `_notify_terminal_failure()` → ntfy notification
- Logs warning; continues polling

**Apply worker terminal failure:**
- `scripts/process_apply_jobs.py:407-415` — current_attempt >= max_retries
- Calls `_notify_terminal_failure()` → ntfy notification
- Logs warning; continues polling

**Dashboard visibility:**
- Status router (`api/routers/status.py`) returns `supervisor.active_stages` — tuple of currently running loop names
- If a loop crashes and enters backoff, it is still in `_tasks` dict, so shows as "active" (even if sleeping)
- Dashboard polls `/api/health` every 5s; health check calls `db.get_automation_mode()` to check modes
- No real-time failure notification to dashboard; logs are the source of truth

### 7.3 Failure Surface Via Logs & NTFY

**Logs:**
- `logger.exception("Decider failed for job {} ...")` (gate retry, scripts/process_new_jobs.py:283)
- `logger.error("Decider terminal failure ...")` (gate max retries, scripts/process_new_jobs.py:301)
- `logger.warning("Tailor FAILED: ...")` (tailor failure, scripts/process_qualified_jobs.py:269)
- `logger.exception("Supervisor: {} loop crashed: ...; restarting")` (supervisor crash restart, supervisor.py:448)

**NTFY notifications (optional, requires NTFY_URL env var):**
- `await send_ntfy_notification(title="Job gate terminal failure", ...)` (gate max retries, scripts/process_new_jobs.py:166)
- `await send_ntfy_notification(title="Resume tailor terminal failure", ...)` (tailor max retries, scripts/process_qualified_jobs.py:174)
- `await send_ntfy_notification(title="Apply Worker: Terminal Failure", ...)` (apply max retries, scripts/process_apply_jobs.py:467)

**System Settings:**
- Automation modes are read every cycle; no explicit "failure" state stored
- Job status (NEW, FILTERED, QUALIFIED, etc.) is the persistent failure indicator
- Individual run rows (tailor_runs, apply_runs) carry error messages and next_retry_at timestamps

## 8. Safe-Mode Behavior

`SAFE_MODE=true` environment variable is the global kill switch for auto-submit across the apply loop.

**Applied at:** `scripts/process_apply_jobs.py:864-865` → `run_apply_loop()` defaults `dry_run` from env

```python
if dry_run is None:
    dry_run = safe_mode_from_env()
```

**Effect:**
- When `dry_run=True`, apply finisher fills all form fields but stops before submit
- Result lands as `NEEDS_REVIEW` status (apply_runs.outcome = "NEEDS_REVIEW")
- Persists `apply_handoffs` row for human review at `/human-review` endpoint
- Per-job binary gate inside `_run_application_flow()` is still evaluated; gate failure also lands as NEEDS_REVIEW

**Current release policy:**
- Default is `True` (auto-submit disabled)
- All successful apply runs are handed off to human review
- Setting `SAFE_MODE=false` enables auto-submit only after per-job gate passes (all required fields filled, Tier-2/Tier-3 rules satisfied)

## 9. Concurrency Caps

The supervisor **does not limit parallelism within a single loop**. Each loop runs 0-1 concurrent instance:

- **Discovery loop:** Runs one copy always; fetches jobs sequentially from all sources
- **Gate loop:** Runs one copy when mode permits; batches up to 25 jobs per cycle (sequential processing within batch)
- **Tailor loop:** Runs one copy when mode permits; claims and processes one job per cycle (pipeline is sequential)
- **Apply loop:** Runs one copy when mode permits; claims and processes one job per cycle (browser automation is sequential)

**Why no intra-loop parallelism?**
- SQLite is single-writer; each process holds one connection with shared `_db` object
- Browser automation (Playwright) is inherently sequential per connection
- LLM calls can be parallelized, but batch size (25 gate jobs) is kept small to avoid API rate limits
- Horizontal scaling is achieved by deploying multiple containers, not by threading within one loop

**If higher throughput is needed:** Deploy multiple app containers and shard the database (using a middleware that distributes claims across containers). This is future work.

## 10. Risks & Gotchas

### 10.1 Race: Dashboard Toggle vs. Worker Poll

**Scenario:** User disables autonomous mode while a gate worker is processing a batch.

**Risk:** Batch completes and persists QUALIFIED status even though mode is now `opt_in`.

**Why this happens:**
- Worker reads mode at the top of the loop (line 450, `_is_gate_mode_active()`)
- If mode is `autonomous` or `both`, worker claims 25 jobs
- User changes mode to `opt_in` (writes to DB, calls `notify_mode_changed()`)
- Worker completes batch; on next cycle, reads updated mode and idles
- Result: One extra batch was processed; this is acceptable and matches existing CDK behavior

**Mitigation:** Mode watcher cancels the loop immediately via `_cancel_task()`, but this only prevents future cycles. In-flight batch is still processed. Acceptable for 25 jobs.

### 10.2 Database Lock Contention

**Scenario:** Multiple loops or routers try to write to the database simultaneously.

**Risk:** SQLite serializes writes; heavy load causes lock timeouts (default 5s in many drivers).

**Mitigation:**
- Shared `DatabaseManager` connection is used by all loops (one async context manager, one connection object)
- Each loop's DB writes are wrapped in try/except and logged if they fail
- Cost telemetry writes are "best-effort" and don't crash the loop (scripts/process_apply_jobs.py:418-451)
- Stale-run sweeps use atomic transactions with `BEGIN IMMEDIATE`

**Future:** Consider async SQLite driver (aiosqlite is already in use; issue is still single-writer serialization).

### 10.3 Stale-Run Lease Timeout Too Long

**Scenario:** Worker crashes; PENDING row is orphaned.

**Current:** Lease timeout is 7200s (2 hours) for tailor, 1800s (30 minutes) for apply.

**Risk:** Job is stuck in PENDING for hours, blocking new claims.

**Mitigation:**
- Operators can manually mark the row FAILED in the dashboard or via SQL
- If frequent crashes occur, lower the lease via `TAILOR_CLAIM_LEASE_SECONDS` env var
- Monitor logs for crash-restart patterns

### 10.4 Mode Watcher Polling vs. Manual SQL Edits

**Scenario:** Operator manually updates `system_settings` row via SQL (e.g., `UPDATE system_settings SET value='autonomous' WHERE key='automation.gate_mode'`).

**Risk:** Mode watcher polls only every 30s (MODE_WATCH_POLL_SECONDS); change is not reflected until next poll.

**Mitigation:**
- Mode watcher has a safety-net 30s poll that catches out-of-band mutations
- For immediate effect, use the dashboard toggle (which calls `notify_mode_changed()` and wakes the watcher in < 2s)
- Or restart the container

### 10.5 LLM Call Timeout During Graceful Shutdown

**Scenario:** SIGTERM arrives; gate worker is mid-Claude-API-call (litellm).

**Risk:** Shutdown takes 10-30 seconds if LLM call is slow.

**Mitigation:**
- Docker healthcheck has `start_period: 60s` (docker-compose.yml:52); gives ample time
- If faster shutdown is needed, use `stop_grace_period: 30s` and accept forced kills
- LLM calls have their own timeout (model-dependent; typically 60s for Claude)

### 10.6 Chrome Reachability Check is Not Real-Time

**Scenario:** Chrome crashes after the loop checks reachability but before `apply_to_job()` tries to connect.

**Risk:** Apply run fails with browser connection error; row is FAILED and retried later.

**Mitigation:** This is acceptable; the error is logged and next_retry_at is scheduled. The apply loop resumes when Chrome comes back.

### 10.7 Test Coverage Gaps

**Tests that validate these behaviors:**
- `tests/test_agent_worker_resilience.py` — gate worker batching and error handling
- `tests/test_api_system_lifecycle.py` — lifespan startup/shutdown (limited coverage)
- `tests/test_worker_mode_gating.py` — per-stage mode gating (tailor loop)
- `tests/test_apply_loop_safe_mode.py` — SAFE_MODE env var propagation
- `tests/test_pipeline_failure_signaling.py` — failure signal flow (if exists)

**Missing test coverage:**
- LoopSupervisor restart with backoff (no unit test for crash recovery)
- Concurrent container restart (requires integration test with real DB + two processes)
- Mode watcher race conditions (requires fine-grained timing control in asyncio)
- SIGTERM graceful shutdown with mid-flight LLM call (requires live provider call or mock)

---

## Architecture Summary

The In-Process Asyncio Supervisor unifies four asynchronous worker loops (discovery, gate, tailor, apply) into a single FastAPI process controlled by a lightweight `LoopSupervisor` class. Each loop polls on a configurable interval and reads per-stage automation modes from the SQLite database on every cycle, allowing the user-facing dashboard toggle to instantly control worker behavior through `notify_mode_changed()` event signaling. Worker crashes are recovered with bounded exponential backoff (5s to 300s), and stale jobs are reaped after lease expiration. Graceful shutdown via SIGTERM cancels all tasks, allowing mid-flight LLM calls to complete before exit. The design eliminates container orchestration while maintaining safety through atomic claim transactions, race-safe mode reconciliation, and comprehensive failure logging.

