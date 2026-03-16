# Data Models

## JobPosting (Pydantic)
- Fields: source, source_url, company/company_url, title, location, is_remote, job_type (Full-time|Part-time|Contract|Internship), salary_min/max (cents), salary_currency, salary_source, description, requirements, posted_date, raw_data [src/models/job_posting.py:10-41](src/models/job_posting.py:10-41).
- Behaviors: canonicalized hash-based dedup key, remote auto-detect, job_type normalization, `to_db_dict()` serialization, extra fields ignored [src/models/job_posting.py](../../src/models/job_posting.py).

## Database Schema (SQLite)
- **job_postings**:
  - core fields: source metadata, normalized job fields, compensation, status, raw payload
  - agent workflow fields: `agent_processed_at`, `agent_result`, `agent_failed_at`, `agent_error`
  - retry fields: `agent_retry_count`, `agent_next_retry_at`
- **tailor_runs** (new):
  - `id` (PK autoincrement), `job_hash` (FK to job_postings), `status` (PENDING|SUCCESS|FAILED)
  - artifact tracking: `artifact_tex_path`, `artifact_pdf_path`, `page_count`
  - retry/claim: `error`, `next_retry_at`, `started_at`, `completed_at`, `claim_token`
  - CHECK constraint: `status IN ('PENDING', 'SUCCESS', 'FAILED')`
  - Indexes: `idx_tailor_runs_job_hash`, `idx_tailor_runs_status`, `idx_tailor_runs_started_at`
- **Indexes** include `idx_agent_retry_ready` for pending retry selection.
- **crawl_history**: per-source crawl execution and failure metadata.
- **daily_stats**: per-day aggregate discovery counters.

## Agent Input Prompt
- Candidate context source order:
  1. `config/candidate_profile.yaml` (`prompt_context` or structured `profile`)
  2. fallback constant in `src/agents/root_apply_decider/prompts.py`
- Runtime payload includes candidate context + normalized job fields via `build_gate_payload(job)`.

## Agent Output
- **GateRunResult**: decision (APPLY|SKIP), optional debug metadata, raw response, provider, model, and parse mode [src/agents/root_apply_decider/schemas.py](../../src/agents/root_apply_decider/schemas.py).
- Persisted outcomes:
  - success: `record_agent_decision` -> `status` to `QUALIFIED`/`FILTERED`
  - transient failure: `record_agent_retry`
  - terminal failure: `mark_job_agent_terminal_failed` + optional ntfy alert

## Resume Tailor Canonical Model
- **ResumeContent** (`src/agents/resume_tailor_pi/schemas.py`):
  - immutable lock metadata:
    - section order (`education`, `experience`, `projects`, `skills_achievements`)
    - locked headings
    - non-editable sections (`personal`, `education`)
  - layout knobs used for bounded compression fallback
  - section payloads:
    - `personal` (name, phone, email, links)
    - `education` entries
    - `experience` listings + bullets (`enabled` toggle for pool behavior)
    - `projects` listings + bullets (`enabled` toggle)
    - `skills_achievements` rows (`enabled` toggle)
- **Canonical artifact**: `config/resume_content.yaml` is the source of truth; `.tex` is generated output.

## Resume Tailor Runtime Models
- **TailorJobRef**: exactly one selector (`job_hash` or `job_id`).
- **TailorInvocationContract**: job ref, YAML/artifact paths, page limit, content retry count, layout profile, optional branch config.
- **TailorAttemptRecord**: phase (`content` or `layout`), attempt index, page count, message, success flag.
- **TailorRunResult**: final success/failure payload returned by `run_resume_tailor_pipeline`.
