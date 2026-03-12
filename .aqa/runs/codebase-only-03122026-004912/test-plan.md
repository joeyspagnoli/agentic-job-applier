# Test Plan

## Metadata

- Generated: 2026-03-12T04:53:00Z
- Repo Root: /Users/josephspagnoli/Projects/agentic-job-applier
- Detected Test Framework(s): Pytest
- Overall Test Quality Rating: Minimal

## Existing Test Inventory

| Test File | Framework | Type | Approx. Test Count | Quality | Notes |
| --------- | --------- | ---- | ------------------ | ------- | ----- |
| tests/test_integration.py | Pytest | Integration/unit mix | ~5 | Adequate for covered paths | Covers DatabaseManager lifecycle, dedup filtering, crawl tracking, JobPosting hash/normalization using temp SQLite DB [tests/test_integration.py:1-111] |

## Existing Test Quality Assessment

The existing pytest suite verifies basic database creation, insert/duplicate handling, dedup filtering, crawl tracking, and JobPosting normalization. Assertions are specific and use isolated temp DBs, but no error-path or network/fetcher scenarios are exercised. Fetchers, orchestrator flows, CLI scripts, and the ADK agent pipeline are untested, leaving key behaviors unchecked (e.g., config handling, salary interval normalization, model wiring). [tests/test_integration.py:12-111]

## Coverage Gap Analysis

### Untested Components

| Component / Module | File(s) | Risk Level | Justification |
| ------------------ | ------- | ---------- | ------------- |
| ADK agent apply/skip pipeline | src/agents/root_apply_decider.py; scripts/process_new_jobs.py | High | Stubbed model currently disables processing (H-001); no tests to catch missing model wiring or session output handling. |
| Deployment service configuration | deploy/job-discovery.service | High | Placeholder paths/venv/env cause scheduled runs to fail (H-002); no automated check to prevent shipping invalid service files. |
| Status and query CLIs | scripts/status.py; scripts/query_jobs.py | Medium | Hardcoded DB path ignores `DATABASE_PATH`, leading to monitoring/query failures on custom deployments (M-001, M-002). |
| JobSpy salary normalization | src/fetchers/jobspy_fetcher.py | Medium | Case-sensitive interval parsing skews salary data (M-003); no tests for interval variants. |
| Orchestrator end-to-end fetch cycle | main.py | Medium | No integration coverage for multi-source fetch flow, error handling, or daily stats updates. |

### Undertested Components

| Component / Module | Existing Tests | Gap Description | Risk Level | Justification |
| ------------------ | -------------- | --------------- | ---------- | ------------- |
| DatabaseManager & Deduplicator | tests/test_integration.py | Only happy-path lifecycle/duplicate checks; lacks concurrency, error handling, and schema migration coverage | Medium | Core persistence layer; regressions could corrupt data or skip crawls.

## Recommended Test Suites

### Suite 1: ADK agent pipeline wiring
- **Priority:** P0
- **Type:** integration
- **Target Component:** `scripts/process_new_jobs.py`, `src/agents/root_apply_decider.py`
- **Framework:** Pytest (async)
- **Justification:** Prevent silent skips when the model is missing and validate apply/skip processing end-to-end (see H-001; scripts/process_new_jobs.py:156-165; src/agents/root_apply_decider.py:51-68).
- **Scenarios to Cover:**
  - Processing exits with clear error when `get_decider_model` returns stub/raises.
  - Injected mock model produces decision persisted via `record_agent_decision` for NEW jobs.
  - Agent output missing `DECIDER_OUTPUT_KEY` triggers failure path and marks job as failed.
- **Estimated Test Count:** 4

### Suite 2: Deployment service validation
- **Priority:** P1
- **Type:** unit
- **Target Component:** `deploy/job-discovery.service`
- **Framework:** Pytest (file parsing) or shell-based check
- **Justification:** Ensure packaged service files have real user/paths and venv/env loading to avoid broken scheduled runs (see H-002; deploy/job-discovery.service:7-10).
- **Scenarios to Cover:**
  - Assert placeholders (`YOUR_USERNAME`, `/path/to/`) are absent before release.
  - Validate ExecStart points to project venv or configured interpreter.
  - Validate Environment/EnvironmentFile is present for `.env`.
- **Estimated Test Count:** 3

### Suite 3: Config-aware CLIs (status/query)
- **Priority:** P1
- **Type:** unit/integration
- **Target Component:** `scripts/status.py`, `scripts/query_jobs.py`
- **Framework:** Pytest
- **Justification:** Ensure CLI tools honor `DATABASE_PATH` and load `.env` to prevent false "Database not found" errors (M-001, M-002; scripts/status.py:16-25; scripts/query_jobs.py:21-37).
- **Scenarios to Cover:**
  - With custom DATABASE_PATH env, scripts connect successfully and read counts from temp DB.
  - Default path still works when env unset.
  - Missing DB surfaces actionable error message.
- **Estimated Test Count:** 4

### Suite 4: JobSpy salary normalization variants
- **Priority:** P1
- **Type:** unit
- **Target Component:** `src/fetchers/jobspy_fetcher.py`
- **Framework:** Pytest
- **Justification:** Prevent incorrect annualization for mixed-case or prefixed interval values (M-003; src/fetchers/jobspy_fetcher.py:143-199).
- **Scenarios to Cover:**
  - Intervals "Hourly", "Per Year", "per month" map to expected multipliers after normalization.
  - Unknown intervals fall back to default with logged warning.
  - min/max None handling remains unchanged.
- **Estimated Test Count:** 3

### Suite 5: DatabaseManager resilience
- **Priority:** P2
- **Type:** unit/integration
- **Target Component:** `src/database/db_manager.py`
- **Framework:** Pytest (async)
- **Justification:** Extend existing coverage to error conditions and migration paths to guard persistence integrity (gap noted; tests/test_integration.py:12-82).
- **Scenarios to Cover:**
  - Busy timeout / WAL settings applied on connect.
  - Migration `migrate_agent_schema` idempotency.
  - Duplicate insert paths under concurrent calls.
- **Estimated Test Count:** 4

## Suite Priority Definitions

| Priority | Definition                                                                                |
| -------- | ----------------------------------------------------------------------------------------- |
| P0       | Blocks production. Covers Critical/High findings or untested critical paths.              |
| P1       | Should be implemented before next release. Covers Medium findings or core business logic. |
| P2       | Improves confidence. Covers Low findings or secondary paths.                              |
| P3       | Nice to have. Improves maintainability or documents behavior.                             |

## Summary

- Total Recommended Suites: 5
- Total Estimated New Tests: 18
- P0 Suites: 1
- P1 Suites: 3
- P2 Suites: 1
- P3 Suites: 0

Implement Suite 1 immediately to restore the agent pipeline and prevent silent skips. Suites 2–4 should follow to harden deployment and configuration correctness before the next release. Suite 5 then deepens persistence resilience. Use Pytest with async support and temp DBs to keep runs isolated and fast.
