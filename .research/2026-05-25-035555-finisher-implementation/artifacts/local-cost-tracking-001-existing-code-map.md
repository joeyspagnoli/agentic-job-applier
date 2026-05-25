# Local audit: existing cost-tracking code map

Date: 2026-05-25
Scope: every file in this repo that participates in cost telemetry.

## 1. Provider abstraction (token-usage source of truth)

- `/Users/jspags/Projects/agentic-job-applier/src/providers/types.py:66-83` — `CompletionResponse` carries `usage_prompt_tokens` and `usage_completion_tokens` (default `0`).
- `/Users/jspags/Projects/agentic-job-applier/src/providers/openai_provider.py:149-166` — fills both from `response.usage.prompt_tokens` / `response.usage.completion_tokens`.
- `/Users/jspags/Projects/agentic-job-applier/src/providers/factory.py:23-68` — only `OPENAI` and `OPENROUTER` (both built from `OpenAIProvider`) survive; Anthropic / Gemini / Codex were removed post-issue-61.
- `/Users/jspags/Projects/agentic-job-applier/src/providers/factory.py:71-91` — `build_provider_from_env()` reads `OPENAI_API_KEY`.

This abstraction is **only** wired into the **gate stage** (`src/agents/root_apply_decider/unified_runtime.py`). Tailor and Review bypass it; Apply makes no LLM call.

## 2. Central cost helper

- `/Users/jspags/Projects/agentic-job-applier/src/utils/cost_tracking.py`
  - `PIPELINE_STAGE_*` constants at lines `23-27` (GATE/TAILOR/REVIEW/APPLY/DISCOVERY).
  - `_STAGE_RATE_ENV_KEYS` at `29-35` maps each stage to `COST_RATE_<STAGE>_USD`.
  - `_DEFAULT_STAGE_RATE_USD = 0.0` at `37`.
  - `_env_var_names_for_model(model)` at `46-60` turns e.g. `"openai/gpt-5-mini"` → `("COST_RATE_OPENAI_GPT_5_MINI_IN_USD", "COST_RATE_OPENAI_GPT_5_MINI_OUT_USD")`.
  - `_token_cost_from_metadata(metadata)` at `88-136` computes USD when metadata contains `model`, `prompt_tokens`, `completion_tokens` AND both env vars are set.
  - `_coerce_stage_rate_usd(stage)` at `139-179` falls back to the flat stage env var.
  - `record_stage_cost_event(...)` at `182-220` — single write path. If token cost is `None` (no env vars), uses flat stage rate.
  - `check_budget_before_claim(db, stage)` at `223-243`.

`_TOKENS_PER_RATE_UNIT = 1000.0` (`39`) — env rate is "USD per 1k tokens".

## 3. DB schema for cost

- `/Users/jspags/Projects/agentic-job-applier/src/database/_mixins/costs.py:34-50` —
  ```sql
  CREATE TABLE IF NOT EXISTS cost_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      stage TEXT NOT NULL,
      job_hash TEXT,
      run_id TEXT,
      cost_usd REAL NOT NULL,
      metadata_json TEXT,
      recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      CHECK (stage IN ('GATE','TAILOR','REVIEW','APPLY','DISCOVERY')),
      CHECK (cost_usd >= 0)
  );
  ```
  Indexes on `recorded_at`, `(stage, recorded_at)`, `job_hash`.

- `budget_settings` table at `52-57` (single-row, `monthly_budget_usd REAL DEFAULT 500.0`).
- `record_cost_event(...)` at `101-145` — the INSERT.
- `get_budget_settings()` at `147-194`, `is_budget_exceeded()` at `196-210`.

No per-row cost columns on `tailor_runs`, `review_runs`, or `apply_runs` (verified by grep). All cost lives in `cost_events`.

## 4. API reads

- `/Users/jspags/Projects/agentic-job-applier/api/routers/costs.py`
  - `GET /api/costs/stats` (lines `18-83`) — sums `cost_events` for current month.
  - `GET /api/costs/daily-trend` (lines `86-163`) — daily/monthly aggregation.
  - `GET /api/costs/by-stage` (lines `166-208`) — current-month spend grouped by `stage`.

