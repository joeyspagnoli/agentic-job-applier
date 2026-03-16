# Bug Report

## Run Metadata

- Repo Root: `/Users/jspags/Projects/agentic-job-applier`
- Run Timestamp (UTC): 2026-03-15T00:00:00Z
- Focus: Tailor worker feature (scripts/process_qualified_jobs.py, src/database/db_manager.py tailor methods, deploy/job-tailor-worker.service, tests/test_tailor_worker.py, schema.sql tailor_runs table)

## Severity Criteria

| Severity | Definition |
| -------- | -------------------------------------------------------------------------------- |
| Critical | Exploitable in production. Data loss, corruption, or unauthorized access likely. |
| High     | Significant defect in a core flow. Realistic exploitation or failure.            |
| Medium   | Degrades quality, performance, or security posture. Not immediately exploitable. |
| Low      | Code quality or maintainability issue. No direct user or security impact.        |

## Issue Summary

- Total Issues: 18
- Critical: 1
- High: 5
- Medium: 8
- Low: 4

## Findings

### Critical

#### [C-001] Path Traversal via Unsanitized job_hash in Output Directory Construction

- **Domain:** Security
- **File:** `scripts/process_qualified_jobs.py`
- **Line(s):** 307-310
- **Description:** The `job_hash` value from the database is used directly to construct a filesystem path (`output_base_dir / job_hash`) without validating it matches the expected hex format. A compromised data source or SQL injection elsewhere could inject path traversal sequences (e.g., `../../etc/cron.d/malicious`).
- **Evidence:**
  ```python
  run_dir = output_base_dir / job_hash
  run_dir.mkdir(parents=True, exist_ok=True)
  ```
- **Impact:** Arbitrary directory creation and file writes outside the intended output directory. Could lead to code execution if combined with writable system paths.
- **Suggested Next Step:** Validate `job_hash` format with `re.match(r'^[a-f0-9]{32,}$', job_hash)` before constructing the path.

### High

#### [H-001] YAML Baseline Race Condition Under Concurrent Workers

- **Domain:** Error Handling
- **File:** `scripts/process_qualified_jobs.py`
- **Line(s):** 304, 358-360
- **Description:** The resume YAML file is read into memory, mutated by the pipeline, then restored in a `finally` block. If multiple tailor workers run concurrently (supported by the claim-based design), both read the same baseline, both mutate, and both restore — causing silent data loss of the other worker's intended state.
- **Evidence:**
  ```python
  yaml_baseline = resume_yaml_path.read_text(encoding="utf-8")  # line 304
  # ... pipeline modifies the file ...
  finally:
      resume_yaml_path.write_text(yaml_baseline, encoding="utf-8")  # line 360
  ```
- **Impact:** Silent resume content corruption when workers overlap. The single-worker design mitigates this today, but the DB claim logic explicitly supports concurrent workers.
- **Suggested Next Step:** Use `fcntl.flock()` file locking or copy the YAML to a per-run temp file and operate on the copy.

#### [H-002] Redundant Subqueries in claim_next_tailor_job Degrade Performance

- **Domain:** Performance
- **File:** `src/database/db_manager.py`
- **Line(s):** 1069-1088
- **Description:** The candidate selection query contains three separate `SELECT MAX(tr.next_retry_at)` subqueries against the same table and conditions. Each scans `tailor_runs` independently.
- **Evidence:**
  ```sql
  AND (
      NOT EXISTS (SELECT 1 FROM tailor_runs tr WHERE ...)
      OR (SELECT MAX(tr.next_retry_at) FROM tailor_runs tr WHERE ...) IS NULL
      OR (SELECT MAX(tr.next_retry_at) FROM tailor_runs tr WHERE ...) <= datetime('now')
  )
  ```
- **Impact:** Query performance degrades linearly with tailor_runs growth. Under high retry volumes, claim latency increases.
- **Suggested Next Step:** Consolidate into a single subquery: `OR COALESCE((SELECT MAX(...)), datetime('now')) <= datetime('now')`.

#### [H-003] N+1 Query Pattern in Failure Retry Counting

- **Domain:** Performance
- **File:** `scripts/process_qualified_jobs.py`
- **Line(s):** 333-336, 379-380
- **Description:** Every time a tailor job fails, `get_tailor_runs_for_job()` fetches ALL runs, then Python counts FAILED ones. This should be a single `SELECT COUNT(*)` query.
- **Evidence:**
  ```python
  failed_runs = await db.get_tailor_runs_for_job(job_hash)
  failed_count = sum(1 for r in failed_runs if r["status"] == "FAILED") + 1
  ```
- **Impact:** Unnecessary data transfer and memory allocation in the error path, where performance matters most.
- **Suggested Next Step:** Add a `get_tailor_failure_count(job_hash) -> int` method to DatabaseManager.

#### [H-004] Missing Compound Index on (job_hash, status) for tailor_runs

