# Bug Report

## Run Metadata

- Repo Root: /Users/jspags/Projects/agentic-job-applier
- Run Timestamp (UTC): 2026-03-14T04:14:33Z

## Severity Criteria

| Severity | Definition                                                                       |
| -------- | -------------------------------------------------------------------------------- |
| Critical | Exploitable in production. Data loss, corruption, or unauthorized access likely. |
| High     | Significant defect in a core flow. Realistic exploitation or failure.            |
| Medium   | Degrades quality, performance, or security posture. Not immediately exploitable. |
| Low      | Code quality or maintainability issue. No direct user or security impact.        |

## Issue Summary

- Total Issues: 19
- Critical: 0
- High: 4
- Medium: 9
- Low: 6

## Findings

### Critical

- None.

### High

#### [H-001] Dedup Hash Can Suppress Distinct Jobs

- **Domain:** Code Quality
- **File:** `src/models/job_posting.py`
- **Line(s):** 63-64
- **Description:** Deduplication hash is built from `company|title|description[:500]` and MD5, which can collapse distinct postings with shared boilerplate intros.
- **Evidence:** `unique_string = f"{self.company.lower()}|{self.title.lower()}|{self.description[:500]}"` then `hashlib.md5(...)`.
- **Impact:** Valid jobs can be silently dropped as duplicates in core ingest flow.
- **Suggested Next Step:** Redesign dedup identity fields (for example include normalized source URL, location, posted date, and full/segmented content strategy) and add collision regression tests.

#### [H-002] Locked Dependencies Include Known CVEs

- **Domain:** Dependencies
- **File:** `uv.lock`
- **Line(s):** 274-275, 481-482, 1800-1801, 2511-2512, 2833-2834
- **Description:** Locked versions include packages reported vulnerable by `pip-audit`.
- **Evidence:** `uv run --with pip-audit pip-audit` reported CVEs in `authlib 1.6.6`, `cryptography 46.0.3`, `markdownify 0.13.1`, `protobuf 6.33.4`, `python-multipart 0.0.21`.
- **Impact:** Known vulnerable components are present in production dependency graph.
- **Suggested Next Step:** Upgrade affected direct/transitive deps and require a passing dependency audit in release gating.

#### [H-003] Insert Path Masks Non-Duplicate Integrity Errors

- **Domain:** Error Handling
- **File:** `src/database/db_manager.py`
- **Line(s):** 137-140
- **Description:** `insert_job` treats any `aiosqlite.IntegrityError` as duplicate hash and returns `False`.
- **Evidence:** `except aiosqlite.IntegrityError: ... return False` with no constraint discrimination.
- **Impact:** Real schema/data integrity failures are silently misclassified and dropped.
- **Suggested Next Step:** Differentiate duplicate-key constraint from other integrity failures and surface/log non-duplicate violations.

#### [H-004] Source Failures Can Be Counted as Success

- **Domain:** Error Handling
- **File:** `src/fetchers/apify_fetcher.py`, `src/fetchers/jobspy_fetcher.py`, `main.py`
- **Line(s):** apify 119-121, 138-140, 166-168; jobspy 143-145, 186-188; main 166-169, 250-253
- **Description:** Fetcher exceptions are converted to empty lists, and orchestrator increments success counters as if crawl completed normally.
- **Evidence:** `except Exception ... return []` in fetchers plus success increments in main after `jobs/new_jobs` processing.
- **Impact:** Reliability metrics and crawl history can underreport actual outages/failures.
- **Suggested Next Step:** Return explicit failure states from fetchers and separate “empty result” from “fetch failed” in orchestrator accounting.

### Medium

#### [M-001] Agent Schema Reliance Is Implicit and Fragile

- **Domain:** Architecture
- **File:** `src/database/schema.sql`, `src/database/db_manager.py`
- **Line(s):** schema 84-89; manager 215-246, 368-421
- **Description:** Agent columns are not in base schema and are required by runtime query paths unless migration runs first.
- **Evidence:** Agent columns are commented in schema and added by `migrate_agent_schema()`.
- **Impact:** Missed migration call can trigger runtime SQL errors in agent-processing flows.
- **Suggested Next Step:** Enforce migration readiness centrally before any agent-column query/update path executes.

#### [M-002] Pytest Suite Collects Manual Smoke Script and Fails

