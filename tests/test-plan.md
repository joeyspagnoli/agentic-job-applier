# Test Plan

## Metadata

- Generated: 2026-03-29T05:22:29Z
- Repo Root: /Users/jspags/Projects/agentic-job-applier
- Detected Test Framework(s): pytest (current), unittest.mock (current), Vitest + React Testing Library (recommended for untested frontend)
- Overall Test Quality Rating: Adequate

## Existing Test Inventory

| Test File | Framework | Type | Approx. Test Count | Quality | Notes |
| --------- | --------- | ---- | ------------------ | ------- | ----- |
| scripts/test_fetchers.py | pytest | integration | 0 | Minimal | Utility script-style test file; no `test_` funcs discovered. |
| tests/__init__.py | pytest | support | 0 | Minimal | Package marker only. |
| tests/conftest.py | pytest | support | 0 | Adequate | Shared fixtures/hooks. |
| tests/test_agent_worker_resilience.py | pytest | integration | 6 | Adequate | Good resilience/error-path coverage in worker boundaries. |
| tests/test_apply_chrome_launcher.py | pytest | unit | 1 | Adequate | Focused launcher behavior check. |
| tests/test_apply_decider.py | pytest | unit | 8 | Adequate | Decider behavior and contracts. |
| tests/test_apply_schema_parity.py | pytest | unit | 2 | Adequate | Schema alignment checks. |
| tests/test_apply_worker_and_retry_semantics.py | pytest | integration | 10 | Adequate | Retry semantics covered; missing some telemetry assertions. |
| tests/test_budget_enforcement.py | pytest | integration | 13 | Adequate | Strong budget guard paths; some logging/order gaps remain. |
| tests/test_dedup_guardrails.py | pytest | unit | 4 | Adequate | Dedup guard checks. |
| tests/test_fetcher_failures.py | pytest | integration | 2 | Adequate | Failure path checks. |
| tests/test_fetcher_units.py | pytest | unit | 8 | Adequate | Source fetcher units. |
| tests/test_full_pipeline_e2e.py | pytest | e2e | 3 | Adequate | End-to-end flow checks. |
| tests/test_hygiene_hardening.py | pytest | integration | 4 | Adequate | Operational hygiene assertions. |
| tests/test_integration.py | pytest | integration | 7 | Adequate | Integration scenario set. |
| tests/test_live_agent_e2e.py | pytest | e2e | 1 | Minimal | Live gated test. |
| tests/test_ops_config_and_notifications.py | pytest | integration | 6 | Adequate | Ops/config notification paths. |
| tests/test_orchestrator_accounting_integrity.py | pytest | integration | 6 | Adequate | Accounting/integrity checks. |
| tests/test_orchestrator_failures.py | pytest | integration | 4 | Adequate | Orchestrator failure handling. |
| tests/test_pipeline_failure_signaling.py | pytest | integration | 3 | Adequate | Pipeline signaling checks. |
| tests/test_queue_claim_concurrency_and_fairness.py | pytest | integration | 5 | Strong | Concurrency and fairness assertions are specific and useful. |
| tests/test_resume_review_prompt_contract.py | pytest | unit | 1 | Adequate | Prompt contract check. |
| tests/test_resume_review_runtime.py | pytest | integration | 6 | Adequate | Runtime edge/failure behavior. |
| tests/test_resume_review_tools.py | pytest | unit | 5 | Adequate | Tool layer behavior. |
| tests/test_resume_tailor_cli_integration.py | pytest | integration | 3 | Adequate | CLI integration paths. |
| tests/test_resume_tailor_prompt_contract.py | pytest | unit | 1 | Adequate | Prompt contract check. |
| tests/test_resume_tailor_runtime.py | pytest | integration | 6 | Adequate | Runtime checks incl. some hard failures. |
| tests/test_resume_tailor_tools_and_renderer.py | pytest | unit | 4 | Adequate | Rendering/tool correctness checks. |
| tests/test_review_worker.py | pytest | integration | 6 | Adequate | Review worker behavior. |
| tests/test_scraper_to_agent_integration.py | pytest | integration | 4 | Adequate | Scraper-to-agent path. |
| tests/test_security_and_collection.py | pytest | integration | 2 | Adequate | Security/collection sanity checks. |
| tests/test_status_command_robustness.py | pytest | unit | 4 | Adequate | Status command hardening. |
| tests/test_tailor_cli_preflight.py | pytest | integration | 6 | Weak | One loop test is mislabeled and does not exercise actual loop logic. |
| tests/test_tailor_concurrent_claims.py | pytest | integration | 4 | Adequate | Tailor claim concurrency. |
| tests/test_tailor_input_validation.py | pytest | unit | 5 | Adequate | Input validation paths. |
| tests/test_tailor_worker.py | pytest | integration | 10 | Adequate | Tailor worker operational scenarios. |
| tests/test_tailor_worker_error_recovery.py | pytest | integration | 4 | Adequate | Error recovery checks. |
| tests/test_tailor_yaml_baseline.py | pytest | integration | 4 | Adequate | YAML baseline restore behavior. |
| tests/test_time_and_migrations.py | pytest | integration | 5 | Adequate | Time/migration integrity checks. |

