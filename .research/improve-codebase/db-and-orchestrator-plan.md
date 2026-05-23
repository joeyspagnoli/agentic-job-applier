# Database + Orchestrator Refactor Plan

## src/database/db_manager.py (2841 lines)

**Approach: Mixin modules composed into one DatabaseManager**. Public API unchanged.

```
src/database/db_manager.py            # __init__, connect, close, __aenter__, __aexit__, _require_conn, create_tables. Composes mixins. Target ~250 lines.
src/database/_mixins/jobs.py          # JobsMixin: insert_job, get_job_by_hash, get_job_by_id, get_resume_tailor_job_context, get_existing_job_hashes, update_job_status, get_jobs_by_status, get_jobs_pending_agent_processing, get_job_count, get_jobs_today
src/database/_mixins/telemetry.py     # TelemetryMixin: start_crawl, complete_crawl, update_daily_stats
src/database/_mixins/agent_gate.py    # AgentGateMixin: gate decision/retry/failure + migrate_agent_schema + _ensure_agent_schema_ready (~591-929)
src/database/_mixins/tailor.py        # TailorMixin: tailor claim/success/failure/reset + tailor schema migration (~982-1362)
src/database/_mixins/review.py        # ReviewMixin: review claim/success/failure + review schema migration (~1364-1779)
src/database/_mixins/apply.py         # ApplyMixin: apply claim/success/failure/handoff + apply schema migration + transition_handoff_status (~1781-2372 + orphan at 2650)
src/database/_mixins/costs.py         # CostsMixin: record_cost_event, get_budget_settings, is_budget_exceeded, set_budget_settings, get_service_tier, set_service_tier, cost schema migration (~2374-2648)
src/database/_mixins/failure_resets.py # reset_review_failure_state, reset_apply_failure_state (and similar)
```

Risk: low-medium. Class name + import path unchanged → 38 call sites + 80+ tests stay green.

## main.py (1706 lines)

```
main.py                                         # ~80 lines: imports, main() sync entrypoint, __main__ guard, re-exports run_job_discovery
src/orchestrator/__init__.py                    # exports run_job_discovery
src/orchestrator/discovery.py                   # run_job_discovery() cycle coordinator (~200 lines)
src/orchestrator/config_loader.py               # load_yaml, load_optional_yaml, _normalize_string_list, _resolve_workday_search_text, _normalize_positive_int, resolve_job_board_default_search_terms, _build_loose_filter
src/orchestrator/insert_pipeline.py             # _filter_by_title_patterns, _insert_with_filters
src/orchestrator/fetchers/greenhouse.py         # fetch_greenhouse_jobs
src/orchestrator/fetchers/workday.py            # fetch_workday_jobs
src/orchestrator/fetchers/taleo.py              # fetch_taleo_jobs
src/orchestrator/fetchers/icims.py              # fetch_icims_jobs
src/orchestrator/fetchers/jobspy.py             # fetch_jobspy_jobs
src/orchestrator/fetchers/lever.py              # fetch_lever_jobs
src/orchestrator/fetchers/ashby.py              # fetch_ashby_jobs
src/orchestrator/fetchers/github_repos.py       # fetch_github_jobs
src/orchestrator/fetchers/linkedin.py           # fetch_linkedin_jobs
src/orchestrator/fetchers/career_pages.py       # fetch_career_page_jobs
```

`main.py` re-exports `main`, `run_job_discovery`, AND any `fetch_*_jobs` that tests import directly.

Risk: low.
