# Database Layer & Persistence Architecture

## Purpose

The database layer owns all durable state for the agentic job-applier pipeline, persisting job postings, intermediate processing stages, cost telemetry, and operational settings to a local SQLite database at `data/jobs.db`. Every stage (discovery, gate, tailor, review, apply) reads and writes exclusively through `DatabaseManager` — a composed async SQLite manager that uses Python's mixin pattern to keep concerns separated by table ownership.

**Key responsibilities:**
- **Job lifecycle management**: Insert, deduplicate, status transitions for postings (NEW → QUALIFIED → APPLIED/REJECTED)
- **Stage-specific run tracking**: Atomic claims, status machines, retry scheduling for tailor/review/apply workers
- **Concurrency safety**: Claim-and-lease semantics via `BEGIN IMMEDIATE` transactions to prevent duplicate work
- **Cost telemetry**: Forward-only event logging with per-call provider/model/token detail
- **Operator controls**: Failure resets, automation mode toggles, monthly budget enforcement

## DatabaseManager Architecture

`DatabaseManager` (src/database/db_manager.py:73-99) is a **composition-based** async manager that multiplies the interfaces of **eight mixins** via Python's MRO. Rather than inheriting a bloated base class, each mixin owns one logical table grouping and exports only the methods relevant to that concern.

**Mixin composition order** (db_manager.py:73-82):
1. `JobsMixin` — job_postings CRUD, pending-agent claim
2. `TelemetryMixin` — crawl_history, daily_stats
3. `AgentGateMixin` — agent-decision columns on job_postings
4. `TailorMixin` — tailor_runs lifecycle
5. `ReviewMixin` — review_runs lifecycle
6. `ApplyMixin` — apply_runs and apply_handoffs
7. `CostsMixin` — cost_events, budget_settings, app_settings
8. `FailureResetsMixin` — operator requeue helpers
9. `SystemSettingsMixin` — system_settings key/value store

**Connection lifecycle** (db_manager.py:101-244):

```python
async def __init__(db_path: str)
  → Stores path, initializes conn=None, sets per-stage schema_ready flags to False

async def connect() → None
  → Creates data/ directory, opens aiosqlite.Connection, applies PRAGMA busy_timeout=5000
  → Journal mode configurable via SQLITE_JOURNAL_MODE env var (default: WAL)
  → Row factory set to aiosqlite.Row for dict-like row access

async def create_tables() → None
  → Loads schema.sql, executes via executescript(), then calls per-stage migrations
  → Calls: migrate_tailor_schema(), migrate_review_schema(), migrate_system_settings_schema()
  → Finally seeds automation defaults from env vars (GATE_MODE, TAILOR_MODE, APPLY_MODE)

async with DatabaseManager(db_path) as db:
  → __aenter__ calls connect(), __aexit__ calls close()
```

**Async pattern**: All database operations are async-first using `aiosqlite` (file:db_manager.py:25). Methods use `await conn.execute()`, `await cursor.fetchall()`, and `await conn.commit()` to prevent blocking the event loop during I/O.

**Schema-ready guards** (base.py:34-41): Each mixin declares what stage schemas it manages. Cross-mixin callers (e.g., `ReviewMixin.claim_next_review_job`) call `_ensure_tailor_schema_ready()` before querying tailor_runs to guarantee backward compatibility with pre-tailor databases.

## Mixin-by-Mixin Breakdown

### JobsMixin (jobs.py:22-432)

**Owns tables**: job_postings

**Public methods**:
- `insert_job(job_data)` → bool: Insert with dedup-hash collision handling (returns False on duplicate)
- `get_job_by_hash(job_hash)` → Optional[JSONObject]
- `get_job_by_id(job_id)` → Optional[JSONObject]
- `get_resume_tailor_job_context(job_hash|job_id)` → Optional[JSONObject]: Tailored read for resume-tailor workflows
- `get_existing_job_hashes(hashes: list[str])` → set[str]: Batch dedup via chunked IN queries (900-item chunks)
- `update_job_description(job_hash, description)`
- `update_job_status(job_hash, status)`
- `get_jobs_by_status(status, limit)` → list[JSONObject]
- `get_jobs_pending_agent_processing(limit)` → list[JSONObject]: **Atomic claim** (line 299-384)
- `get_job_count()` → int
- `get_jobs_today()` → int

**State machine**: `job_postings.status` enum: NEW → FILTERED | QUALIFIED → APPLIED | REJECTED

**Concurrency (agent claim)**: (jobs.py:299-384)
```sql
BEGIN IMMEDIATE;
UPDATE job_postings SET agent_claim_token=?, agent_claimed_at=NOW()
WHERE id IN (
  SELECT id FROM job_postings
  WHERE status='NEW' AND agent_processed_at IS NULL AND agent_failed_at IS NULL
    AND (agent_next_retry_at IS NULL OR agent_next_retry_at <= NOW())
    AND (agent_claimed_at IS NULL OR agent_claimed_at <= datetime('now', '-{lease_seconds} seconds'))
  ORDER BY COALESCE(agent_next_retry_at, fetched_at), fetched_at, id
  LIMIT ?
)
RETURNING *;
COMMIT;
```
Claim tokens are 12-byte hex strings (`os.urandom(12).hex()`, jobs.py:331). Lease is configurable (default 900s = 15 min, jobs.py:19) and guarded by env var `AGENT_CLAIM_LEASE_SECONDS`. Deterministic FIFO ordering preserved after claim (jobs.py:375-383).

