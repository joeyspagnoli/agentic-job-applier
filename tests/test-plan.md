# Test Plan

## Metadata

- Generated: 2026-03-14T04:14:33Z
- Repo Root: /Users/jspags/Projects/agentic-job-applier
- Detected Test Framework(s): pytest, pytest-asyncio
- Overall Test Quality Rating: Weak

## Existing Test Inventory

| Test File | Framework | Type | Approx. Test Count | Quality | Notes |
| --------- | --------- | ---- | ------------------ | ------- | ----- |
| tests/test_apply_decider.py | pytest + pytest-asyncio | unit + integration | 5 | Adequate | Strong DB-persistence checks for success/failure paths, but heavy monkeypatching bypasses core ADK runtime path (`_run_decider_for_job`). |
| tests/test_integration.py | pytest + pytest-asyncio | integration + unit | 7 | Adequate | Covers DB lifecycle and model normalization basics, but not orchestrator/fetcher runtime behavior. |
| scripts/test_fetchers.py | pytest (accidentally collected) | manual smoke (network) | 2 | Weak | Named as tests and uses `async def` without pytest async markers; breaks full-suite `pytest` runs and performs live network calls. |

## Existing Test Quality Assessment

Assertion quality is mostly specific in `tests/test_apply_decider.py` and `tests/test_integration.py` (for example status/result payload checks in `tests/test_apply_decider.py:187-194` and DB row checks in `tests/test_integration.py:131-139`). Test names are generally clear and scenario-oriented.

Major quality gaps remain. The highest-risk one is that core decider runtime behavior is mocked out in both batch tests (`tests/test_apply_decider.py:164`, `tests/test_apply_decider.py:228`), so streamed event parsing and empty-response error handling in production code (`scripts/process_new_jobs.py:120-152`) are unverified. Parser coverage is partial (`tests/test_apply_decider.py:63-119`) and misses key recovery/failure branches (`src/agents/root_apply_decider/agent.py:47-81`, `src/agents/root_apply_decider/agent.py:151`). Finally, `scripts/test_fetchers.py:16-48` is unintentionally discoverable as pytest tests and causes suite instability.

## Coverage Gap Analysis

### Untested Components

| Component / Module | File(s) | Risk Level | Justification |
| ------------------ | ------- | ---------- | ------------- |
| Discovery orchestrator error accounting and aggregation | main.py | High | No automated tests cover source-failure accounting, APIFY-token skip behavior, or daily stats aggregation (`main.py:101-107`, `main.py:136-138`, `main.py:254-259`, `main.py:354-361`). See H-002, M-007. |
| Greenhouse and Apify fetcher failure handling | src/fetchers/greenhouse_fetcher.py, src/fetchers/apify_fetcher.py | High | HTTP/network and actor/dataset failure branches are not validated by automated tests (`src/fetchers/greenhouse_fetcher.py:110-124`, `src/fetchers/apify_fetcher.py:119-140`). See H-002, M-007. |
| Dependency security gate | pyproject.toml, uv.lock | High | No automated policy test blocks known-CVE dependency sets (`uv.lock:274`, `uv.lock:481`, `uv.lock:1800`, `uv.lock:2511`, `uv.lock:2833`). See H-001. |
| CLI status time-window logic | scripts/status.py | Medium | No tests for 24h failed-crawl query semantics (`scripts/status.py:100-109`) despite format mismatch risk. See M-002, M-003. |
| DB migration preconditions for agent columns | src/database/db_manager.py, src/database/schema.sql | Medium | No tests assert behavior when agent queries run before migration (`src/database/db_manager.py:215-246`, `src/database/db_manager.py:368-421`, `src/database/schema.sql:84-89`). See M-004. |

### Undertested Components

| Component / Module | Existing Tests | Gap Description | Risk Level | Justification |
| ------------------ | -------------- | --------------- | ---------- | ------------- |
| Apply-decider parser and runtime integration | tests/test_apply_decider.py | Covers JSON and plain-text happy paths only; does not cover malformed embedded JSON scanning and unrecoverable path beyond one injected error. | High | Core decision recovery logic spans `src/agents/root_apply_decider/agent.py:47-151`; current tests bypass runtime event parsing in `scripts/process_new_jobs.py:120-152`. See M-007. |
| Deduplication correctness and performance behavior | tests/test_integration.py | Covers only simple duplicate/non-duplicate scenario; no in-batch duplicates, collision-like cases, or scale behavior. | High | Risk of false dedup suppression and inefficient lookup pattern (`src/models/job_posting.py:63-64`, `src/utils/deduplicator.py:46-53`, `src/database/db_manager.py:137-140`). See H-003, H-004, M-005. |
| Agent batch loop resilience | tests/test_apply_decider.py | No coverage of `--loop` long-running mode exceptions and retry resilience. | Medium | Unhandled exceptions can terminate worker loop (`scripts/process_new_jobs.py:277-285`). See M-001. |
| Query/status date semantics | none | No tests for timezone consistency or index-preserving date windows. | Medium | Mixed semantics across `DATE('now')` and local time paths (`scripts/query_jobs.py:82`, `scripts/status.py:48-57`, `src/database/db_manager.py:551-555`). See M-003. |

## Recommended Test Suites

### Suite 1: Orchestrator Failure Accounting