- **Domain:** Performance
- **File:** `src/database/db_manager.py`
- **Line(s):** 979-984
- **Description:** The claim query filters on `(job_hash, status)` pairs across multiple NOT EXISTS subqueries, but only single-column indexes exist.
- **Evidence:**
  ```sql
  CREATE INDEX IF NOT EXISTS idx_tailor_runs_job_hash ON tailor_runs(job_hash);
  CREATE INDEX IF NOT EXISTS idx_tailor_runs_status ON tailor_runs(status);
  -- Missing: CREATE INDEX idx_tailor_runs_job_status ON tailor_runs(job_hash, status);
  ```
- **Impact:** Full table scans on `tailor_runs` for each NOT EXISTS subquery during claim. Performance degrades as run history grows.
- **Suggested Next Step:** Add `CREATE INDEX IF NOT EXISTS idx_tailor_runs_job_status ON tailor_runs(job_hash, status);` to the migration.

#### [H-005] Unhandled Database Errors in Exception Recovery Path

- **Domain:** Error Handling
- **File:** `scripts/process_qualified_jobs.py`
- **Line(s):** 333, 379
- **Description:** Inside the `except Exception` handler, `db.get_tailor_runs_for_job()` is called without error handling. If the database connection is lost (which may be the original cause of failure), this secondary query throws, masking the original error.
- **Evidence:**
  ```python
  except Exception as exc:
      logger.error("Tailor pipeline raised for {}: {}", job_hash, exc)
      failed_runs = await db.get_tailor_runs_for_job(job_hash)  # can throw
  ```
- **Impact:** Original failure error is lost; failure is not recorded in the database; job becomes stuck in PENDING until stale cleanup.
- **Suggested Next Step:** Wrap the recovery query in its own try/except with fallback behavior.

### Medium

#### [M-001] SQL Injection Vector in PRAGMA Statement (Mitigated)

- **Domain:** Security
- **File:** `src/database/db_manager.py`
- **Line(s):** 94
- **Description:** PRAGMA journal_mode is set via f-string. Although validated against a whitelist, this is fragile — future changes removing the validation would expose SQL injection.
- **Evidence:**
  ```python
  await self.conn.execute(f"PRAGMA journal_mode = {journal_mode}")
  ```
- **Impact:** Currently safe due to whitelist. Risk increases if validation is refactored away.
- **Suggested Next Step:** Use a dictionary mapping to literal SQL strings instead of f-string interpolation.

#### [M-002] Duplicated Retry Calculation Logic

- **Domain:** Code Quality
- **File:** `scripts/process_qualified_jobs.py`
- **Line(s):** 333-350 and 378-403
- **Description:** The retry count calculation and `_calculate_next_retry_at` invocation appear in two nearly identical blocks — one in the pipeline exception handler and one in the page-overflow failure path.
- **Evidence:** Both blocks call `get_tailor_runs_for_job`, count failures, calculate backoff, and call `record_tailor_failure` with the same structure.
- **Impact:** Maintenance burden; fixing a bug in one path but not the other introduces inconsistency.
- **Suggested Next Step:** Extract a `_handle_tailor_failure(db, run_id, job_hash, error, ...)` helper.

#### [M-003] YAML File Read Has No Error Handling

- **Domain:** Error Handling
- **File:** `scripts/process_qualified_jobs.py`
- **Line(s):** 304
- **Description:** `resume_yaml_path.read_text()` is called without try/except. If the file is missing or unreadable, the exception propagates before the pipeline starts, meaning no failure is recorded for the claimed job.
- **Evidence:**
  ```python
  yaml_baseline = resume_yaml_path.read_text(encoding="utf-8")
  ```
- **Impact:** Job claimed but failure not recorded; job stuck in PENDING until stale cleanup.
- **Suggested Next Step:** Wrap in try/except and call `record_tailor_failure` before re-raising.

#### [M-004] Finally Block File Write Can Mask Original Exception

- **Domain:** Error Handling
- **File:** `scripts/process_qualified_jobs.py`
- **Line(s):** 358-360
- **Description:** The `finally` block writes the YAML baseline back to disk. If this write fails (disk full, permissions), it raises a new exception that masks the original pipeline error.
- **Evidence:**
  ```python
  finally:
      resume_yaml_path.write_text(yaml_baseline, encoding="utf-8")
  ```
- **Impact:** Original failure reason lost in logs and database.
- **Suggested Next Step:** Wrap the restore in its own try/except with a warning log.

#### [M-005] Systemd Service Missing Resource Limits

- **Domain:** Configuration
- **File:** `deploy/job-tailor-worker.service`
- **Line(s):** 15-36
- **Description:** The systemd unit has good security hardening but lacks resource limits (`MemoryMax`, `CPUQuota`, `TasksMax`). The tailor worker runs pi-mono (a coding agent) which could consume unbounded memory or CPU.
- **Evidence:** No `MemoryMax`, `CPUQuota`, or `TasksMax` directives present.
- **Impact:** A runaway pi-mono process could exhaust server resources and affect other services.
- **Suggested Next Step:** Add `MemoryMax=4G`, `CPUQuota=200%`, `TasksMax=64` (or appropriate limits).

#### [M-006] Exception Messages Stored Unsanitized in Database

