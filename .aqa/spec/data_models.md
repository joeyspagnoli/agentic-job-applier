# Data Models

## JobPosting (Pydantic)
- Fields (lines 22-49): source, source_url, company, company_url (Optional), title, location (Optional), is_remote (Optional[bool]), job_type (Optional[Literal["Full-time","Part-time","Contract","Internship"]]), salary_min/max (Optional[int], in cents), salary_currency (str, default "USD"), salary_source (Optional[Literal["direct","parsed","not_listed"]], default "not_listed"), description (str, default ""), requirements (str, default ""), posted_date (Optional[str]), raw_data (dict).
- Property `job_hash` (lines 51-77): SHA-256 hex digest of 8 canonicalized identity parts: source, company, title, normalized location, normalized posted_date, canonicalized URL (tracking params stripped, query sorted), description sub-hash, requirements sub-hash.
- Private helpers: `_normalize_text` (lowercases, collapses whitespace), `_canonicalize_url` (strips `utm_*`/`gh_src`/`gh_jid` params, sorts query, lowercases scheme/netloc, strips trailing `/`).
- Model validator `detect_remote` (lines 130-150): auto-detects remote from location keywords ("remote", "anywhere", "work from home", "wfh", "distributed").
- Field validator `normalize_job_type` (lines 152-183): maps common variants to Literal values or None.
- `to_db_dict()` (lines 185-218): serializes to 17-key dict with computed `job_hash` and JSON-dumped `raw_data`.
- Config: `ConfigDict(extra="ignore")` — extra fields silently dropped.

## Database Schema (SQLite)

### job_postings (lines 2-56 of schema.sql)
- core fields: source metadata, normalized job fields, compensation, status (CHECK: NEW/FILTERED/QUALIFIED/APPLIED/REJECTED), raw payload
- agent workflow fields: `agent_processed_at`, `agent_result`, `agent_failed_at`, `agent_error`
- retry fields: `agent_retry_count` (INTEGER NOT NULL DEFAULT 0), `agent_next_retry_at` (TIMESTAMP)
- claim fields: `agent_claim_token` (TEXT), `agent_claimed_at` (TIMESTAMP)
- timestamps: `fetched_at`, `updated_at`
- additional: `posted_date_parsed` (TIMESTAMP)
- 9 indexes including `idx_agent_retry_ready` (composite) and `idx_agent_claimed_at`

### tailor_runs (lines 99-113)
- `id` (PK autoincrement), `job_hash`, `status` (CHECK: PENDING/SUCCESS/FAILED)
- artifact tracking: `artifact_yaml_path`, `artifact_tex_path`, `artifact_pdf_path`, `page_count`
- retry/claim: `error`, `next_retry_at`, `started_at`, `completed_at`, `claim_token`
- 4 indexes: `idx_tailor_runs_job_hash`, `idx_tailor_runs_status`, `idx_tailor_runs_started_at`, `idx_tailor_runs_job_status` (composite)

### review_runs (lines 120-148)
- `id` (PK autoincrement), `job_hash`, `tailor_run_id`, `status` (CHECK: PENDING/SUCCESS/FAILED)
- verdict: `verdict` (CHECK: NULL or PASS/TAILORED/BASE/FAIL)
- selected artifacts: `selected_yaml_path`, `selected_tex_path`, `selected_pdf_path`
- report/diagnostics: `review_report_json`, `agent_stdout`, `agent_stderr`, `error`
- retry/claim: `next_retry_at`, `started_at`, `completed_at`, `claim_token`
- fallback refs: `fallback_base_yaml_path`, `fallback_base_tex_path`, `fallback_base_pdf_path`
- 5 indexes: `idx_review_runs_job_hash`, `idx_review_runs_status`, `idx_review_runs_started_at`, `idx_review_runs_tailor_run_id`, `idx_review_runs_tailor_status` (composite)

### crawl_history (lines 71-83)
- Per-source crawl execution: `source`, `company`, `started_at`, `completed_at`, `status` (CHECK: IN_PROGRESS/SUCCESS/FAILED), `jobs_found`, `jobs_new`, `error_message`.

### daily_stats (lines 89-96)
- Per-day aggregate discovery counters: `date` (PK, YYYY-MM-DD), `total_jobs_discovered`, `jobs_new`, `jobs_duplicate`, `sources_crawled`, `sources_failed`.