- **Domain:** Code Quality
- **File:** `scripts/test_fetchers.py`
- **Line(s):** 16, 48
- **Description:** Manual network smoke checks are named as pytest tests and are auto-collected in full-suite runs.
- **Evidence:** `uv run pytest -q` failed with 2 failures: async functions in `scripts/test_fetchers.py::test_greenhouse/test_jobspy` not plugin-marked.
- **Impact:** Release gate is unstable/flaky and mixes manual network behavior into automated tests.
- **Suggested Next Step:** Move or rename manual smoke script out of pytest discovery scope and keep automated suite deterministic.

#### [M-003] Critical Runtime Paths Have No Automated Coverage

- **Domain:** Code Quality
- **File:** `main.py`, `src/fetchers/greenhouse_fetcher.py`, `src/fetchers/apify_fetcher.py`, `src/fetchers/jobspy_fetcher.py`
- **Line(s):** main 101-107, 136-138, 254-259, 354-361; greenhouse 110-124; apify 119-140; jobspy 141-160
- **Description:** Orchestrator and fetcher error branches are largely untested.
- **Evidence:** Current automated tests are confined to `tests/test_apply_decider.py` and `tests/test_integration.py` (12 tests total).
- **Impact:** High-risk ingest behavior can regress without detection.
- **Suggested Next Step:** Add integration tests covering source failure accounting and key fetcher failure modes.

#### [M-004] systemd Service Lacks Hardening Controls

- **Domain:** Configuration
- **File:** `deploy/job-discovery.service`
- **Line(s):** 5-17
- **Description:** Service unit does not define common sandbox/hardening directives.
- **Evidence:** No `NoNewPrivileges`, `ProtectSystem`, `ProtectHome`, `PrivateTmp`, or constrained write paths.
- **Impact:** Compromise blast radius is higher if process or dependency is exploited.
- **Suggested Next Step:** Add baseline systemd hardening directives appropriate for file/database needs.

#### [M-005] Dependency Constraints Are Open-Ended and Include Test Tools at Runtime

- **Domain:** Dependencies
- **File:** `pyproject.toml`
- **Line(s):** 9-23 (especially 18-19)
- **Description:** Runtime dependencies are unbounded (`>=`) and include `pytest`/`pytest-asyncio`.
- **Evidence:** Direct dependency list uses lower bounds only and test frameworks are in main dependency set.
- **Impact:** Future lock refreshes can introduce breaking upgrades; production footprint/attack surface is larger than needed.
- **Suggested Next Step:** Bound critical dependency ranges and move test frameworks to a dev dependency group.

#### [M-006] Loop Mode Can Halt on Unhandled Exception

- **Domain:** Error Handling
- **File:** `scripts/process_new_jobs.py`
- **Line(s):** 277-285
- **Description:** Long-running loop has no outer exception guard per cycle.
- **Evidence:** `while True` directly awaits `_process_once` then sleeps, with no protective try/except around loop body.
- **Impact:** One uncaught exception can terminate background processing until manual restart.
- **Suggested Next Step:** Wrap each cycle in resilient error handling and log/retry strategy.

#### [M-007] Failed-Crawl Last-24h Filter Uses Incompatible Timestamp Format

- **Domain:** Error Handling
- **File:** `scripts/status.py`
- **Line(s):** 100-109
- **Description:** Query parameter uses ISO format with `T` while DB timestamps are `CURRENT_TIMESTAMP` format with space separator.
- **Evidence:** `yesterday = (...).isoformat()` used in `WHERE started_at > ?`.
- **Impact:** Failed crawls can be incorrectly excluded from operational status output.
- **Suggested Next Step:** Normalize timestamp format/type for comparison (or compare via SQLite datetime functions consistently).

#### [M-008] Date Filters Mix Semantics and Weaken Query Performance

- **Domain:** Performance
- **File:** `scripts/query_jobs.py`, `scripts/status.py`, `src/database/db_manager.py`
- **Line(s):** query 82; status 48-57; db_manager 551-555
- **Description:** `DATE(fetched_at)` wrapping and mixed UTC/local “today” logic are used across tools.
- **Evidence:** `DATE('now')` in query script vs local `datetime.now()` date strings elsewhere.
- **Impact:** Inconsistent metrics near timezone boundaries and poorer index usage on `fetched_at`.
- **Suggested Next Step:** Standardize one timezone/date-window policy and use index-friendly range predicates.

#### [M-009] Deduplicator Has N+1 DB Lookup Pattern and No In-Batch Dedup

- **Domain:** Performance
- **File:** `src/utils/deduplicator.py`
- **Line(s):** 46-53, 78-80
- **Description:** Each job does an individual DB lookup and there is no in-memory hash-set dedup for current batch.
- **Evidence:** Loop performs `await self.db.get_job_by_hash(job.job_hash)` per item.
- **Impact:** Throughput degrades with larger batches and duplicate rows inside same batch can still hit DB path unnecessarily.
- **Suggested Next Step:** Batch hash existence checks and apply per-batch in-memory dedup set.