- **Domain:** Security
- **File:** `scripts/process_qualified_jobs.py`
- **Line(s):** 354
- **Description:** `str(exc)` is stored directly in the `error` column. If the exception contains file paths, API responses, or credentials from upstream errors, this sensitive data persists in the database.
- **Evidence:**
  ```python
  await db.record_tailor_failure(run_id=run_id, error=str(exc), ...)
  ```
- **Impact:** Information disclosure if the database is accessed by unauthorized parties.
- **Suggested Next Step:** Truncate and sanitize error messages before storage (e.g., first 500 chars, strip paths).

#### [M-007] No Validation on max_retries Parameter

- **Domain:** Error Handling
- **File:** `src/database/db_manager.py`
- **Line(s):** 1020-1023
- **Description:** `max_retries` is used directly in the SQL WHERE clause without validation. A negative or zero value produces unexpected query behavior (no jobs ever eligible, or all jobs always eligible).
- **Evidence:**
  ```python
  async def claim_next_tailor_job(self, *, max_retries: int, ...) -> Optional[dict]:
      # max_retries used directly: ... < ?
  ```
- **Impact:** Misconfigured `TAILOR_MAX_RETRIES=0` silently disables all tailoring.
- **Suggested Next Step:** Add `if max_retries < 1: raise ValueError(...)` at function entry.

#### [M-008] Config Directory Unnecessarily Writable in Systemd Unit

- **Domain:** Configuration
- **File:** `deploy/job-tailor-worker.service`
- **Line(s):** 27
- **Description:** `ReadWritePaths` includes the config directory. The tailor worker needs write access for YAML baseline restore, but this also grants write access to all config files.
- **Evidence:**
  ```ini
  ReadWritePaths=.../data .../logs .../config
  ```
- **Impact:** If the service is compromised, the attacker can modify configuration files including company targets.
- **Suggested Next Step:** Move the YAML working copy to `data/` and remove config from `ReadWritePaths`.

### Low

#### [L-001] Claim Token Uses 96 Bits Instead of 256 Bits

- **Domain:** Security
- **File:** `src/database/db_manager.py`
- **Line(s):** 1044
- **Description:** `os.urandom(12).hex()` generates a 96-bit token. While adequate for a local SQLite queue, 256 bits is the standard for cryptographic tokens.
- **Evidence:**
  ```python
  claim_token = os.urandom(12).hex()
  ```
- **Impact:** Negligible for single-server deployment. Would matter if tokens were exposed over a network.
- **Suggested Next Step:** Increase to `os.urandom(32).hex()` for defense-in-depth.

#### [L-002] Missing Claim Success Logging

- **Domain:** Configuration
- **File:** `src/database/db_manager.py`
- **Line(s):** 1020-1131
- **Description:** `claim_next_tailor_job` does not log successful claims. Only failures and empty queues are observable without database inspection.
- **Evidence:** No `logger.info(...)` call after successful claim and commit.
- **Impact:** Operational visibility gap; harder to audit job processing history from logs alone.
- **Suggested Next Step:** Add `logger.info("Claimed tailor job: job_hash={} run_id={}", job_hash, run_row["id"])` after commit.

#### [L-003] Database Directory Created with Default Permissions

- **Domain:** Security
- **File:** `src/database/db_manager.py`
- **Line(s):** 72
- **Description:** `Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)` uses default permissions (typically 0o755), making the database directory world-readable.
- **Evidence:**
  ```python
  Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
  ```
- **Impact:** On shared systems, other users could read the SQLite database containing job data and error messages.
- **Suggested Next Step:** Add `mode=0o700` to the `mkdir` call.

#### [L-004] deploy/README.md Does Not Document Tailor Worker

- **Domain:** Documentation
- **File:** `deploy/README.md`
- **Line(s):** (entire file)
- **Description:** The deploy README documents the discovery timer, gate worker, and alert hook but does not mention `job-tailor-worker.service`. Operators reading the deploy docs will miss this service.
- **Evidence:** No reference to `job-tailor-worker.service` in `deploy/README.md`.
- **Impact:** Operator confusion during deployment; tailor worker may be overlooked.
- **Suggested Next Step:** Add a section documenting the tailor worker service, its prerequisites, and configuration.

## Analysis Coverage

| Analysis Domain    | Status      | Files Reviewed | Notes |
| ------------------ | ----------- | -------------- | ----- |
| Code Quality       | ✅ Complete | 4              | Focused on changed/new files |
| Security           | ✅ Complete | 8              | Full secret scan + OWASP review |
| Performance        | ✅ Complete | 3              | Query analysis + algorithmic review |
| Error Handling     | ✅ Complete | 3              | All I/O and DB paths reviewed |
| Architecture       | ✅ Complete | 31             | Full module dependency graph mapped |
| Dependencies       | ✅ Complete | 2              | pyproject.toml + uv.lock reviewed |
| Configuration      | ✅ Complete | 4              | .env.example, systemd units, YAML configs |
| Documentation      | ✅ Complete | 5              | README, AGENTS.md, QUICKSTART.md, deploy/README.md |

> **Scope Note**: This review was focused on the tailor worker feature changeset. The verdict is scoped to these changes and does not claim full-repo approval. Existing code outside the changeset was reviewed for integration points only.