### TelemetryMixin (telemetry.py:14-136)

**Owns tables**: crawl_history, daily_stats

**Public methods**:
- `start_crawl(source, company)` → int: Insert with IN_PROGRESS status, return crawl_id
- `complete_crawl(crawl_id, jobs_found, jobs_new, error=None)`: Mark SUCCESS/FAILED with counts
- `update_daily_stats(date, jobs_discovered, jobs_new, jobs_duplicate, sources_crawled, sources_failed)`: Upsert with accumulation (ON CONFLICT DO UPDATE)

**No state machine**: crawl_history is fire-and-forget; daily_stats is append-only aggregation.

### AgentGateMixin (agent_gate.py:15-323)

**Owns columns on job_postings**: agent_processed_at, agent_result, agent_failed_at, agent_error, agent_retry_count, agent_next_retry_at, agent_claim_token, agent_claimed_at

**Public methods**:
- `migrate_agent_schema()`: Idempotent ALTER TABLE for missing columns (agent_gate.py:18-108). Lightweight migration pattern.
- `_ensure_agent_schema_ready()`: Guard that checks column existence before agent queries run
- `record_agent_decision(job_hash, agent_result, status)`: Atomic write of result + status, clears failure flags
- `record_agent_retry(job_hash, error, retry_count, next_retry_at)`: Exponential backoff scheduling
- `mark_job_agent_terminal_failed(job_hash, error, retry_count=None)`: Sets agent_failed_at timestamp (irreversible until operator reset)
- `update_job_agent_result(job_hash, agent_result)`: Save result without status change

**Retry policy**: No hard limit in the schema; controlled by the worker's max-retry loop. `next_retry_at` is writer-specified (exponential backoff logic lives in the agent worker, not the DB).

### TailorMixin (tailor.py:32-691)

**Owns table**: tailor_runs

**State machine**: `tailor_runs.status` enum
```
PENDING → RUNNING → SUCCESS
              ↓
            FAILED (next_retry_at governs retry eligibility)
```

**Public methods**:
- `migrate_tailor_schema()`: Creates table + idempotent ALTERs for artifact_yaml_path, deleted_at, plan_json_path, apply_after_completion (tailor.py:35-114)
- `_widen_status_check_if_needed()`: Rebuilds table if legacy CHECK lacks RUNNING state (tailor.py:117-201)
- `_ensure_tailor_schema_ready()`: Guard for backward compat (tailor.py:203-227)
- `claim_next_tailor_job(max_retries, lease_seconds)` → Optional[dict]: **Atomic claim** (tailor.py:229-340)
  - Returns merged job_postings + tailor_runs row with _tailor_run_id, _tailor_claim_token keys
  - Filters to QUALIFIED jobs without active SUCCESS/PENDING/RUNNING claims
  - Respects max_retries FAILED count ceiling
  - Checks next_retry_at eligibility
- `mark_tailor_running(run_id)`: Transition PENDING→RUNNING (tailor.py:342-366)
- `record_tailor_success(run_id, artifact_yaml_path, artifact_tex_path, artifact_pdf_path, page_count, plan_json_path=None)`
- `record_tailor_failure(run_id, error, next_retry_at)`
- `soft_delete_tailor_run(run_id)` → bool: Mark deleted_at (tailor.py:461-489)
- `insert_user_triggered_tailor_run(job_hash, apply_after_completion=False)` → Optional[TailorRunClaim]: User-driven tailor from API (tailor.py:491-555)
- `get_tailor_run(run_id)` → Optional[dict]
- `get_latest_tailor_run_for_job(job_hash)` → Optional[dict]: Newest non-deleted run
- `mark_stale_tailor_runs_failed(lease_seconds)` → int: Crash recovery (tailor.py:610-643)
- `get_tailor_runs_for_job(job_hash)` → list[JSONObject]: Full history
- `get_tailor_failure_count(job_hash)` → int: Efficient count without N+1

**Claim semantics** (tailor.py:229-340): 32-byte hex claim token. Searches for QUALIFIED jobs, checks no SUCCESS exists (idempotent), excludes active PENDING/RUNNING (staleness guarded by lease_seconds), counts FAILED ≤ max_retries, respects next_retry_at. Returns merged dict so worker has full job + tailor context.