- **Priority:** P0
- **Type:** integration
- **Target Component:** `main.py`
- **Framework:** pytest + pytest-asyncio
- **Justification:** Prevent silent source failures being counted as success by asserting crawl status/metrics transitions in orchestrator branches (`main.py:101-107`, `main.py:166-169`, `main.py:254-259`), tied to H-002 and M-007.
- **Scenarios to Cover:**
  - Greenhouse/Apify/JobSpy fetch exceptions increment `sources_failed`.
  - Empty-but-successful fetch does not mask transport/actor failure.
  - APIFY token missing branch returns deterministic counters.
  - Daily stats row reflects aggregate totals after mixed pass/fail crawls.
- **Estimated Test Count:** 8

### Suite 2: Dedup and Insert Integrity Guardrails

- **Priority:** P0
- **Type:** integration
- **Target Component:** `src/models/job_posting.py`, `src/utils/deduplicator.py`, `src/database/db_manager.py`
- **Framework:** pytest + pytest-asyncio
- **Justification:** Protect core storage correctness against false dedup and masked insert errors (`src/models/job_posting.py:63-64`, `src/database/db_manager.py:137-140`, `src/utils/deduplicator.py:46-53`) tied to H-003, H-004, M-005.
- **Scenarios to Cover:**
  - Similar jobs with distinct identities are not incorrectly collapsed.
  - Non-duplicate integrity errors surface distinctly from duplicate hash conflicts.
  - In-batch duplicate rows are filtered before DB writes.
  - Large batch dedup path keeps query counts bounded.
- **Estimated Test Count:** 10

### Suite 3: Agent Worker Resilience and Loop Safety

- **Priority:** P1
- **Type:** integration
- **Target Component:** `scripts/process_new_jobs.py`
- **Framework:** pytest + pytest-asyncio
- **Justification:** Ensure polling worker does not stop on transient failures and preserves expected per-cycle behavior (`scripts/process_new_jobs.py:174-181`, `scripts/process_new_jobs.py:277-285`) tied to M-001 and M-007.
- **Scenarios to Cover:**
  - `_process_once` exception in loop mode does not terminate process lifecycle.
  - Model-not-configured path logs and safely skips batch.
  - Missing `job_hash` path is handled without side effects.
  - SKIP decision maps to `FILTERED` status.
- **Estimated Test Count:** 7

### Suite 4: Date/Time Query Semantics

- **Priority:** P1
- **Type:** unit
- **Target Component:** `scripts/status.py`, `scripts/query_jobs.py`, `src/database/db_manager.py`
- **Framework:** pytest
- **Justification:** Fix inconsistent operational metrics and time-window errors in status/query tools (`scripts/status.py:100-109`, `scripts/query_jobs.py:82`, `src/database/db_manager.py:551-555`) tied to M-002 and M-003.
- **Scenarios to Cover:**
  - 24h failed-crawl filter matches intended window boundaries.
  - “Today” counts align across status/query/db helpers under timezone edge cases.
  - Date filtering strategy preserves expected index usage assumptions.
- **Estimated Test Count:** 6

### Suite 5: Migration Preconditions and Agent Columns

- **Priority:** P1
- **Type:** integration
- **Target Component:** `src/database/db_manager.py`, `src/database/schema.sql`
- **Framework:** pytest + pytest-asyncio
- **Justification:** Prevent runtime SQL failures from migration ordering assumptions (`src/database/db_manager.py:215-246`, `src/database/db_manager.py:368-421`, `src/database/schema.sql:84-89`) tied to M-004.
- **Scenarios to Cover:**
  - Agent query methods fail loudly before migration and pass after migration.
  - `migrate_agent_schema()` is idempotent across repeated runs.
  - Index creation for agent columns exists after migration.
- **Estimated Test Count:** 5

### Suite 6: Test Discovery and Dependency Security Gates

- **Priority:** P0
- **Type:** integration
- **Target Component:** `scripts/test_fetchers.py`, `pyproject.toml`, `uv.lock`
- **Framework:** pytest + CI command assertions (`uv run pytest`, `uv run --with pip-audit pip-audit`)
- **Justification:** Keep release gate stable and block known vulnerable dependency sets (`scripts/test_fetchers.py:16-48`, `uv.lock:274`, `uv.lock:481`, `uv.lock:1800`, `uv.lock:2511`, `uv.lock:2833`) tied to H-001 and M-006.
- **Scenarios to Cover:**
  - Automated pytest command excludes manual smoke tests.
  - CI fails on high-severity `pip-audit` findings.
  - Runtime dependencies exclude test-only packages.
- **Estimated Test Count:** 4

## Suite Priority Definitions

| Priority | Definition                                                                                |
| -------- | ----------------------------------------------------------------------------------------- |
| P0       | Blocks production. Covers Critical/High findings or untested critical paths.              |
| P1       | Should be implemented before next release. Covers Medium findings or core business logic. |
| P2       | Improves confidence. Covers Low findings or secondary paths.                              |
| P3       | Nice to have. Improves maintainability or documents behavior.                             |

## Summary

- Total Recommended Suites: 6
- Total Estimated New Tests: 40
- P0 Suites: 3
- P1 Suites: 3
- P2 Suites: 0
- P3 Suites: 0

Implementation order should start with P0 suites that directly gate production safety: dependency security gate, orchestrator failure accounting, and dedup/insert integrity. Those suites cover the highest-risk pathways where the system can silently miss failures or suppress valid jobs.

After that, implement P1 suites for worker-loop resilience, date/time query correctness, and migration-precondition enforcement. These reduce operational drift and runtime fragility and should be completed before the next release candidate is approved.
