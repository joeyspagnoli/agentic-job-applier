# Data Models

## JobPosting (`src/models/job_posting.py`, 222 lines)
- Core fields: source metadata, company/title/location, job type, salary fields, description/requirements, posted date, raw payload.
- `job_hash` property: SHA-256 hash of canonical identity parts (source/company/title/location/posted_date/canonical_url/content sub-hashes).
- URL canonicalization strips tracking params and normalizes ordering/case.
- `detect_remote` validator infers remote roles from location text.
- `normalize_job_type` validator maps common variants into constrained values.
- `to_db_dict()` returns the SQLite-ready payload including JSON-serialized `raw_data`.

## SQLite Schema (`src/database/schema.sql`, 193 lines)

### `job_postings`
- Main workflow table for discovered jobs.
- `status` check constraint: `NEW`, `FILTERED`, `QUALIFIED`, `APPLIED`, `REJECTED`.
- Gate fields: `agent_processed_at`, `agent_result`, `agent_failed_at`, `agent_error`, `agent_retry_count`, `agent_next_retry_at`, `agent_claim_token`, `agent_claimed_at`.
- Other tables reference `job_hash` but no FK constraints are enforced at DB level.

### `crawl_history`
- Tracks discovery crawl runs (`IN_PROGRESS`, `SUCCESS`, `FAILED`) and per-run job counts/errors.

### `daily_stats`
- Date-keyed aggregate counters for discovery totals/new/duplicate and source success/failure.

### `tailor_runs`
- Retryable run table for resume tailoring.
- Status enum: `PENDING`, `SUCCESS`, `FAILED`.
- Artifact paths: YAML/TeX/PDF and `page_count`.
- Retry metadata: `error`, `next_retry_at`, `claim_token`, timestamps.

### `review_runs`
- Retryable run table for post-tailor review.
- Status enum: `PENDING`, `SUCCESS`, `FAILED`.
- Verdict enum (nullable): `PASS`, `TAILORED`, `BASE`, `FAIL`.
- Selected artifact refs for non-FAIL verdicts, report JSON, stdout/stderr, fallback base refs.

### `apply_runs`
- Retryable run table for browser apply attempts.
- Status enum: `PENDING`, `SUCCESS`, `FAILED`.
- Outcome enum (nullable): `NEEDS_REVIEW`, `SUBMITTED`, `FAILED_PREFILL`, `FAILED_UPLOAD`, `FAILED_NAVIGATION`, `FAILED_OTHER`.
- Resume attribution: `resume_pdf_path`, `resume_source` (`TAILORED` or `BASE`).
- Confidence/diagnostics: `confidence_score`, `confidence_report_json`, `unresolved_fields_json`, `simplify_autofill_detected`, `ats_platform`, `page_url`, screenshot/DOM paths.
- Retry metadata: `error`, `next_retry_at`, `claim_token`, timestamps.

### `apply_handoffs`
- Operator handoff table keyed by `apply_run_id` for non-submitting apply outcomes.
- Handoff status enum: `PENDING_REVIEW`, `APPROVED`, `REJECTED`.
- Captures review payload: `apply_outcome`, resume attribution, confidence/diagnostics JSON, screenshot/DOM paths, ATS/page URL.
- Review annotations: `reviewer_notes`, `reviewed_at`, plus `created_at` and `updated_at`.

## Gate Agent Output Models
- `ApplyDecision`: `APPLY` or `SKIP`.
- `GateDebugInfo`: confidence/explanation/match metadata.
- `GateRunResult`: normalized decision payload with provider/model metadata and raw response.

## Resume Tailor Models
- `ResumeContent`: canonical YAML schema with locked sections and ordering rules.
- `TailorInvocationContract`: one-run runtime contract (job selector, paths, model/process settings).
- `TailorAttemptRecord`: per-attempt stage history.
- `TailorRunResult`: final tailor output payload.

## Resume Review Models
- `ReviewInvocationContract`: review runtime input contract.
- `ReviewVerdict`: `PASS|TAILORED|BASE|FAIL`.
- `ReviewReport`: strict completion report with selected artifacts for non-FAIL verdicts.
- `ReviewRunResult`: runtime result, verdict/report payload, diagnostics.

## Browser Apply Models (`src/agents/apply_worker/schemas.py`)
- `ApplyOutcome`: application-level outcome independent of row lifecycle status.
- `ATSPlatform`: detected ATS enum.
- `UnresolvedField`: rich field metadata for unresolved form inputs.
- `ConfidenceCheck` and `ConfidenceReport`: deterministic weighted scoring payload.
- `ApplyRunResult`: worker output object used by `process_apply_jobs.py` for persistence.