**Legacy columns**: artifact_tex_path, artifact_pdf_path still written but replaced by artifact_yaml_path in new runs (Issue #59). Table carries both for backward compat.

### ReviewMixin (review.py:26-593)

**Owns table**: review_runs

**State machine**: `review_runs.status` enum
```
PENDING → SUCCESS (verdict: PASS | TAILORED | BASE | FAIL | NO_IMPROVEMENT | PAGE_FIT_FAILED)
    ↓
  FAILED (next_retry_at governs retry eligibility)
```

**Public methods**:
- `migrate_review_schema()`: Creates table with verdict CHECK from db_verdict.py (review.py:29-86)
- `_widen_verdict_check_if_needed()`: Rebuilds if legacy CHECK lacks NO_IMPROVEMENT, PAGE_FIT_FAILED (review.py:89-161)
- `_ensure_review_schema_ready()`: Guard (review.py:163-187)
- `claim_next_review_job(max_retries, lease_seconds)` → Optional[JSONObject]: **Atomic claim** (review.py:189-300)
  - Joins tailor_runs + job_postings, filters to tailor SUCCESS
  - Returns merged row with _review_run_id, _review_claim_token
- `insert_pipeline_review_run(job_hash, tailor_run_id, verdict, selected_yaml_path, selected_tex_path, selected_pdf_path, review_report_json, fallback_base_*)` → int: Direct SUCCESS insert (no claim path) for integrated tailor-review pipeline (review.py:302-372)
- `record_review_success(run_id, claim_token, verdict, selected_yaml_path, selected_tex_path, selected_pdf_path, review_report_json, agent_stdout, agent_stderr)`: Updates PENDING→SUCCESS, raises ClaimOwnershipError on token mismatch (review.py:374-444)
- `record_review_failure(run_id, claim_token, error, next_retry_at, agent_stdout, agent_stderr, fallback_base_*)`
- `mark_stale_review_runs_failed(lease_seconds)` → int: Crash recovery
- `get_review_failure_count(tailor_run_id)` → int
- `get_review_runs_for_tailor_run(tailor_run_id)` → list[JSONObject]

**Verdict handling**: Externalized to src/agents/resume_tailor/db_verdict.py via `db_verdict_check_sql()` import (review.py:42-43, 116-120). CHECK constraint generated dynamically so new verdicts don't require schema migrations.

**Fallback semantics**: On FAILED, both fallback_base_* paths and error are persisted. Allow apply stage to use fallback resume if review is exhausted.

### ApplyMixin (apply.py:45-1148)

**Owns tables**: apply_runs, apply_handoffs

**State machines**:

apply_runs.status:
```
PENDING → SUCCESS (outcome: NEEDS_REVIEW | SUBMITTED | FAILED_*)
    ↓
  FAILED (next_retry_at governs retry eligibility)
```

apply_handoffs.handoff_status:
```
PENDING_REVIEW → APPROVED
             ↓
           REJECTED
```

**Key columns**:
- apply_runs.outcome: Enum (src/agents/apply_worker/schemas.py::ApplyOutcome): NEEDS_REVIEW, SUBMITTED, FAILED_PREFILL, FAILED_UPLOAD, FAILED_NAVIGATION, FAILED_OTHER
- apply_runs.confidence_score: [0.0, 1.0] weighted completeness
- apply_runs.confidence_report_json: Serialized ConfidenceReport
- apply_runs.simplify_autofill_detected: Boolean flag for Simplify extension activation
- apply_runs.unresolved_fields_json: Rich field metadata for finisher repair
- apply_handoffs: Maps apply_run_id 1:1 to operator-review queue with deferred_questions_json, finisher_diagnostics_json, user_answers_json

**Public methods**:
- `migrate_apply_schema()`: Creates both tables, applies idempotent ALTERs for finisher columns (apply.py:48-159)
- `_ensure_apply_schema_ready()`: Guard (apply.py:161-176)
- `claim_next_apply_job(max_retries, lease_seconds)` → Optional[JSONObject]: **Atomic claim** (apply.py:178-307)
  - Joins review_runs + job_postings, filters to review SUCCESS with verdict in (PASS, TAILORED, BASE)
  - **Bug 4 exclusion** (apply.py:241-252): Never re-claim PENDING rows with non-NULL claim_token (user-triggered or stale)
  - Returns merged row with _apply_run_id, _apply_claim_token
- `record_apply_success(run_id, claim_token, outcome, resume_pdf_path, resume_source, confidence_score, confidence_report_json, screenshot_path, dom_snapshot_path, unresolved_fields_json, simplify_autofill_detected, ats_platform, page_url)`: Atomically updates PENDING→SUCCESS
- `record_apply_failure(run_id, claim_token, error, next_retry_at, outcome=None, screenshot_path=None, dom_snapshot_path=None, ats_platform=None, page_url=None)`: Partial capture allowed
- `record_apply_handoff(apply_run_id, job_hash, review_run_id, apply_outcome, resume_source, resume_pdf_path, confidence_score, confidence_report_json, unresolved_fields_json, screenshot_path, dom_snapshot_path, ats_platform, page_url, deferred_questions_json=None, finisher_diagnostics_json=None)`: Upsert handoff row for operator review (apply.py:467-572)
- `get_apply_handoffs(handoff_status=None, limit)` → list[JSONObject]: Newest-first query
- `mark_stale_apply_runs_failed(lease_seconds)` → int: Crash recovery
- `get_apply_failure_count(review_run_id)` → int
- `transition_handoff_status(handoff_id, target_status, reviewer_notes=None)` → JSONObject: **Atomic handoff+job_postings update** (apply.py:678-760)
  - Updates apply_handoffs.handoff_status + job_postings.status in same transaction
  - APPROVED → job status = APPLIED, REJECTED → job status = REJECTED
  - Raises ValueError on invalid transition (non-PENDING source)
- `save_handoff_user_answers(handoff_id, user_answers_json)` → JSONObject: Persist reviewer answers before finisher re-submit
- `enqueue_apply_run_for_job(job_hash)` → dict: **Atomic user-triggered apply** (apply.py:822-942)
  - Checks no PENDING apply exists (returns ApplyRunInFlightError)
  - Finds latest SUCCESS review run
  - Inserts PENDING apply_runs with fresh claim_token
  - Returns merged dict compatible with claim_next_apply_job
  - Raises NoReviewRunError if no review exists
- `enqueue_apply_run_with_base_resume(job_hash, base_pdf_path)` → dict: **Synthetic tailor+review for skip-tailoring** (apply.py:944-1097)
  - Inserts synthetic tailor_runs row (status=SUCCESS, error='skipped_by_user')
  - Inserts synthetic review_runs row (status=SUCCESS, verdict=BASE, fallback_base_pdf_path=<pdf>)
  - Inserts apply_runs row with claim_token
  - Returns merged dict with verdict='BASE'
- `get_apply_run(run_id)` → Optional[JSONObject]: Non-deleted rows only
- `soft_delete_apply_run(run_id)` → bool: Mark deleted_at (apply.py:1122-1147)

**Handoff state machine detail** (apply.py:678-760):
```python
await conn.execute("BEGIN IMMEDIATE")
SELECT * FROM apply_handoffs WHERE id=? → check current status is PENDING_REVIEW
UPDATE apply_handoffs SET handoff_status=?, reviewed_at=NOW(), updated_at=NOW()
UPDATE job_postings SET status=(APPLIED if target=APPROVED else REJECTED)
SELECT * FROM apply_handoffs WHERE id=? → return updated row
COMMIT
```
One-way transitions enforced: only PENDING_REVIEW→{APPROVED, REJECTED}. Reviewer notes are optional.

### CostsMixin (costs.py:36-387)

**Owns tables**: cost_events, budget_settings, app_settings

**Cost event schema** (costs.py:54-96):
- stage: TEXT (GATE, TAILOR, REVIEW, APPLY, DISCOVERY)
- cost_usd: REAL (non-negative)
- job_hash: TEXT (optional)
- run_id: TEXT (optional)
- metadata_json: TEXT (optional)
- **Issue #59 additions** (costs.py:24-33, 65-72):
  - provider: TEXT (default 'unknown')
  - model: TEXT (default 'unknown')
  - prompt_tokens: INTEGER
  - completion_tokens: INTEGER
  - cached_input_tokens: INTEGER
  - reasoning_tokens: INTEGER
  - phase: TEXT (optional sub-phase)
  - cost_source: TEXT (provider, computed, internal, unknown)

**Public methods**:
- `migrate_cost_schema()`: Creates tables + idempotent ALTERs for Issue #59 columns (costs.py:39-126)
- `_ensure_cost_schema_ready()`: Guard (costs.py:128-152)
- `record_cost_event(stage, cost_usd, job_hash=None, run_id=None, metadata_json=None, provider='unknown', model='unknown', prompt_tokens=0, completion_tokens=0, cached_input_tokens=0, reasoning_tokens=0, phase=None, cost_source='unknown')`: Forward-only insert (costs.py:154-238)
- `get_budget_settings()` → JSONObject: Returns {monthly_budget_usd, spent_usd, remaining_usd, utilization_pct}
  - Rolls up current month's cost_events via `strftime('%Y-%m', recorded_at)`
- `is_budget_exceeded()` → bool: Guard for worker loops
- `set_budget_settings(monthly_budget_usd)` → JSONObject: Upsert budget_settings row 1, return updated snapshot
- `get_service_tier()` → str: Reads app_settings WHERE key='service_tier', default 'base'
- `set_service_tier(tier)`: Upsert app_settings

**Budget enforcement**: Worker loops call `is_budget_exceeded()` before claiming new jobs. Does not stop in-flight work.

### SystemSettingsMixin (system_settings.py:62-261)

**Owns table**: system_settings (generic key/value store)

**Keys**:
- automation.gate_mode: {autonomous, opt_in, both}
- automation.tailor_mode: {autonomous, opt_in, both}
- automation.apply_mode: {autonomous, opt_in, both}

**Public methods**:
- `migrate_system_settings_schema()`: Creates table
- `_ensure_system_settings_schema_ready()`: Guard
- `get_system_setting(key)` → Optional[str]: Raw lookup
- `set_system_setting(key, value)`: Upsert with updated_at
- `get_automation_mode(key, default='opt_in')` → str: Validated enum getter
- `set_automation_mode(key, mode)`: Enum-validated setter (raises ValueError on typo)
- `seed_automation_defaults_from_env()`: One-time seeding from GATE_MODE_ENV_VAR, TAILOR_MODE_ENV_VAR, APPLY_MODE_ENV_VAR (system_settings.py:227-261)

**Semantics**: Worker and API read these every cycle to decide autonomous vs. manual-only operation. Only set on first boot if key is missing; existing rows survive restarts.

### TelemetryMixin

Already covered above (see crawl_history, daily_stats).

### FailureResetsMixin (failure_resets.py:14-125)

**Owns**: No dedicated tables; operates across all stages

**Public methods**:
- `reset_agent_failure_state(job_hash)`: Clears agent_failed_at, agent_error, agent_retry_count, agent_next_retry_at, agent_claim_token, agent_claimed_at; sets status=NEW (failure_resets.py:17-48)
- `reset_tailor_failure_state(job_hash)`: DELETE FROM tailor_runs WHERE status=FAILED (failure_resets.py:50-69)
- `reset_review_failure_state(job_hash)` → int: DELETE FROM review_runs WHERE status=FAILED AND tailor_run_id IN (...) (failure_resets.py:71-97)
- `reset_apply_failure_state(job_hash)` → int: DELETE FROM apply_runs WHERE status=FAILED AND review_run_id IN (...) (failure_resets.py:99-125)

**Operator use case**: After manual investigation, operator clicks "Requeue" to clear terminal failure markers and re-enter the pipeline.

## Schema Overview

### Tables & Key Columns

#### job_postings (discovery root)
```sql
PRIMARY KEY: id (autoincrement)
UNIQUE: job_hash (MD5 dedup)

Core posting data:
  job_hash, source, source_url, company, company_url,
  title, location, is_remote, job_type,
  salary_min, salary_max, salary_currency, salary_source,
  description, requirements, posted_date, posted_date_parsed, raw_data

Workflow status:
  status (NEW | FILTERED | QUALIFIED | APPLIED | REJECTED)
  liveness_status (active | expired | uncertain | unchecked)

Agent processing (gate stage):
  agent_processed_at (success timestamp)
  agent_result (serialized GateRunResult)
  agent_failed_at (terminal failure marker)
  agent_error (last error message)
  agent_retry_count (attempt counter)
  agent_next_retry_at (backoff timestamp)
  agent_claim_token (12-byte hex)
  agent_claimed_at (claim timestamp)

Metadata:
  fetched_at, updated_at

INDEXES:
  idx_job_hash, idx_status, idx_company, idx_fetched_at, idx_source,
  idx_agent_processed, idx_agent_failed,
  idx_agent_retry_ready (status, agent_failed_at, agent_processed_at, agent_next_retry_at),
  idx_agent_claimed_at
```

#### tailor_runs
```sql
PRIMARY KEY: id
FK: job_hash → job_postings.job_hash

Tracking:
  job_hash, status (PENDING | RUNNING | SUCCESS | FAILED),
  claim_token, started_at, completed_at, deleted_at

Artifacts:
  artifact_yaml_path (work file)
  artifact_tex_path (compiled TeX)
  artifact_pdf_path (final PDF)
  plan_json_path (planner rationale, Issue #59 Bug E)
  page_count

Retry:
  error, next_retry_at

Pipeline:
  apply_after_completion (boolean flag, Issue #59)

INDEXES:
  idx_tailor_runs_job_hash, idx_tailor_runs_status,
  idx_tailor_runs_started_at, idx_tailor_runs_job_status
```

#### review_runs
```sql
PRIMARY KEY: id
FK: job_hash, tailor_run_id

Tracking:
  job_hash, tailor_run_id, status (PENDING | SUCCESS | FAILED),
  claim_token, started_at, completed_at

Verdict:
  verdict (PASS | TAILORED | BASE | FAIL | NO_IMPROVEMENT | PAGE_FIT_FAILED)
  verdict CHECK constraint from db_verdict_check_sql()

Artifacts:
  selected_yaml_path, selected_tex_path, selected_pdf_path
  review_report_json (reviewer payload)
  fallback_base_yaml_path, fallback_base_tex_path, fallback_base_pdf_path

Diagnostics:
  agent_stdout, agent_stderr, error, next_retry_at

INDEXES:
  idx_review_runs_job_hash, idx_review_runs_status,
  idx_review_runs_started_at, idx_review_runs_tailor_run_id,
  idx_review_runs_tailor_status
```

#### apply_runs
```sql
PRIMARY KEY: id
FK: job_hash, review_run_id

Tracking:
  job_hash, review_run_id, status (PENDING | SUCCESS | FAILED),
  claim_token, started_at, completed_at, deleted_at

Resume:
  resume_pdf_path, resume_source (TAILORED | BASE)

Outcome:
  outcome (NEEDS_REVIEW | SUBMITTED | FAILED_PREFILL | FAILED_UPLOAD | FAILED_NAVIGATION | FAILED_OTHER)
  confidence_score [0.0, 1.0], confidence_report_json

Diagnostics:
  screenshot_path, dom_snapshot_path, page_url,
  unresolved_fields_json, ats_platform,
  simplify_autofill_detected, error, next_retry_at

INDEXES:
  idx_apply_runs_job_hash, idx_apply_runs_status,
  idx_apply_runs_started_at, idx_apply_runs_review_run_id,
  idx_apply_runs_outcome
```

#### apply_handoffs
```sql
PRIMARY KEY: id
UNIQUE FK: apply_run_id

Workflow:
  job_hash, review_run_id, handoff_status (PENDING_REVIEW | APPROVED | REJECTED),
  apply_outcome (mirrors apply_runs.outcome enum)

Resume metadata:
  resume_source, resume_pdf_path, confidence_score, confidence_report_json

Diagnostics:
  unresolved_fields_json, screenshot_path, dom_snapshot_path,
  ats_platform, page_url

Human review:
  reviewer_notes, reviewed_at,
  deferred_questions_json (Issue #59),
  finisher_diagnostics_json (Issue #59),
  user_answers_json (Issue #59)

Metadata:
  created_at, updated_at

INDEXES:
  idx_apply_handoffs_status, idx_apply_handoffs_job_hash,
  idx_apply_handoffs_review_run_id
```

#### cost_events (forward-only telemetry)
```sql
PRIMARY KEY: id
No FK, pure event log

Event:
  stage (GATE | TAILOR | REVIEW | APPLY | DISCOVERY),
  cost_usd (non-negative), recorded_at

Correlation:
  job_hash (optional), run_id (optional), metadata_json (optional)

Provider detail (Issue #59):
  provider, model, prompt_tokens, completion_tokens,
  cached_input_tokens, reasoning_tokens, phase, cost_source

INDEXES:
  idx_cost_events_recorded_at,
  idx_cost_events_stage_recorded_at,
  idx_cost_events_job_hash,
  idx_cost_events_run_id,
  idx_cost_events_model
```

#### budget_settings
```sql
PRIMARY KEY: id (always 1)
monthly_budget_usd (REAL, default 500.0)
updated_at
```

#### crawl_history
```sql
PRIMARY KEY: id
source, company (optional), started_at, completed_at,
status (IN_PROGRESS | SUCCESS | FAILED),
jobs_found, jobs_new, error_message

INDEXES:
  idx_crawl_source, idx_crawl_started
```

#### daily_stats
```sql
PRIMARY KEY: date (YYYY-MM-DD string)
total_jobs_discovered, jobs_new, jobs_duplicate,
sources_crawled, sources_failed
(Accumulates across multiple runs on same date via ON CONFLICT DO UPDATE)
```

#### system_settings
```sql
PRIMARY KEY: key
value, updated_at
```

#### app_settings
```sql
PRIMARY KEY: key
value
```

### Entity-Relationship Diagram

```mermaid
erDiagram
  job_postings ||--o{ tailor_runs : "job_hash"
  job_postings ||--o{ review_runs : "job_hash"
  job_postings ||--o{ apply_runs : "job_hash"
  job_postings ||--o{ cost_events : "job_hash"
  
  tailor_runs ||--o{ review_runs : "tailor_run_id"
  review_runs ||--o{ apply_runs : "review_run_id"
  
  apply_runs ||--|| apply_handoffs : "apply_run_id"
  
  crawl_history : string source
  crawl_history : string company
  crawl_history : string status
  
  daily_stats : string date
  
  budget_settings : id
  budget_settings : monthly_budget_usd
  
  system_settings : key
  system_settings : value
  
  cost_events : stage
  cost_events : cost_usd
  cost_events : provider
  cost_events : model
  
  apply_handoffs : handoff_status
  apply_handoffs : apply_outcome
```

## Status & Lifecycle State Machines

### Job Posting Status Lifecycle

```mermaid
stateDiagram-v2
  [*] --> NEW
  
  NEW --> FILTERED: Agent decision (not_qualified)
  NEW --> QUALIFIED: Agent decision (qualified)
  NEW --> [*]: (stays NEW if agent fails, retries via next_retry_at)
  
  QUALIFIED --> APPLIED: Apply handoff approved OR autonomous apply succeeds
  QUALIFIED --> REJECTED: Apply handoff rejected
  QUALIFIED --> [*]: (stays QUALIFIED if tailor/review fail, retries via claim logic)
  
  FILTERED --> [*]
  APPLIED --> [*]
  REJECTED --> [*]
  
  note right of NEW
    Controls agent claim loop.
    Agent processing external to status enum;
    failures tracked in agent_* columns.
  end
  
  note right of QUALIFIED
    Controls tailor/review/apply claim loops.
    Stage workers filter by status=QUALIFIED.
  end
```

### Agent Processing Lifecycle (job_postings columns)

```mermaid
stateDiagram-v2
  [*] --> new_job
  
  new_job: agent_processed_at=NULL
  new_job: agent_failed_at=NULL
  new_job: agent_next_retry_at=NULL
  new_job: claim_token=NULL
  
  new_job --> claimed: Claim loop<br/>claim_token set<br/>claimed_at=NOW
  
  claimed: In flight with<br/>worker process
  
  claimed --> success: record_agent_decision()<br/>agent_processed_at=NOW<br/>status→QUALIFIED|FILTERED
  
  claimed --> retry: record_agent_retry()<br/>agent_next_retry_at=NOW+backoff
  
  claimed --> terminal_fail: mark_agent_terminal_failed()<br/>agent_failed_at=NOW<br/>status stays NEW
  
  success --> [*]
  retry --> new_job
  terminal_fail --> new_job: Operator reset_agent_failure_state
  
  note right of claimed
    Lease timeout (AGENT_CLAIM_LEASE_SECONDS, default 15min)
    converts stale PENDING to FAILED via
    mark_stale_tailor_runs_failed() on startup.
  end
```

### Tailor Run Lifecycle

```mermaid
stateDiagram-v2
  [*] --> pending
  
  pending: PENDING status<br/>claim_token set<br/>started_at=NOW
  
  pending --> running: mark_tailor_running()
  running: RUNNING status<br/>(visibility to dashboard)
  
  running --> success: record_tailor_success()<br/>artifacts written<br/>completed_at=NOW
  
  running --> failed: record_tailor_failure()<br/>error logged<br/>next_retry_at set
  
  success --> soft_delete: soft_delete_tailor_run()<br/>deleted_at=NOW
  
  failed --> pending: Claim retry (max_retries-bounded)
  failed --> [*]: Exhausted retries
  
  pending --> soft_delete: User DELETE /api/tailor-runs/{id}
  
  soft_delete --> [*]
  success --> [*]: Apply stage consumes
  
  note right of pending
    Stale PENDING rows (> TAILOR_CLAIM_LEASE_SECONDS old)
    marked FAILED on startup by mark_stale_tailor_runs_failed().
  end
```

### Review Run Lifecycle

```mermaid
stateDiagram-v2
  [*] --> pending
  
  pending: PENDING status<br/>claim_token set<br/>started_at=NOW
  
  pending --> success: record_review_success()<br/>verdict + selected artifacts<br/>completed_at=NOW
  
  pending --> failed: record_review_failure()<br/>fallback artifacts<br/>next_retry_at set
  
  failed --> pending: Claim retry (max_retries-bounded)
  failed --> [*]: Exhausted retries
  
  success --> [*]: Apply stage consumes
  
  note right of success
    Verdicts: PASS, TAILORED, BASE, FAIL,
    NO_IMPROVEMENT, PAGE_FIT_FAILED.
    Apply stage filters to PASS|TAILORED|BASE.
  end
```

### Apply Run Lifecycle

```mermaid
stateDiagram-v2
  [*] --> pending
  
  pending: PENDING status<br/>claim_token set<br/>started_at=NOW
  
  pending --> success: record_apply_success()<br/>outcome + confidence<br/>completed_at=NOW
  
  pending --> failed: record_apply_failure()<br/>partial artifacts<br/>next_retry_at set
  
  success --> handoff: record_apply_handoff()<br/>apply_handoffs.status=PENDING_REVIEW
  
  failed --> pending: Claim retry (max_retries-bounded)
  failed --> [*]: Exhausted retries
  
  success --> soft_delete: soft_delete_apply_run()
  
  soft_delete --> [*]: Freed in-flight slot
  
  note right of pending
    Bug 4: Never re-claim PENDING rows with claim_token.
    Stale rows marked FAILED on startup.
  end
```

### Apply Handoff Lifecycle

```mermaid
stateDiagram-v2
  [*] --> pending_review
  
  pending_review: PENDING_REVIEW status<br/>job_postings.status remains QUALIFIED
  
  pending_review --> approved: transition_handoff_status()<br/>job_postings.status→APPLIED<br/>reviewed_at=NOW
  
  pending_review --> rejected: transition_handoff_status()<br/>job_postings.status→REJECTED<br/>reviewed_at=NOW
  
  approved --> [*]
  rejected --> [*]
  
  note right of pending_review
    Operator reviews apply_handoffs rows,
    optionally provides reviewer_notes,
    optionally saves user_answers_json
    for finisher re-submit.
  end
```

## Migrations & Schema Versioning

**No migration framework** (e.g., Alembic, Flyway). Instead:

1. **Baseline schema** (schema.sql:1-294):
   - Loaded once on `create_tables()`
   - Defines core job_postings, crawl_history, daily_stats, tailor_runs (base structure), review_runs (base), apply_runs (base), apply_handoffs (base), cost_events (base), budget_settings, ai_provider_settings, portal_configs

2. **Per-stage migrations** (called from `create_tables()`, db_manager.py:188-191):
   - `migrate_tailor_schema()`: Adds tailor_runs if missing; ALTERs for artifact_yaml_path, deleted_at, plan_json_path, apply_after_completion; rebuilds table if CHECK lacks RUNNING
   - `migrate_review_schema()`: Creates review_runs if missing; widens verdict CHECK for NO_IMPROVEMENT, PAGE_FIT_FAILED
   - `migrate_system_settings_schema()`: Creates system_settings table
   - `migrate_cost_schema()`: Created by CostsMixin but not called from create_tables (loaded on-demand via _ensure_cost_schema_ready())
   - `migrate_apply_schema()`: Created by ApplyMixin but not called from create_tables (loaded on-demand)

3. **Idempotent ALTERs** pattern:
   ```python
   cursor = await conn.execute("PRAGMA table_info({table})")
   columns = {col["name"] for col in await cursor.fetchall()}
   if "new_column" not in columns:
       await conn.execute("ALTER TABLE {table} ADD COLUMN new_column {type}")
   ```
   Used in tailor, review, apply, cost migrations to safely add columns on existing databases.

4. **Stale row recovery** (on startup):
   - `mark_stale_tailor_runs_failed(lease_seconds)`: Converts PENDING/RUNNING tailor runs older than lease to FAILED
   - `mark_stale_review_runs_failed(lease_seconds)`: Converts stale PENDING review runs to FAILED
   - `mark_stale_apply_runs_failed(lease_seconds)`: Converts stale PENDING apply runs to FAILED

## Concurrency Model

**Locking strategy**: SQLite `IMMEDIATE` transactions for all multi-statement operations that must be atomic.

### Claim-and-lease semantics

Every stage uses the same pattern:

```python
BEGIN IMMEDIATE  # Exclusive lock
SELECT candidates WHERE (
  status matches &&
  no active claims (PENDING age <= lease) &&
  no successful completion &&
  retry count < max &&
  next_retry_at elapsed
)
INSERT into run table with fresh claim_token
COMMIT
```

**Claim token**: 12-byte or 32-byte hex string (`os.urandom(12|32).hex()`). Worker must present same token on completion; mismatch raises `ClaimOwnershipError`.

**Lease**: Worker must finish within lease_seconds or claim is considered stale:
- Agent: 900s (15 min)
- Tailor: 7200s (2 hr)
- Review: 7200s (2 hr)
- Apply: 1800s (30 min)

Configurable via env vars: AGENT_CLAIM_LEASE_SECONDS, etc.

### Soft deletes & in-flight slots

`apply_runs.deleted_at` and `tailor_runs.deleted_at` (soft-delete pattern):
- User deletes tailor run → soft-delete (deleted_at=NOW)
- Soft-deleted rows excluded from all claim queries
- Row kept for audit
- Frees up in-flight slot for job

Prevents users from accidentally permanently losing rows while allowing requeue.

### Race conditions prevented

1. **Duplicate claims**: `BEGIN IMMEDIATE` block prevents concurrent workers from claiming same job
2. **Claim token hijack**: `record_*_success/failure` checks claim_token == owned_token
3. **Stale claims**: Lease timeouts mark stale PENDING as FAILED on startup
4. **Job-status drift**: Handoff transition updates job_postings.status + apply_handoffs atomically

## Soft-Delete & Retention

### Columns with soft-delete support:
- `tailor_runs.deleted_at`
- `apply_runs.deleted_at`

### Cleanup behavior:
- No automatic hard-delete in the codebase
- Soft-deleted rows excluded from:
  - Claim queries (WHERE deleted_at IS NULL)
  - Latest-run queries (WHERE deleted_at IS NULL)
  - Listing endpoints
- Rows kept indefinitely for audit

### Cost events:
- Forward-only, never deleted
- `strftime('%Y-%m', recorded_at)` filters to current month for budget checks

### Crawl/daily stats:
- No delete; append-only
- Oldest data is months/years stale but queries still scan full table (consider archiving for production)

## Risks & Gotchas

### 1. Legacy columns still in schema (AGENTS.md references)
- `*_yaml_path` columns appear in schema but newer code prefers serialized JSON paths
- Example: tailor_runs still has artifact_tex_path, artifact_pdf_path but artifact_yaml_path is the canonical path
- **Impact**: Backward compat requires writing both; new code reads artifact_yaml_path first
- **Fix**: Deprecation planned but not yet scheduled

### 2. Unique constraint on apply_run_id in apply_handoffs
- `apply_handoffs.apply_run_id UNIQUE`: Only one handoff per apply run
- **Risk**: If record_apply_handoff() is called twice, second call triggers upsert (ON CONFLICT DO UPDATE)
- **Expected**: Idempotent; finisher can safely retry handoff creation

### 3. Verdict CHECK constraint dynamism
- `review_runs.verdict` CHECK is generated by `db_verdict_check_sql()` in src/agents/resume_tailor/db_verdict.py
- Adding new verdict requires:
  1. Update db_verdict_check_sql()
  2. Existing databases rebuild table via _widen_verdict_check_if_needed()
- **Risk**: Typo in verdict string fails CHECK; not caught until runtime
- **Mitigation**: Type hints in reviewers; test coverage on verdict insert

### 4. Agent status stays NEW across retries
- `job_postings.status` enum does not include intermediate states like PROCESSING, RETRYING
- Agent processing tracked via agent_* columns separately
- **Risk**: Operators may not see that agent is actively retrying without viewing agent_next_retry_at
- **Mitigation**: Dashboard shows agent_* state; API exposes full row

### 5. Cost events no automatic aggregation
- `cost_events` is append-only; no pre-aggregated summaries
- Budget queries do live `SUM(cost_usd) WHERE strftime('%Y-%m', recorded_at) = current_month`
- **Risk**: Heavy budget queries if cost_events grows to millions of rows
- **Mitigation**: Consider materialized daily_costs table for production; not yet implemented

### 6. Claim token collision probability
- Using `os.urandom(N).hex()` → 2^(8N) possible tokens
- 12-byte = 96 bits, 32-byte = 256 bits
- **Risk**: Negligible for 12-byte; cryptographically secure for 32-byte
- **Mitigation**: Current usage is sufficient; no known collisions

### 7. Applied handoffs do not re-block new applies
- Once apply handoff is APPROVED, job_postings.status=APPLIED but no flag prevents re-enqueueing
- **Risk**: User could manually POST /api/jobs/{hash}/apply again; second apply run allowed
- **Mitigation**: Frontend disables button; API should ideally check apply_handoffs.handoff_status before enqueue

### 8. Tailor+apply_after_completion flag survives soft-deletes
- When user deletes tailor run but apply_after_completion=1, the intent is lost
- **Risk**: If tailor run is re-created, old flag does not carry over
- **Mitigation**: Dashboard resets flag; acceptable UX

### 9. System settings has no schema validation
- system_settings table is generic key/value; no schema enforcement
- **Risk**: Typo in key (e.g., 'automation.tailr_mode') silently ignored
- **Mitigation**: Type-safe getters (get_automation_mode) validate values; mistyped keys fall back to default

### 10. Missing foreign key constraints
- tailor_runs.job_hash is TEXT, not FK to job_postings.id
- review_runs.tailor_run_id has no FK constraint to tailor_runs.id
- apply_runs.review_run_id has no FK constraint to review_runs.id
- **Risk**: Orphaned rows if parent is deleted (not a practical concern since no deletes, only soft-deletes)
- **Benefit**: Flexibility to clean up without cascades; simpler schema
- **Mitigation**: Application code enforces referential integrity

---

**Conclusion**: The database layer is a mature async-first SQLite design with multi-stage claim-and-lease concurrency, soft-delete retention, and comprehensive cost telemetry. The mixin pattern keeps concerns separated and reduces code duplication. Migration strategy relies on idempotent ALTERs and per-stage schema guards for backward compatibility. Key risks are legacy column duplication and the absence of hard foreign keys, but both are manageable trade-offs.