## Agent Input Prompt
- Candidate context source order:
  1. `config/candidate_profile.yaml` (`prompt_context` or structured `profile`)
  2. fallback constant in `src/agents/root_apply_decider/prompts.py`
- Runtime payload includes candidate context + normalized job fields via `build_gate_payload(job)`.
- Prompt includes safety rules treating job text as untrusted data.

## Agent Output
- **GateRunResult**: decision (APPLY|SKIP), optional GateDebugInfo (confidence, explanation, preference_matches, preference_conflicts), raw response, provider (`openai`), model (`openai/gpt-5.1-codex-mini`), parse mode (`json_recovered`).
- Decisions are accepted only from structured JSON parse recovery via `_extract_first_json_object`.
- Persisted outcomes:
  - success: `record_agent_decision` -> `status` to `QUALIFIED`/`FILTERED`
  - transient failure: `record_agent_retry`
  - terminal failure: `mark_job_agent_terminal_failed` + optional ntfy alert

## Resume Tailor Canonical Model
- **ResumeContent** (`src/agents/resume_tailor_pi/schemas.py`):
  - `schema_version` (int, default 1)
  - immutable lock metadata (`ResumeLockRules`):
    - section order (`education`, `experience`, `projects`, `skills_achievements`)
    - locked headings
    - non-editable sections (`personal`, `education`)
  - layout knobs (`LayoutKnobs`) used for bounded compression fallback
  - section payloads:
    - `personal` (`PersonalSection`: name, phone, email, links with `ResumeLink` model)
    - `education` (`EducationSection`: entries with `EducationEntry` model, each having optional bullets)
    - `experience` (`ExperienceSection`: listings with `ExperienceListing` + `enabled` toggle + `ResumeBullet` items)
    - `projects` (`ProjectsSection`: listings with `ProjectListing` + `tech_stack` + `enabled` toggle)
    - `skills_achievements` (`SkillsAchievementsSection`: listings with `SkillListing` + `enabled` toggle)
  - Model validator enforces unique listing IDs per section.
- Lock enforcement: `validate_locked_structure`, `build_locked_section_snapshot` (SHA-256), `ensure_locked_sections_unchanged`.
- **Canonical artifact**: `config/resume_content.yaml` is the source of truth; `.tex` is generated output.
- **Tailor worker output artifact set**: `resume_content_work.yaml`, `resume_tailored.tex`, `resume_tailored.pdf`.

## Resume Tailor Runtime Models
- **TailorJobRef**: exactly one selector (`job_hash` or `job_id`).
- **TailorInvocationContract**: job ref, database/YAML/artifact paths, page limit, content retry count, layout profile, pi model (`openai/gpt-5.1-codex-mini`), pi command config (argv/command/workspace/timeout/env allowlist), optional branch config.
- **TailorAttemptRecord**: phase (`content` or `layout`), attempt index, page count, message, success flag.
- **TailorRunResult**: final success/failure payload with artifact paths, page count, attempts history, active git branch.

## Resume Review Runtime Models
- **ReviewJobRef**: exactly one selector (`job_hash` or `job_id`).
- **ReviewInvocationContract**: job/tailor refs, tailored artifact paths (yaml/tex/pdf/log), base artifact paths, report path, max self-edit iterations (default 2, max 10), pi model/command/timeout config.
- **ReviewVerdict**: `PASS | TAILORED | BASE | FAIL`.
- **ReviewProfileLabel**: `SPARSER_THAN_BASE | DENSER_THAN_BASE | MARGIN_IMBALANCE | SIMILAR_TO_BASE`.
- **PdfGeometryMetrics**: page count, dimensions, margins, coverage metrics (vert_cov, horiz_cov, ink_ratio, bbox_cov, text_block_count).
- **PdfComparisonResult**: candidate/base metrics, delta dict, relative profile labels.
- **LatexLogAnalysis**: overfull/underfull counts, error count, warning count, has_fatal_error flag.
- **PdfTextSignals**: text_length_chars, word_count, nonempty_line_count, bullet_line_count.
- **ReviewReport**: strict completion handshake payload with verdict, summary, iteration_count, selected artifact paths (required for non-FAIL verdicts), optional geometry/comparison/log/text signal payloads, diagnostics list.
- **ReviewRunResult**: runtime outcome with success, hard_failure flag, validated report payload, selected refs, and agent stdout/stderr diagnostics.