## Existing Test Quality Assessment

Representative sample reviewed: 12/39 files (30.8%).

- Assertion quality: generally specific and meaningful, especially in concurrency/fairness and runtime tests (`tests/test_queue_claim_concurrency_and_fairness.py:76`, `tests/test_resume_tailor_runtime.py:286`).
- Edge-case coverage: good in resilience and migration paths (`tests/test_agent_worker_resilience.py:148`, `tests/test_time_and_migrations.py:217`), but missing some newly introduced UI/API and budget-ordering cases.
- Test isolation: mostly good with mock/fixture isolation; deterministic by default for core suite.
- Mocking appropriateness: mostly appropriate; one case stubs behavior but omits important assertion (`tests/test_apply_worker_and_retry_semantics.py:879`, `tests/test_apply_worker_and_retry_semantics.py:942`).
- Naming clarity: generally clear, with one notable mismatch where the test name claims loop behavior but only calls `_tailor_once` directly (`tests/test_tailor_cli_preflight.py:63`, `tests/test_tailor_cli_preflight.py:98`).

## Coverage Gap Analysis

### Untested Components

| Component / Module | File(s) | Risk Level | Justification |
| ------------------ | ------- | ---------- | ------------- |
| Resume download endpoint behavior (artifact-path resolution + access constraints) | api/main.py:1479, api/main.py:1495 | High | No direct tests cover the endpoint’s path resolution behavior or access gating. See H-001, M-002. |
| Jobs row outbound-link sanitization | dashboard/src/pages/JobsPage.tsx:320 | High | No frontend tests enforce scheme allowlisting for external job links. See M-001. |
| Settings draft preservation during global sync invalidation | dashboard/src/components/layout/TopBar.tsx:88, dashboard/src/pages/SettingsPage.tsx:176 | High | No tests verify that unsaved guided/YAML drafts survive sync refreshes. See M-004. |
| Frontend API client success-parse hardening | dashboard/src/lib/api/client.ts:72 | Medium | No tests for empty/non-JSON successful responses and typed error normalization. See L-002. |

### Undertested Components

| Component / Module | Existing Tests | Gap Description | Risk Level | Justification |
| ------------------ | -------------- | --------------- | ---------- | ------------- |
| Budget guard and budget reads | tests/test_budget_enforcement.py | Missing assertions on logging semantics and read-path write amplification behavior under concurrency | Medium | Current tests cover boolean outcomes but not operational lock/contention implications. See M-003, L-004. |
| Tailor CLI loop semantics | tests/test_tailor_cli_preflight.py | Loop-mode test does not exercise loop/sleep branch | Medium | Leaves polling behavior regression-prone despite test presence. See L-003. |
| Apply worker telemetry persistence | tests/test_apply_worker_and_retry_semantics.py | Cost event path mocked but not asserted | Medium | Can miss regressions in cost accounting pipeline. See L-004. |
| Settings upload API contract typing | No direct contract tests | `SettingsFilesDto` expects both `resume` and `profile`, backend upload endpoints return one key | Medium | Type drift can cause downstream misuse and runtime assumptions. See M-006. |

## Recommended Test Suites

### Suite 1: Resume Download Contract + Security

- **Priority:** P0
- **Type:** integration
- **Target Component:** `api/main.py` (`/api/jobs/{job_hash}/resume`)
- **Framework:** pytest
- **Justification:** Endpoint currently uses a fixed filesystem path and lacks explicit access guard behavior under non-default deployment settings (`api/main.py:1479`, `api/main.py:1495`, `api/main.py:1391`). Addresses H-001 and M-002.
- **Scenarios to Cover:**
  - Resume is downloadable when `tailor_runs.artifact_pdf_path` points to non-default output directory.
  - Endpoint returns 404 when DB has no successful artifact row.
  - Endpoint denies/permits access according to configured auth policy.
  - Invalid `job_hash` is rejected consistently.
- **Estimated Test Count:** 6

### Suite 2: Jobs Link Sanitization