### Low

#### [L-001] `--once` Flag Is Parsed but Not Used

- **Domain:** Code Quality
- **File:** `scripts/process_new_jobs.py`
- **Line(s):** 246-248, 263
- **Description:** CLI includes `--once`, but control flow only uses `args.loop`.
- **Evidence:** `should_loop = args.loop`; `args.once` never read.
- **Impact:** CLI contract is misleading.
- **Suggested Next Step:** Either remove `--once` or wire it into explicit mode logic and tests.

#### [L-002] Cross-Script Coupling Uses Private Helpers

- **Domain:** Code Quality
- **File:** `scripts/decide_job.py`
- **Line(s):** 29-31
- **Description:** Script imports underscored internals from another script module.
- **Evidence:** `from scripts.process_new_jobs import _map_status, _run_decider_for_job`.
- **Impact:** Refactors can break CLI behavior unexpectedly.
- **Suggested Next Step:** Move shared logic to stable library module with explicit public API.

#### [L-003] Secret Ignore Coverage Is Narrow

- **Domain:** Configuration
- **File:** `.gitignore`
- **Line(s):** 13-15
- **Description:** Ignore rules cover `.env` but not common variants like `.env.local`/`.env.prod`.
- **Evidence:** Only `.env` and two specific config files are ignored for secrets.
- **Impact:** Variant env files can be accidentally committed.
- **Suggested Next Step:** Add `.env*` ignore with explicit allowlist for `.env.example`.

#### [L-004] Roadmap Section Is Stale Versus Current Capabilities

- **Domain:** Documentation
- **File:** `README.md`
- **Line(s):** 87-99, 293-304
- **Description:** README documents active apply/skip workflow while roadmap still marks Phase 2 as incomplete.
- **Evidence:** Apply/skip usage section exists, but roadmap says “Phase 2” unchecked.
- **Impact:** Contributor/operator expectations can diverge from real system state.
- **Suggested Next Step:** Update roadmap state and release notes to match implemented behavior.

#### [L-005] License Attribution Is Incomplete

- **Domain:** License Compliance
- **File:** `LICENSE`
- **Line(s):** 3
- **Description:** Copyright line lacks owner.
- **Evidence:** `Copyright (c) 2026`
- **Impact:** Legal attribution ambiguity.
- **Suggested Next Step:** Add copyright holder (person or legal entity).

#### [L-006] Runtime `sys.path` Mutation in CLI Scripts

- **Domain:** Security
- **File:** `scripts/process_new_jobs.py`, `scripts/decide_job.py`, `scripts/query_jobs.py`, `scripts/status.py`, `scripts/find_greenhouse_id.py`, `scripts/test_fetchers.py`
- **Line(s):** 29; 21; 19; 11; 12; 10
- **Description:** Multiple scripts prepend repo root to import path at runtime.
- **Evidence:** `sys.path.insert(0, str(Path(__file__).parent.parent))`.
- **Impact:** Import resolution becomes less deterministic and broadens module-hijack surface in misconfigured environments.
- **Suggested Next Step:** Prefer package/module execution patterns that avoid runtime path mutation.

## Analysis Coverage

| Analysis Domain    | Status      | Files Reviewed | Notes |
| ------------------ | ----------- | -------------- | ----- |
| Code Quality       | ✅ Complete | 37             | All first-party Python/SQL code paths reviewed; key risks captured. |
| Security           | ✅ Complete | 43             | Secret scans + unsafe pattern scans + dependency vulnerability audit executed. |
| Performance        | ✅ Complete | 37             | Query, dedup, and workflow throughput hotspots identified. |
| Error Handling     | ✅ Complete | 31             | Exception handling, failure propagation, and resilience paths reviewed. |
| Architecture       | ✅ Complete | 37             | Module boundaries, orchestration flow, and schema/runtime coupling reviewed. |
| Dependencies       | ✅ Complete | 2              | `pyproject.toml` + `uv.lock` analyzed; `pip-audit` executed. |
| License Compliance | ✅ Complete | 3              | License presence/consistency checked; attribution gap noted. |
| Configuration      | ✅ Complete | 9              | `.env.example`, `.gitignore`, deploy units, and config YAML reviewed. |
| Documentation      | ✅ Complete | 5              | README/AGENTS/spec index/deploy docs reviewed for freshness/completeness. |
