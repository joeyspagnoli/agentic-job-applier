# Test Plan

## Metadata

- Generated: 2026-03-26T15:29:07Z
- Repo Root: /Users/jspags/Projects/agentic-job-applier
- Detected Test Framework(s): pytest
- Overall Test Quality Rating: Adequate

## Existing Test Inventory

| Test File | Framework | Type | Approx. Test Count | Quality | Notes |
| --------- | --------- | ---- | ------------------ | ------- | ----- |
| scripts/test_fetchers.py | manual smoke (not collected) | integration | 0 | Minimal | Explicitly excluded from pytest via `__test__ = False`. |
| tests/test_agent_worker_resilience.py | pytest | integration | 6 | Adequate | Agent worker failure/isolation paths covered. |
| tests/test_apply_decider.py | pytest | unit | 8 | Strong | Good structural assertions and parse-failure tests. |
| tests/test_dedup_guardrails.py | pytest | unit | 4 | Adequate | Dedup behavior checks. |
| tests/test_fetcher_failures.py | pytest | unit | 2 | Adequate | Failure-path fetcher behavior. |
| tests/test_fetcher_units.py | pytest | unit | 8 | Adequate | Deterministic parser normalization checks. |
| tests/test_full_pipeline_e2e.py | pytest | e2e | 3 | Adequate | End-to-end flow checks. |
| tests/test_hygiene_hardening.py | pytest | unit | 4 | Adequate | Meta-guardrail tests. |
| tests/test_integration.py | pytest | integration | 7 | Adequate | DB lifecycle and integration checks. |
| tests/test_live_agent_e2e.py | pytest | e2e | 1 | Adequate | Live-model gated test. |
| tests/test_ops_config_and_notifications.py | pytest | integration | 6 | Adequate | Operational config/notifications behavior. |
| tests/test_orchestrator_accounting_integrity.py | pytest | unit | 6 | Adequate | Orchestrator accounting invariants. |
| tests/test_orchestrator_failures.py | pytest | unit | 4 | Adequate | Orchestrator failure paths. |
| tests/test_pipeline_failure_signaling.py | pytest | unit | 3 | Adequate | Pipeline failure signaling semantics. |
| tests/test_queue_claim_concurrency_and_fairness.py | pytest | integration | 5 | Adequate | Queue/claim concurrency behavior. |
| tests/test_resume_review_prompt_contract.py | pytest | unit | 1 | Adequate | Prompt contract assertions. |
| tests/test_resume_review_runtime.py | pytest | integration | 6 | Strong | Runtime hard-failure boundaries covered. |
| tests/test_resume_review_tools.py | pytest | unit | 5 | Adequate | Tool-level checks. |
| tests/test_resume_tailor_cli_integration.py | pytest | integration | 3 | Adequate | CLI integration path. |
| tests/test_resume_tailor_prompt_contract.py | pytest | unit | 1 | Adequate | Prompt contract assertions. |
| tests/test_resume_tailor_runtime.py | pytest | integration | 6 | Strong | Retry/order/failure semantics covered. |
| tests/test_resume_tailor_tools_and_renderer.py | pytest | unit | 4 | Adequate | Renderer/tools checks. |
| tests/test_review_worker.py | pytest | integration | 6 | Adequate | Review worker behavior. |
| tests/test_scraper_to_agent_integration.py | pytest | integration | 4 | Adequate | Scraper-to-agent integration path. |
| tests/test_security_and_collection.py | pytest | unit | 2 | Adequate | Security guardrail checks are narrow/version-specific. |
| tests/test_status_command_robustness.py | pytest | integration | 4 | Strong | Robust degraded-schema status behavior checks. |
| tests/test_tailor_cli_preflight.py | pytest | integration | 6 | Adequate | Preflight/env parsing checks. |
| tests/test_tailor_concurrent_claims.py | pytest | integration | 4 | Adequate | Tailor claim concurrency behavior. |
| tests/test_tailor_input_validation.py | pytest | unit | 5 | Adequate | Tailor input validation checks. |
| tests/test_tailor_worker.py | pytest | integration | 10 | Adequate | Tailor worker core behavior. |
| tests/test_tailor_worker_error_recovery.py | pytest | integration | 4 | Adequate | Tailor worker recovery checks. |
| tests/test_tailor_yaml_baseline.py | pytest | unit | 4 | Adequate | YAML baseline restoration behavior. |
| tests/test_time_and_migrations.py | pytest | integration | 5 | Adequate | Time-window and agent migration checks. |

## Existing Test Quality Assessment

Representative sample reviewed: 10/32 pytest files (>=30%), plus pattern search across full suite.

