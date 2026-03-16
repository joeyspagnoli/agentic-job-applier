# Test Plan

## Metadata

- Generated: 2026-03-15T00:00:00Z
- Repo Root: `/Users/jspags/Projects/agentic-job-applier`
- Detected Test Framework(s): pytest, pytest-asyncio
- Overall Test Quality Rating: Adequate

## Existing Test Inventory

| Test File | Framework | Type | Approx. Test Count | Quality | Notes |
| --------- | --------- | ---- | ------------------ | ------- | ----- |
| test_orchestrator_accounting_integrity.py | pytest-asyncio | Integration | 6 | Strong | Crawl metrics accumulation |
| test_scraper_to_agent_integration.py | pytest-asyncio | Integration | 4 | Strong | End-to-end discovery+gate |
| test_resume_tailor_cli_integration.py | pytest-asyncio | Integration | 3 | Adequate | Full tailor CLI flow |
| test_tailor_worker.py | pytest-asyncio | Unit/Integration | 10 | Strong | Tailor DB methods, claim, retry |
| test_apply_decider.py | pytest-asyncio | Unit | 8 | Strong | Gate logic, parsing |
| test_agent_worker_resilience.py | pytest-asyncio | Unit | 6 | Strong | Worker error handling |
| test_orchestrator_failures.py | pytest-asyncio | Integration | 4 | Strong | Failure recovery |
| test_queue_claim_concurrency_and_fairness.py | pytest-asyncio | Concurrency | 5 | Strong | Multi-worker queueing |
| test_time_and_migrations.py | pytest-asyncio | Integration | 5 | Adequate | Schema evolution |
| test_resume_tailor_runtime.py | pytest-asyncio | Unit | 5 | Adequate | Content retry sequencing |
| test_resume_tailor_prompt_contract.py | pytest | Unit | 1 | Adequate | Prompt structure |
| test_resume_tailor_tools_and_renderer.py | pytest-asyncio | Unit | 4 | Adequate | Tool helpers, rendering |
| test_ops_config_and_notifications.py | pytest-asyncio | Unit | 6 | Strong | Config loading, alerts |
| test_status_command_robustness.py | pytest-asyncio | Unit | 4 | Adequate | Status CLI resilience |
| test_dedup_guardrails.py | pytest-asyncio | Unit | 4 | Strong | Deduplication edge cases |
| test_hygiene_hardening.py | pytest-asyncio | Unit | 4 | Adequate | Data validation |
| test_security_and_collection.py | pytest-asyncio | Unit | 2 | Adequate | Security validation |
| test_pipeline_failure_signaling.py | pytest-asyncio | Integration | 3 | Strong | Failure signal flow |
| test_fetcher_failures.py | pytest-asyncio | Unit | 2 | Weak | Only 2 tests for 3 fetchers |
| test_integration.py | pytest-asyncio | Integration | 7 | Adequate | Multi-component flows |
| test_live_agent_e2e.py | pytest | E2E | 1 | Adequate | Opt-in live model test |

## Existing Test Quality Assessment

**Assertion Quality: Strong** — Assertions are specific and behavioral. Examples: `test_tailor_worker.py:126-129` checks both key presence and value type; `test_apply_decider.py` validates parsed decision enums, not just truthiness. Average 2.9 assertions per test.

**Edge Case Coverage: Adequate** — Recent tailor tests cover null claims, double-claims, retry exhaustion, stale PENDING conversion, and failure state reset. Gap: no concurrent claim tests under actual lock contention (only sequential simulation in `test_queue_claim_concurrency_and_fairness.py`).

**Test Isolation: Strong** — Every test uses `tmp_path` fixtures for fresh databases. Async fixtures use `yield` for cleanup. No shared mutable state between tests. 215 targeted mock usages across the suite.

**Mocking Appropriateness: Strong** — Mocks are scoped to external dependencies (pi-mono subprocess, API calls) while preserving real database interactions. `test_tailor_worker.py:340-356` mocks only the pipeline invocation, keeping claim/record logic under real test.

**Naming Clarity: Strong** — Consistent `test_<behavior>_<condition>_<result>` pattern. Examples: `test_claim_returns_none_when_no_qualified_jobs`, `test_double_claim_same_lease_returns_none`.

## Coverage Gap Analysis

### Untested Components

| Component / Module | File(s) | Risk Level | Justification |
| ------------------ | ------- | ---------- | ------------- |
| Fetchers (unit) | `src/fetchers/greenhouse_fetcher.py`, `apify_fetcher.py`, `jobspy_fetcher.py` | Medium | Only 2 failure tests exist; no unit tests for parsing, normalization, or field mapping |
| Shared model builder | `src/agents/shared/model.py` | Low | Simple LiteLLM wrapper; indirectly tested through agent tests |

### Undertested Components

| Component / Module | Existing Tests | Gap Description | Risk Level | Justification |
| ------------------ | -------------- | --------------- | ---------- | ------------- |
| Tailor worker error recovery | test_tailor_worker.py | No test for DB failure during exception handling path | High | See H-005: secondary DB query in except block can throw |
| Concurrent tailor claims | test_tailor_worker.py | Sequential claim tests only; no actual concurrent task testing | Medium | Claim atomicity relies on BEGIN IMMEDIATE but is untested under contention |
| YAML baseline restore | test_tailor_worker.py | Tests mock the pipeline; no test verifies actual file restore after real write | Medium | See H-001: race condition in restore logic |
| process_qualified_jobs CLI | (none) | No tests for argument parsing, preflight checks, or main() orchestration | Medium | CLI is the production entry point |

## Recommended Test Suites