## 5. Dashboard reads

- `/Users/jspags/Projects/agentic-job-applier/dashboard/src/pages/CostTrackingPage.tsx` calls `fetchCostStats`, `fetchCostDailyTrend`, `fetchCostByStage`, `fetchBudget`. No write paths.

## 6. WRITE call sites (per stage)

### GATE — `/Users/jspags/Projects/agentic-job-applier/scripts/process_new_jobs.py`
- Imports cost helpers at `36-38`.
- Line `301-312`: writes a `FAILED` cost event when the decider raises. Metadata has `model`, `provider`, `retry_count`, `status` — **but NO `prompt_tokens` / `completion_tokens`**.
- Line `360-371`: writes a `SUCCESS` cost event after a parsed decision. Metadata has `model`, `provider`, `decision`, `status` — **again no token counts**.

Why no tokens? Gate uses Google ADK (`google.adk.agents.BaseAgent`, `google.adk.runners.Runner`) — see `src/agents/root_apply_decider/runtime.py:62-134`. The ADK runner returns text events but `GateRunResult` (schemas.py:41-50) does not capture token usage. The newer unified provider runtime (`unified_runtime.py:33-80`) does extract `usage_prompt_tokens`/`usage_completion_tokens` from `CompletionResponse` and logs them at line `68-74`, **but the worker script does not call `run_gate_with_provider` — it calls `run_decider_for_job` (the ADK path) at `process_new_jobs.py:293`**. The unified runtime is dead code from a cost-tracking perspective.

### TAILOR / REVIEW — `/Users/jspags/Projects/agentic-job-applier/src/agents/resume_tailor/pipeline.py`
- `_record_cost(...)` at lines `405-449` — best-effort wrapper. Passes `model`, `phase`, `prompt_tokens`, `completion_tokens`, `total_tokens` from `LlmCallResult`.
- Called 7 times across the pipeline (lines `569, 640, 695, 722, 762`, ...), once per Instructor sub-call (tailor / trim / retailor / two-way / three-way reviewer).
- Token source: `LlmCallResult` (`src/agents/resume_tailor/llm.py:46-59`) populated by `_extract_usage()` at `llm.py:155-186` — reads from the raw OpenAI/Responses-API completion object. **Tailor/review do NOT go through `src/providers/`** — they call `instructor.from_openai(OpenAI(), mode=instructor.Mode.RESPONSES_TOOLS)` directly (`llm.py:138-147`).

So tailor/review have correct token-passing but are coupled to the OpenAI SDK directly (not the provider abstraction).

### APPLY — `/Users/jspags/Projects/agentic-job-applier/scripts/process_apply_jobs.py`
- `_record_apply_cost_best_effort(...)` at lines `369-403`.
- Called twice (success path at `645-655`, failure path at `346-357`).
- Metadata contains `status`, `review_run_id`, `outcome`, `resume_source`, `attempt` — **NO `model`, no tokens**.
- Apply worker makes **no LLM calls** today (verified by grep across `src/agents/apply_worker/`). The cost event is purely a "this stage ran" stub. Cost computation will resolve to `COST_RATE_APPLY_USD` env (unset → `0.0`).

### DISCOVERY — never written.
The stage label exists in the CHECK constraint and the env-var map, but `grep -rn 'stage="DISCOVERY"\|PIPELINE_STAGE_DISCOVERY' src/ scripts/ api/` returns only the declaration in `cost_tracking.py:27,34`. No caller writes discovery events.

## 7. Configuration check (the smoking gun)

`.env.example` (lines `1-100`) and the local `.env` were both grepped for `COST_RATE`:
- `.env.example` — zero matches.
- `.env` — zero matches (`grep -c "COST_RATE" /Users/jspags/Projects/agentic-job-applier/.env` returns `0`).

`deploy/README.md:45-49` and the project `README.md:166` mention these env vars as "OPTIONAL — defaults to 0.0 if unset", which is exactly what is happening today: every cost-event row written by the gate, tailor, review, and apply workers receives `cost_usd = 0.0`.

The Cost Tracking dashboard, therefore, sums up zeros and displays `$0.00`.