- Assertion quality is generally specific and behavior-oriented, e.g. payload structure and parse contracts in `tests/test_apply_decider.py:63-69` and `tests/test_apply_decider.py:193-196`, plus explicit status output checks in `tests/test_status_command_robustness.py:68-69` and `tests/test_status_command_robustness.py:220`.
- Edge-case coverage is good for established subsystems: malformed report/runtime errors in `tests/test_resume_review_runtime.py:215-217` and overflow sequencing in `tests/test_resume_tailor_runtime.py:110-117`.
- Isolation is generally strong: temp DBs and monkeypatching are consistently used (e.g., `tests/test_time_and_migrations.py:35-39`, `tests/test_integration.py:29-33`).
- Mocking is mostly appropriate, but some tests assert wiring rather than full behavior (e.g., heavy monkeypatching in `tests/test_agent_worker_resilience.py:123-130`).
- Naming is clear and scenario-driven in most sampled files.
- Major gap: no direct tests cover newly staged apply worker modules or apply DB claim/retry flow (see findings H-001, H-002, H-003, M-003).

## Coverage Gap Analysis

### Untested Components

| Component / Module | File(s) | Risk Level | Justification |
| ------------------ | ------- | ---------- | ------------- |
| Browser apply orchestration | `src/agents/apply_worker/browser.py` | High | Contains blocking timeout/argument bug path and submit-mode contract drift (H-001, H-003). |
| Apply worker loop and retry scheduling | `scripts/process_apply_jobs.py` | High | Core claim/retry scheduling path is untested and has timestamp compatibility defect (H-002). |
| Apply DB schema/claim persistence | `src/database/db_manager.py` (`migrate_apply_schema`, `claim_next_apply_job`, `record_apply_*`) | High | Critical queue claim/retry semantics introduced without tests (H-002, M-003). |
| Field scan and upload helpers | `src/agents/apply_worker/field_scanner.py`, `src/agents/apply_worker/resume_upload.py` | Medium | Silent exception swallowing and selector correctness concerns need deterministic coverage (L-001). |
| Deploy launcher and units | `deploy/start-chrome-cdp.sh`, `deploy/job-apply-*.service` | Medium | Production boot behavior and hardening assumptions currently untested (H-004, M-001, M-002). |

### Undertested Components

| Component / Module | Existing Tests | Gap Description | Risk Level | Justification |
| ------------------ | -------------- | --------------- | ---------- | ------------- |
| Migration behavior (DB) | `tests/test_time_and_migrations.py` | Covers agent schema migration but not apply schema migration/claim/retry compatibility | High | Apply migration and retry logic added in staged changes; no parity tests (H-002, M-003). |
| Dependency security guardrails | `tests/test_security_and_collection.py` | Version-denylist checks miss newly reported lock CVEs | Medium | `pip-audit` flags vulnerable lock entries not asserted by tests (M-004). |
| Worker CLI contract | No `process_apply_jobs` tests | Missing tests for `--dry-run`/`--no-dry-run` behavior and preflight failure modes | High | Current flag behavior mismatches stated contract (H-003). |

## Recommended Test Suites

### Suite 1: Apply Browser Flow Contract

- **Priority:** P0
- **Type:** integration
- **Target Component:** `src/agents/apply_worker/browser.py`
- **Framework:** pytest + pytest-asyncio
- **Justification:** Prevent production hangs and contract regressions in the highest-risk new path (H-001, H-003; `src/agents/apply_worker/browser.py:54`, `src/agents/apply_worker/browser.py:264-267`, `src/agents/apply_worker/browser.py:327-330`).
- **Scenarios to Cover:**
  - Simplify polling exits on timeout when markers are absent.
  - `page.evaluate` argument plumbing passes deterministic interval/timeout values.
  - `dry_run=False` behavior matches documented CLI contract.
  - Failure path still captures screenshot/DOM artifacts.
- **Estimated Test Count:** 8

### Suite 2: Apply Claim And Retry Semantics

- **Priority:** P0
- **Type:** integration
- **Target Component:** `scripts/process_apply_jobs.py`, `src/database/db_manager.py`
- **Framework:** pytest + pytest-asyncio
- **Justification:** Queue reclaim correctness is core to autonomous operation and currently has a blocking timestamp-format defect (H-002; `scripts/process_apply_jobs.py:180`, `src/database/db_manager.py:1897-1906`).
- **Scenarios to Cover:**
  - Failed run schedules retry and becomes claimable at expected UTC time.
  - Retry cutoff query behaves correctly across timestamp formats.
  - Max-retry terminal path stops further claims.
  - Stale PENDING cleanup restores queue progress.
- **Estimated Test Count:** 10

### Suite 3: Apply Worker CLI And Preflight

- **Priority:** P0
- **Type:** unit
- **Target Component:** `scripts/process_apply_jobs.py`
- **Framework:** pytest + monkeypatch
- **Justification:** Prevent operator-facing behavior mismatches and startup regressions (H-003, H-004; `scripts/process_apply_jobs.py:588-598`, `scripts/process_apply_jobs.py:621-627`, `scripts/process_apply_jobs.py:629-641`).
- **Scenarios to Cover:**
  - `--dry-run` and `--no-dry-run` precedence and effective outcome behavior.
  - Missing `DISPLAY` or unreachable CDP raises preflight errors cleanly.
  - Invalid env values fall back safely.
  - Once vs loop mode processing semantics.