### Suite 1: Tailor Worker Error Recovery

- **Priority:** P0
- **Type:** unit
- **Target Component:** `scripts/process_qualified_jobs.py:326-360`
- **Framework:** pytest-asyncio
- **Justification:** H-005 identifies unhandled DB errors in the exception path. M-003 and M-004 identify file I/O failures that go unrecorded. These are production crash paths.
- **Scenarios to Cover:**
  - DB connection lost during `get_tailor_runs_for_job` in except handler — verify original error is logged
  - `resume_yaml_path.read_text()` raises FileNotFoundError before pipeline starts — verify failure recorded
  - YAML restore in finally block raises PermissionError — verify original error preserved
  - `record_tailor_failure` itself throws during error handling — verify graceful degradation
- **Estimated Test Count:** 4

### Suite 2: Concurrent Tailor Claim Atomicity

- **Priority:** P0
- **Type:** integration
- **Target Component:** `src/database/db_manager.py:1020-1131`
- **Framework:** pytest-asyncio
- **Justification:** H-002 and H-004 affect claim performance. The claim logic uses BEGIN IMMEDIATE but has never been tested under concurrent asyncio tasks.
- **Scenarios to Cover:**
  - Two asyncio tasks call `claim_next_tailor_job` simultaneously — verify no double-claim
  - Three tasks claim from a pool of 2 jobs — verify exactly 2 claims, 1 returns None
  - Claim under simulated lock timeout (busy_timeout exhausted) — verify clean error
  - Claim with stale PENDING rows from crashed workers — verify stale cleanup works
- **Estimated Test Count:** 4

### Suite 3: Path Traversal and Input Validation

- **Priority:** P0
- **Type:** unit
- **Target Component:** `scripts/process_qualified_jobs.py:307-310`, `src/database/db_manager.py:1020`
- **Framework:** pytest-asyncio
- **Justification:** C-001 identifies path traversal via unsanitized job_hash. M-007 identifies missing max_retries validation.
- **Scenarios to Cover:**
  - job_hash containing `../` sequences — verify rejection or sanitization
  - job_hash with null bytes, spaces, or special characters — verify safe handling
  - max_retries = 0 — verify appropriate error or behavior
  - max_retries = -1 — verify rejection
  - Extremely long job_hash (1000+ chars) — verify no filesystem issues
- **Estimated Test Count:** 5

### Suite 4: YAML Baseline Integrity

- **Priority:** P1
- **Type:** integration
- **Target Component:** `scripts/process_qualified_jobs.py:304-360`
- **Framework:** pytest-asyncio
- **Justification:** H-001 identifies a race condition in YAML restore. The baseline read/mutate/restore pattern is central to correctness.
- **Scenarios to Cover:**
  - Single worker: verify YAML is identical before and after successful pipeline run
  - Single worker: verify YAML is restored after pipeline failure
  - YAML file deleted between read and restore — verify error handling
  - YAML file modified externally between read and restore — verify baseline wins
- **Estimated Test Count:** 4

### Suite 5: Tailor Worker CLI and Preflight

- **Priority:** P1
- **Type:** integration
- **Target Component:** `scripts/process_qualified_jobs.py:458-608`
- **Framework:** pytest-asyncio
- **Justification:** The main() function is the production entry point but has zero test coverage. Preflight checks validate external dependencies.
- **Scenarios to Cover:**
  - `--once` mode processes one job and exits
  - `--loop` mode processes jobs and continues polling
  - Missing pi-mono command triggers preflight failure with actionable error
  - Missing latexmk triggers preflight failure
  - Missing database path triggers clean error
  - Invalid TAILOR_MAX_RETRIES env var falls back to default
- **Estimated Test Count:** 6

### Suite 6: Fetcher Unit Tests

- **Priority:** P2
- **Type:** unit
- **Target Component:** `src/fetchers/greenhouse_fetcher.py`, `apify_fetcher.py`, `jobspy_fetcher.py`
- **Framework:** pytest-asyncio
- **Justification:** Fetcher layer has only 2 failure tests across 3 implementations. No parsing or normalization tests exist.
- **Scenarios to Cover:**
  - Greenhouse: parse valid API response into JobPosting with correct field mapping
  - Greenhouse: handle missing optional fields (salary, location) gracefully
  - Apify: parse Workday dataset items with various field formats
  - Apify: handle empty dataset response
  - JobSpy: salary normalization for hourly/monthly/annual
  - JobSpy: handle NaN values in DataFrame columns
- **Estimated Test Count:** 8

## Suite Priority Definitions

| Priority | Definition |
| -------- | ----------------------------------------------------------------------------------------- |
| P0       | Blocks production. Covers Critical/High findings or untested critical paths.              |
| P1       | Should be implemented before next release. Covers Medium findings or core business logic. |
| P2       | Improves confidence. Covers Low findings or secondary paths.                              |
| P3       | Nice to have. Improves maintainability or documents behavior.                             |

## Summary

- Total Recommended Suites: 6
- Total Estimated New Tests: 31
- P0 Suites: 3 (Suites 1, 2, 3)
- P1 Suites: 2 (Suites 4, 5)
- P2 Suites: 1 (Suite 6)
- P3 Suites: 0

Implementation should begin with Suite 3 (path traversal) as it addresses the only Critical finding (C-001), then Suite 1 (error recovery) and Suite 2 (concurrent claims) which cover the High-severity error handling and performance findings. Suite 5 (CLI/preflight) should be prioritized next since it covers the production entry point. All suites use the existing pytest-asyncio infrastructure and can share the `db` fixture pattern from `test_tailor_worker.py`.