- **Priority:** P0
- **Type:** unit
- **Target Component:** `dashboard/src/pages/JobsPage.tsx`
- **Framework:** Vitest + React Testing Library
- **Justification:** External job URL is rendered directly into `<a href>` from scraped data (`dashboard/src/pages/JobsPage.tsx:320`). Addresses M-001.
- **Scenarios to Cover:**
  - `https://` URL renders as clickable link.
  - `http://` URL renders as clickable link.
  - `javascript:` URL is rejected/neutralized.
  - `data:` URL is rejected/neutralized.
  - Missing/invalid URL renders safe fallback text.
- **Estimated Test Count:** 5

### Suite 3: Settings Draft Durability During Sync

- **Priority:** P1
- **Type:** integration
- **Target Component:** `dashboard/src/components/layout/TopBar.tsx`, `dashboard/src/pages/SettingsPage.tsx`
- **Framework:** Vitest + React Testing Library
- **Justification:** Global invalidation plus data-driven draft reset can clobber unsaved edits (`TopBar.tsx:88`, `SettingsPage.tsx:176`, `SettingsPage.tsx:184`). Addresses M-004.
- **Scenarios to Cover:**
  - Unsaved profile draft remains intact after sync-now click.
  - Unsaved resume draft remains intact after sync-now click.
  - Dirty draft prompts before destructive reset.
  - Non-dirty draft updates safely on query refresh.
- **Estimated Test Count:** 6

### Suite 4: Budget Read Path and Contention

- **Priority:** P1
- **Type:** integration
- **Target Component:** `src/database/db_manager.py`, `src/utils/cost_tracking.py`
- **Framework:** pytest
- **Justification:** Budget check path currently performs insert+commit on read calls (`db_manager.py:2459`, `db_manager.py:2489`, `cost_tracking.py:128`). Addresses M-003.
- **Scenarios to Cover:**
  - Repeated `is_budget_exceeded()` calls do not mutate DB in steady state.
  - Concurrent claim checks do not produce avoidable lock contention.
  - Budget defaults initialize correctly without per-read writes.
- **Estimated Test Count:** 5

### Suite 5: API Contract Shape Tests for Settings Uploads

- **Priority:** P1
- **Type:** integration
- **Target Component:** `dashboard/src/lib/api/client.ts`, `dashboard/src/lib/api/types.ts`, `api/main.py`
- **Framework:** pytest (backend contract) + Vitest (frontend type/runtime contract)
- **Justification:** Upload client return types and backend payloads are shape-misaligned (`client.ts:393`, `types.ts:226`, `api/main.py:2586`, `api/main.py:2771`). Addresses M-006.
- **Scenarios to Cover:**
  - Resume upload response shape matches typed contract.
  - Profile upload response shape matches typed contract.
  - Consumer code handles single-metadata payload safely if contract remains split.
- **Estimated Test Count:** 4

### Suite 6: Tailor Worker Loop + Telemetry Assertions

- **Priority:** P2
- **Type:** integration
- **Target Component:** `tests/test_tailor_cli_preflight.py`, `tests/test_apply_worker_and_retry_semantics.py`
- **Framework:** pytest
- **Justification:** Existing tests have gaps in loop behavior validation and cost telemetry assertions (`test_tailor_cli_preflight.py:63`, `test_apply_worker_and_retry_semantics.py:942`). Addresses L-003 and L-004.
- **Scenarios to Cover:**
  - Loop mode executes iteration and sleep ordering under controlled break conditions.
  - Apply worker success path asserts cost event persistence payload.
  - Budget-warning log path includes stage context.
- **Estimated Test Count:** 5

## Suite Priority Definitions

| Priority | Definition                                                                                |
| -------- | ----------------------------------------------------------------------------------------- |
| P0       | Blocks production. Covers Critical/High findings or untested critical paths.              |
| P1       | Should be implemented before next release. Covers Medium findings or core business logic. |
| P2       | Improves confidence. Covers Low findings or secondary paths.                              |
| P3       | Nice to have. Improves maintainability or documents behavior.                             |

## Summary

- Total Recommended Suites: 6
- Total Estimated New Tests: 31
- P0 Suites: 2
- P1 Suites: 3
- P2 Suites: 1
- P3 Suites: 0

Implement P0 suites first because they cover outbound-link safety and resume-download correctness, both of which affect user-facing trust and core workflow integrity. Then execute P1 suites to close data-loss and budget/concurrency risks introduced by recent settings and budget features.

Prerequisite: add frontend test harness support (`vitest`, `@testing-library/react`, `jsdom`) because current automated coverage is Python-centric and leaves dashboard behavior largely untested.