- **Estimated Test Count:** 8

### Suite 4: Deploy Launcher Hardening Contracts

- **Priority:** P1
- **Type:** integration
- **Target Component:** `deploy/start-chrome-cdp.sh`, `deploy/job-apply-chrome.service`, `deploy/job-apply-worker.service`
- **Framework:** pytest (subprocess/text parsing)
- **Justification:** Deployment artifacts currently include ambiguous hardening and non-executable placeholders (H-004, M-001, M-002; `deploy/start-chrome-cdp.sh:21-23`, `deploy/start-chrome-cdp.sh:29`, `deploy/job-apply-worker.service:9-15`).
- **Scenarios to Cover:**
  - Script starts/validates correct display-specific Xvfb behavior.
  - Chrome launch flags include explicit localhost CDP bind.
  - Service files fail validation when placeholders remain.
  - Service environment paths resolve to existing binaries/files.
- **Estimated Test Count:** 6

### Suite 5: Dependency Security Gate

- **Priority:** P1
- **Type:** integration
- **Target Component:** `uv.lock`, CI dependency check step
- **Framework:** pytest wrapper + pip-audit invocation in CI
- **Justification:** Current lock reports known CVEs and existing tests do not detect them comprehensively (M-004; `uv.lock:2819-2820`, `uv.lock:2987-2998`, `uv.lock:3247-3248`).
- **Scenarios to Cover:**
  - Fails when lock includes vulnerabilities above policy threshold.
  - Fails when security-critical packages lag fixed versions.
  - Emits actionable package/version/CVE report artifacts.
- **Estimated Test Count:** 3

### Suite 6: Field Scanner/Upload Resilience

- **Priority:** P2
- **Type:** unit
- **Target Component:** `src/agents/apply_worker/field_scanner.py`, `src/agents/apply_worker/resume_upload.py`
- **Framework:** pytest + Playwright mocks
- **Justification:** Improves diagnosability and metadata correctness for repair workflows (L-001; `src/agents/apply_worker/field_scanner.py:117-122`, `src/agents/apply_worker/field_scanner.py:202-204`, `src/agents/apply_worker/resume_upload.py:96-97`).
- **Scenarios to Cover:**
  - Selector generation matches expected element identity.
  - Cross-origin iframe errors are logged with context.
  - Upload fallback strategy ordering and exit behavior.
- **Estimated Test Count:** 6

## Suite Priority Definitions

| Priority | Definition                                                                                |
| -------- | ----------------------------------------------------------------------------------------- |
| P0       | Blocks production. Covers Critical/High findings or untested critical paths.              |
| P1       | Should be implemented before next release. Covers Medium findings or core business logic. |
| P2       | Improves confidence. Covers Low findings or secondary paths.                              |
| P3       | Nice to have. Improves maintainability or documents behavior.                             |

## Summary

- Total Recommended Suites: 6
- Total Estimated New Tests: 41
- P0 Suites: 3
- P1 Suites: 2
- P2 Suites: 1
- P3 Suites: 0

Implement in this order: (1) browser flow and retry semantics, then (2) CLI contract/preflight, then (3) deployment and dependency gates. This sequence directly burns down blocking release risk first (H-001/H-002/H-003/H-004), then closes medium-risk operational and security regressions.

Before implementing suites, normalize timestamp handling and Simplify polling argument shape so baseline behavior is testable and deterministic. Add CI wiring for `pip-audit` once dependency remediations are applied to keep the risk from re-entering.

## Implementation Status (2026-03-26)

- Implemented `tests/test_apply_worker_and_retry_semantics.py` with coverage for:
  - Simplify polling argument contract and marker-absent completion behavior.
  - Navigation failure classification in browser flow.
  - SQLite-compatible apply retry timestamp formatting.
  - Apply claim eligibility with legacy ISO retry timestamps (due vs future).
  - Max-retry cutoff semantics for apply claim eligibility.
  - Stale PENDING apply-run recovery and re-claim behavior.
  - Structured warning logging in iframe field scan and direct upload fallbacks.
- Implemented `tests/test_apply_chrome_launcher.py` with coverage for:
  - Display-specific Xvfb process and socket checks in `deploy/start-chrome-cdp.sh`.
- Implemented `tests/test_apply_schema_parity.py` with coverage for:
  - Parity check between base `schema.sql` apply DDL and runtime
    `migrate_apply_schema()` DDL output.
- Test execution completed:
  - `uv run pytest -q tests/test_apply_worker_and_retry_semantics.py tests/test_apply_chrome_launcher.py tests/test_apply_schema_parity.py`
  - Result: `11 passed`
