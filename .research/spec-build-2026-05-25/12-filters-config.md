# Filters & Config Subsystem Specification

**Subsystem:** Pre-LLM filtering of job postings, candidate profile validation, defer rules, answer cache, environment contract.

**Owning modules:**
- `src/filters/` — hard/soft filter pipeline
- `src/config/` — schema validation (Pydantic v2)
- `config/*.yaml` — user-facing configuration files
- `.env` contract — environment variable defaults and runtime paths

---

## 1. Purpose & Scope

The Filters & Config subsystem owns the entire pre-LLM filtering and configuration validation pipeline. It enforces two critical guarantees:

1. **Pre-gate hard filtering:** Job postings are rejected before entering the database based on title patterns, location, company blocklist, salary bounds, age, job type, and remote requirements.
2. **Soft filtering:** Jobs matching negative keywords or excessive experience requirements are auto-filtered; jobs with positive keywords are auto-qualified, skipping the gate agent.
3. **Configuration validation:** The candidate profile YAML is validated against a strict Pydantic schema at API startup, surfacing misconfiguration loudly rather than failing silently.
4. **Defer-rule classification:** Form fields are routed to Tier 1 (profile-direct), Tier 2 (LLM draft + review), or Tier 3 (always defer) based on regex patterns in `defer_rules.yaml`.
5. **Answer caching:** Previously-answered application questions are persisted and fuzzy-matched across runs to reduce redundant LLM invocations.
6. **Resume migration:** The codebase transitioned from YAML-centric resume layout (`resume_content.yaml`) to `.tex` source-of-truth, with an idempotent migration script that validates the new contract.

---

## 2. YAML Config Inventory

### 2.1 `config/filters.yaml`

**Purpose:** Hard and soft filter rules controlling pre-gate job acceptance.

**Schema (hard_filters):**
- `exclude_job_types: [str]` — job type literals to reject (e.g., "Full-time", "Part-time", "Contract")
- `exclude_title_patterns: [regex]` — title regexes; any match rejects the job
- `require_title_patterns: [regex]` — title must match *at least one*; empty disables
- `exclude_locations: [str]` — substring match against job location (case-insensitive)
- `require_remote: bool` — when True, only non-remote jobs pass
- `exclude_companies: [str]` — exact company name match (case-insensitive)
- `max_days_old: int` — reject jobs older than N days; 0 disables
- `min_salary_usd: int` — reject jobs with salary_max < this; 0 disables
- `max_salary_usd: int` — reject jobs with salary_min > this; 0 disables

**Schema (soft_filters):**
- `negative_keywords: [str]` — description contains any → REJECT_FILTERED
- `positive_keywords: [str]` — description contains any → ACCEPT_QUALIFIED
- `max_experience_years: int` — if description mentions "X+ years" where X > this, REJECT_FILTERED

**Owner:** User-facing config; lives at `config/filters.yaml` (optional, loaded by `load_optional_yaml`).

**Runtime read-path:** `src/orchestrator/discovery.py:_run_batch()` calls `load_optional_yaml(config_dir / "filters.yaml")` and instantiates `JobFilter(filters_config)`.

**Write-path:** None (read-only from user perspective). Backup snapshots written to `config/backups/filters_YYYYMMDD_HHMMSS.yaml` by the onboarding wizard.

**Recent edits:** Job type exclude now forces "Full-time" only for the candidate (line 9); the most recent modification confirmed title patterns match case-insensitive senior/staff/principal/manager/director/vp/head/chief/recruiter/sales/marketing/support (lines 13–24). Require patterns pin entry-level: intern, co-op, new.?grad, early.?career, student (lines 28–34).

---

### 2.2 `config/candidate_profile.yaml`

**Purpose:** Comprehensive candidate profile consumed by the apply finisher, gate agent, resume tailor, and discovery loop.

**Top-level schema (validated by Pydantic `CandidateProfile`):**
- `profile: ProfileSection` — personal/professional summary, contact, work auth, education, target roles, strongest areas, experience highlights, hard filters, preferences
- `search_defaults: SearchDefaultsSection` — job board search terms fed to the discovery loop
- `apply_prefs: ApplyPrefs` — auto-apply finisher preferences (EEO defaults, compensation, availability, location, languages)

**Key nested structures:**

**ProfileSection:**
- `contact: ContactSection` — full name, email, phone, city, state/region, country code, LinkedIn/GitHub/portfolio URLs
- `work_authorization: WorkAuthorizationSection` — citizenship country, authorized-to-work-us (yes/no/unknown), sponsorship requirement (yes/no/unknown)
- `target_roles: [str]` — preferred role titles (e.g., "AI Engineer Intern", "Machine Learning Engineer Intern")
- `strongest_areas: [str]` — technical strengths (e.g., "Agentic AI orchestration", "PyTorch model training")
- `experience_highlights: [str]` — structured work/project summaries
- `hard_filters: [regex]` — title patterns to auto-reject (duplicates hard_filters from filters.yaml for candidate-profile-direct access)
- `education_entries: [object]` — flexible list of education records; schema allows `id`, `school`, `degree_name`, `field_of_study`, `start_year`, `start_month`, `end_year`, `end_month`, `is_current`, `gpa`, `minors` (handled as `list[object]` to preserve unknown fields)

**ApplyPrefs:**
- `pronouns: str` — candidate pronouns (e.g., "he/him")
- `eeo_defaults: EeoDefaults` — gender, race_ethnicity, veteran_status, disability_status (each defaults to "prefer_not_to_say")
- `sponsorship_required_now_or_future: Literal["yes", "no", "unknown"]` — default "unknown"; used by finisher to pre-fill sponsorship prompts
- `work_authorized_us: Literal["yes", "no", "unknown"]` — default "unknown"; used to answer work-authorization questions
- `compensation: CompensationPrefs` — expected_salary_min_usd, expected_salary_max_usd, expected_hourly_rate_usd (all optional)
- `availability: AvailabilityPrefs` — earliest_start_date (ISO date or "flexible"), notice_period_weeks (optional int)
- `location_preferences: LocationPrefs` — willing_to_relocate (Literal["yes", "no", "open_to_discussion"], defaults "open_to_discussion"), preferred_cities (list[str]), willing_remote (bool, default True), willing_hybrid (bool, default True)
  - **Backward compatibility:** Old profiles with boolean `willing_to_relocate` are coerced: False → "no", True → "yes" (Pydantic field_validator at `src/config/schema.py:95–109`)
- `application_defaults: ApplicationDefaults` — how_did_you_hear (str), tier2_confidence_threshold (float, range [0.0, 1.0], default 1.0)
- `languages: [LanguageEntry]` — each entry has `language: str`, `proficiency: Literal["basic", "conversational", "fluent", "native"]` (default "conversational")

**Owner:** User-facing config; lives at `config/candidate_profile.yaml` (mandatory if CANDIDATE_PROFILE_PATH env var points to it).

**Runtime read-path:**
- `src/orchestrator/discovery.py:_run_batch()` calls `load_optional_yaml(config_dir / "candidate_profile.yaml")` and validates via `CandidateProfile.model_validate(parsed_dict)`.
- `src/agents/apply_finisher/runner.py` loads the profile as raw YAML text (not through Pydantic schema) to preserve exact formatting for finisher prompts.
- `src/agents/resume_tailor/pipeline.py` receives `candidate_profile_yaml_path` to build a context for the tailor worker.

**Write-path:** None (read-only from the app perspective). Backup snapshots written to `config/backups/candidate_profile_YYYYMMDD_HHMMSS.yaml` by the onboarding wizard when the user completes any section.

**Validation:** Schema enforced by Pydantic v2 at `src/config/schema.py:CandidateProfile` (lines 270–290). Validation errors raised at API startup via `startup_hook` to catch misconfiguration immediately (tests: `tests/test_config_schema*.py`).

---

### 2.3 `config/search_criteria.yaml`

**Purpose:** (Deprecated; for Phase 2+ use only.) Search filtering rules and job-board query templates.

**Schema:**
- `include_title_patterns: [regex]` — title must match at least one to be stored; empty disables pre-storage filtering
- `target_titles: [str]` — global job board search terms (typically empty; search terms from `candidate_profile.yaml:search_defaults.job_board_search_terms` take priority)
- `exclude_title_patterns: [regex]` — title to exclude (duplicates filters.yaml patterns)
- `locations: {remote_preference: str, acceptable_cities: [str]}`
- `salary: {min: int, max: int, currency: str}` — for Phase 2 filtering
- `experience: {min_years: int, max_years: int}`
- `company_size: {min_employees: int, max_employees: int}`
- `positive_keywords: [str]` — positive signals in descriptions
- `negative_keywords: [str]` — negative signals (duplicates soft_filters from filters.yaml)

**Owner:** User-facing; optional. Loaded by `load_optional_yaml(config_dir / "search_criteria.yaml")`.

**Runtime read-path:** Primarily informational; the discovery loop and fetchers don't actively enforce search_criteria rules (those live in filters.yaml). This file documents intent for Phase 2+.

**Write-path:** Backups to `config/backups/search_criteria_*.yaml` if user edits via wizard.

---

### 2.4 `config/companies.yaml`

**Purpose:** Target company list, indexed by ATS ID (Greenhouse, Workday, iCIMS, Ashby, Lever) with priority and industry tags.

**Schema:**
- Top-level keys: `greenhouse_companies`, `workday_companies`, `icims_companies`, `ashby_companies`, `lever_companies`
- Each company entry:
  - `greenhouse_id: str` (or equivalent for other ATS)
  - `industry: str` — category tag (e.g., "software_tech", "semiconductor", "aerospace_defense", "hardware")
  - `priority: int` — 1 (highest) to 10 (lowest); used to sort discovery batch processing

**Owner:** User-facing config; mandatory for discovery to function.

**Runtime read-path:** `src/orchestrator/discovery.py:_run_batch()` calls `load_yaml(config_dir / "companies.yaml")` (required, not optional).

**Write-path:** Backups to `config/backups/companies_YYYYMMDD_HHMMSS.yaml` by onboarding wizard; no in-app mutations.

---

### 2.5 `config/defer_rules.yaml`

**Purpose:** Regex patterns that classify form field labels into three tiers for the apply finisher.

**Schema:**
- `always_defer_labels: [{regex: str}]` — Tier 3; always defer to human. Recent edits (last modified 2026-05-25 13:47) removed EEO/start-date (user has explicit cached answers), kept sponsorship and salary.
- `draft_and_flag_labels: [{regex: str}]` — Tier 2; LLM drafts an answer, marked needs_review=True
- `bypass_field_types: [str]` — field types the finisher skips entirely (file, hidden, submit, button)
- `never_defer_overrides: [{regex: str}]` — regexes that *remove* Tier 3 classification even if an always_defer pattern would match

**Loaded by:** `src/agents/apply_finisher/defer_rules.py:load_defer_rules(Path)` (line 121–149).

**Tier classification logic** (line 60–89):
1. Check if label matches any always_defer pattern. If yes and not overridden, return "tier3".
2. Check if label matches any draft_and_flag pattern. If yes, return "tier2".
3. Otherwise, return "tier1" (safe to auto-fill from profile).

**Runtime read-path:** `src/agents/apply_worker/finisher_integration.py:defer_rules = load_defer_rules(context.defer_rules_path)` and `src/agents/apply_finisher/__init__.py` export the `load_defer_rules` function.

**Write-path:** None (read-only from app perspective). Backups may be written by wizard, but tier classification happens at runtime.

**Recent edits (2026-05-25 13:47):**
- `always_defer_labels` now includes two regex entries:
  - `'(?i)sponsor|visa|authorize.*sponsor'` — catches "sponsor", "visa", "authorization for sponsorship"
  - `'(?i)salary|compensation|desired pay'` — catches salary and compensation questions
- EEO and start-date removed from always_defer (they have explicit cached answers + profile defaults, and deferring them blocks every submit).
- Comment updated to clarify that sponsorship and salary are kept as tier-3 because they're legally consequential.

---

### 2.6 `data/answer_cache.yaml`

**Purpose:** Fuzzy-matched cache of previously-answered application questions.

**Schema:**
```yaml
schema_version: 1
entries:
  - question_text: str          # Original question label (e.g., "Why do you want to work here?")
    question_normalized: str    # Normalized form (lowercase, no punctuation, $COMPANY → COMPANY)
    answer: str                 # Answer, may contain literal "$COMPANY" placeholder
    category: str               # Free-form tag (e.g., "motivation", "sponsorship")
    company_specific: bool      # True if locked to a company
    company: str | null         # Company name or null for anonymized entries
```

**Owned by:** Apply finisher; loaded by `src/agents/apply_finisher/answer_cache.py:load_answer_cache(Path)` (line 253+).

**Lookup strategy** (`src/agents/apply_finisher/answer_cache.py:195–250`):
1. Normalize question (lowercase, strip punctuation, replace $COMPANY with sentinel COMPANY token)
2. Check per-company entries first:
   - Exact hash match (normalized hash comparison)
   - Fuzzy RapidFuzz token_set_ratio >= 85% match
3. Check anonymized entries (same strategy)
4. Return highest-scoring hit; per-company beats anonymized at equal scores
5. Substitute $COMPANY with actual company name in returned answer

**Write-path:** `AnswerCache.persist(Path)` (line 223–242) writes back to YAML using atomic rename (temp file + move) to avoid corruption on crash.

**Runtime read-path:** `src/agents/apply_worker/browser.py` receives deps.answer_cache and uses it to pre-fill fields before LLM refinement.

**Current state (2026-05-25):** `data/answer_cache.yaml` contains only `schema_version: 1` and empty `entries: []` — fresh start for this run.

---

## 3. `src/filters/job_filter.py` — Hard & Soft Filter Pipeline

**Module purpose:** Apply user-configured hard and soft filters to fetched job postings before they enter the database.

**Key exports:**
- `FilterAction` enum (line 35–48): ACCEPT_NEW, ACCEPT_QUALIFIED, REJECT, REJECT_FILTERED
- `JobFilter` class (line 51–459)

**JobFilter public API:**
- `__init__(config: dict[str, Any])` — Loads filter rules from parsed filters.yaml config; pre-compiles all regex patterns (lines 61–77).
- `filter_job(job: JobPosting) -> tuple[FilterAction, str]` — Main entry point; runs hard filters first, then soft filters, returns (FilterAction, reason) (lines 83–103).

### Hard Filter Checks (run in order, first match wins):

1. **_check_exclude_job_type** (line 156–168) — Reject if job.job_type matches exclude_job_types (case-insensitive set lookup).

2. **_check_exclude_title** (line 170–178) — Reject if job.title matches any exclude_title_patterns regex.

3. **_check_require_title** (line 180–192) — Reject if require_title_patterns are defined and job.title matches *none* of them.

4. **_check_exclude_location** (line 194–207) — Reject if job.location contains an excluded substring (case-insensitive).

5. **_check_require_remote** (line 209–220) — Reject if require_remote=True and job.is_remote=False.

6. **_check_exclude_company** (line 222–234) — Reject if job.company matches any exclude_companies (case-insensitive exact match).

7. **_check_max_days_old** (line 236–252) — Reject if job is older than max_days_old days. Parses ISO 8601 and Unix timestamp formats (lines 435–458).

8. **_check_salary_bounds** (line 254–278) — Reject if salary falls outside min/max_salary_usd bounds. Works in cents internally (32 CENTS_PER_DOLLAR = 100).

### Soft Filter Checks (return REJECT_FILTERED or ACCEPT_QUALIFIED):

1. **_check_negative_keywords** (line 311–327) — If description contains any negative keyword, return (REJECT_FILTERED, reason). Case-insensitive substring match.

2. **_check_experience_years** (line 329–351) — Extract "N+ years" from description using regex (line 26–29: `_EXPERIENCE_YEARS_PATTERN`). If any match exceeds max_experience_years, return (REJECT_FILTERED, reason).

3. **_check_positive_keywords** (line 353–384) — If description contains *any* positive keyword (using `next()` with default None, line 375–378), return (ACCEPT_QUALIFIED, reason). **Bug fix:** Changed from `all()` to `any()` semantics so users with non-software profiles don't require every keyword to be present (line 361–361).

**Key helpers:**
- `_compile_patterns(patterns: list[str], *, label: str) -> list[re.Pattern]` (line 390–422) — Compiles regex patterns; logs warnings for invalid ones, tolerates None/empty list.
- `_try_parse_date(date_str: str) -> datetime | None` (line 424–458) — Best-effort date parser supporting ISO 8601, Unix epoch, and various formats.

---

## 4. `src/config/schema.py` — Pydantic v2 Schema Validation

**Purpose:** Validate the entire candidate_profile.yaml at API startup to surface misconfiguration loudly.

**Key Pydantic models:**

1. **WillingToRelocate** (line 20) — Tri-state literal: "yes", "no", "open_to_discussion"

2. **EeoDefaults** (line 26–41) — Gender, race_ethnicity, veteran_status, disability_status; all default to "prefer_not_to_say".

3. **CompensationPrefs** (line 44–57) — expected_salary_min_usd, expected_salary_max_usd, expected_hourly_rate_usd (all Optional[int]).

4. **AvailabilityPrefs** (line 60–71) — earliest_start_date (str, default "flexible"), notice_period_weeks (Optional[int]).

5. **LocationPrefs** (line 74–109) — 
   - willing_to_relocate (WillingToRelocate, default "open_to_discussion")
   - preferred_cities (list[str], default [])
   - willing_remote (bool, default True)
   - willing_hybrid (bool, default True)
   - **Field validator** (line 95–109): Coerces legacy boolean YAML values (False → "no", True → "yes") for backward compat with profiles written before 2026-05-25.

6. **ApplicationDefaults** (line 112–128) — 
   - how_did_you_hear (str, default "")
   - tier2_confidence_threshold (float, range [0.0, 1.0], default 1.0) — Pydantic `Annotated[float, Field(ge=0.0, le=1.0)]` enforces bounds.

7. **LanguageEntry** (line 131–142) — language (str), proficiency (Literal["basic", "conversational", "fluent", "native"], default "conversational").

8. **ApplyPrefs** (line 145–172) — Container for all apply-finisher preferences; aggregates all the above models.

9. **ContactSection, WorkAuthorizationSection, ProfileSection** (lines 178–256) — Minimal struct validators for candidate contact, work auth, and profile metadata.

10. **SearchDefaultsSection** (line 258–267) — job_board_search_terms (list[str]).

11. **CandidateProfile** (line 270–290) — Top-level document model:
    - profile (ProfileSection)
    - search_defaults (SearchDefaultsSection)
    - apply_prefs (ApplyPrefs)

**All models use `ConfigDict(extra="allow")`** to permit undocumented keys without errors, allowing the schema to evolve backward-compatibly.

---

## 5. Environment Variable Contract

**File:** `.env.example` (all defaults below apply if env vars are unset).

### Required

- **OPENAI_API_KEY** — OpenAI API key (used by gate, tailor, review workers). Workers idle gracefully if unset; they don't crash. Multi-provider support (Anthropic, Gemini, OpenRouter) tracked in #35.

### Optional — Config Paths

- **CANDIDATE_PROFILE_PATH** (default `config/candidate_profile.yaml`) — Path to the candidate profile YAML.
- **TAILOR_RESUME_YAML_PATH** (default `config/resume_content.yaml`) — Legacy path; resume tailor reads this.
- **REVIEW_BASE_RESUME_YAML_PATH** (default `config/resume_content.yaml`) — Legacy path; review worker reads this.
- **REVIEW_BASE_RESUME_TEX_PATH** (default `data/tailored_resumes/_base_reference/resume_base.tex`) — Path to the reference resume TeX file (Phase 3+ path after migration).
- **REVIEW_BASE_RESUME_PDF_PATH** (default `data/tailored_resumes/_base_reference/resume_base.pdf`) — Compiled PDF from resume TeX.

### Optional — Feature Flags & Defaults

- **NTFY_TOPIC** (default `""` / disabled) — ntfy.sh topic for push notifications on terminal-state failures.
- **NTFY_SERVER** (default `https://ntfy.sh`) — ntfy.sh server URL.
- **NTFY_TOKEN** (default `""`) — ntfy.sh authentication token.
- **NTFY_PRIORITY** (default `default`) — ntfy.sh priority level.
- **RUN_INTERVAL_MINUTES** (default `30`) — How often discovery runs.
- **API_PORT** (default `8000`) — API port exposed on the host.
- **CHROME_CDP_URL** (default `http://host.docker.internal:9222`) — Chrome DevTools Protocol endpoint the apply loop uses to drive the host's Chrome instance.
- **LITELLM_LOCAL_MODEL_COST_MAP** (default `true`) — Use bundled litellm pricing table instead of network lookup.
- **SAFE_MODE** (default `false`) — When `true`, hard kill switch disables auto-submit globally; finisher still fills forms but leaves them in NEEDS_REVIEW.

### Optional — Database & Logging

- **DATABASE_PATH** (default `data/jobs.db`) — SQLite database file.
- **SQLITE_JOURNAL_MODE** (default `WAL`) — SQLite journal mode (WAL recommended).
- **LOG_LEVEL** (default `INFO`) — Logging level.
- **LOG_FILE** (default `logs/job_monitor.log`) — Log file path.

### Optional — Gate Worker (process_new_jobs.py)

- **AGENT_BATCH_SIZE** (default `100`) — Jobs to process per batch.
- **AGENT_POLL_INTERVAL_SECONDS** (default `60`) — Polling interval.
- **AGENT_MAX_RETRIES** (default `3`) — Max retry attempts.
- **AGENT_RETRY_BACKOFF_SECONDS** (default `300`) — Initial backoff.
- **AGENT_RETRY_BACKOFF_MULTIPLIER** (default `3`) — Exponential backoff multiplier.
- **JOB_MAX_AGE_DAYS** (default `90`) — Skip jobs older than N days (0 disables).

### Optional — Tailor Worker (process_qualified_jobs.py)

- **TAILOR_POLL_INTERVAL_SECONDS** (default `30`) — Polling interval.
- **TAILOR_MAX_RETRIES** (default `2`) — Max retries.
- **TAILOR_RETRY_BACKOFF_SECONDS** (default `600`) — Initial backoff.
- **TAILOR_RETRY_BACKOFF_MULTIPLIER** (default `2`) — Exponential backoff.
- **TAILOR_CLAIM_LEASE_SECONDS** (default `7200`) — Lease duration for claimed jobs.
- **TAILOR_OUTPUT_DIR** (default `data/tailored_resumes`) — Output directory for tailored resumes.
- **RESUME_TAILOR_MODEL** (default `openai/gpt-5-mini`) — LLM model for resume tailoring. Prose-tuned models only; avoid coding-tuned variants (they bail on prose-rewrite tasks per issue #53).

### Optional — Review Worker (process_reviewed_resumes.py)

- **REVIEW_POLL_INTERVAL_SECONDS** (default `30`) — Polling interval.
- **REVIEW_MAX_RETRIES** (default `2`) — Max retries.
- **REVIEW_RETRY_BACKOFF_SECONDS** (default `600`) — Initial backoff.
- **REVIEW_RETRY_BACKOFF_MULTIPLIER** (default `2`) — Exponential backoff.
- **REVIEW_CLAIM_LEASE_SECONDS** (default `7200`) — Lease duration.
- **REVIEW_OUTPUT_DIR** (default `data/tailored_resumes`) — Output directory.
- **RESUME_REVIEWER_MODEL** (default `openai/gpt-5-mini`) — LLM model for review. Same guidance as RESUME_TAILOR_MODEL.

---

## 6. Defer Rules & Answer Cache in Apply Finisher

**Integration point:** `src/agents/apply_worker/finisher_integration.py`

**Loading:**
```python
defer_rules = load_defer_rules(context.defer_rules_path)
answer_cache = load_answer_cache(context.answer_cache_path)
```

**Tier-based form-filling strategy:**
1. **Tier 1** — Auto-fill from candidate profile (location prefs, availability, compensation, EEO defaults).
2. **Tier 2** — LLM drafts an answer + human review flag; used for "why us", "hardest problem", "tell us about yourself" type questions.
3. **Tier 3** — Always defer; never auto-fill. Sponsorship and salary questions require explicit user decision.

**Answer cache lookup (before LLM):**
- Normalize the question label
- Search per-company cached answers first, then anonymized answers
- Fuzzy match with RapidFuzz token_set_ratio >= 85%
- Substitute $COMPANY placeholder with actual company name
- If hit, use cached answer; if tier-2, mark needs_review=True
- If miss, invoke LLM to draft answer

**Persistence:**
- After finisher submits or defers a form, the new answer is appended to AnswerCache via `cache.append_entry(...)` and persisted atomically to `data/answer_cache.yaml`.
- Schema version 1 enforced; migration plan for future versions is TBD.

---

## 7. YAML → TeX Resume Migration

**Script:** `scripts/migrate_yaml_to_tex.py` (lines 1–120)

**Purpose:** Move users from YAML-centric resume layout (`config/resume_content.yaml` + `config/resume_base.tex`) to Phase 3+ `.tex` source-of-truth (`config/resume.tex`).

**Migration logic (per plan §9):**

1. **Step 1 — Short-circuit on already-migrated:**
   - If `config/resume.tex` exists AND validates → print "ALREADY-MIGRATED", return EXIT_OK (0).
   - If `config/resume.tex` exists but INVALID → print errors, return EXIT_MANUAL_FIX_REQUIRED (2).

2. **Step 2 — No source TeX found:**
   - If neither `config/resume.tex` nor `config/resume_base.tex` exist → print "NO-SOURCE-TEX-FOUND", return EXIT_NO_SOURCE (1).

3. **Step 3a — Migrate from legacy TeX (if valid):**
   - Validate `config/resume_base.tex` against the `.tex` contract (via `validate_resume_tex(...)`).
   - If valid: Rename to `config/resume.tex`, delete `config/resume_content.yaml` if present, print "ALREADY-CONFORMING-MIGRATED", return EXIT_OK (0).

4. **Step 3b — Legacy TeX fails contract:**
   - If `config/resume_base.tex` fails contract validation → print errors with line numbers + suggested fixes, print "MANUAL-FIX-REQUIRED", return EXIT_MANUAL_FIX_REQUIRED (2).
   - The legacy file is NOT auto-rewritten (per plan §11) to avoid silent data damage; user must fix manually.

**Idempotence:** Running the script twice:
- First run: "ALREADY-CONFORMING-MIGRATED" + rename + delete yaml.
- Second run: "ALREADY-MIGRATED" + no-op.
- File content identical after both runs (verified by tests: `tests/test_migrate_yaml_to_tex.py:test_running_migration_twice_is_a_clean_no_op_on_second_run`).

**Tests locked in:**
- Step 1 short-circuit (no-op, exit 0)
- Step 2 no-source-found (exit 1)
- Step 3a successful migration (exit 0, files renamed/deleted)
- Step 3b manual-fix-required (exit 2, legacy file untouched)
- Invalid existing resume.tex surfaced (exit 2, FOUND-INVALID-RESUME-TEX)
- Idempotence verified (second run is no-op)

**Contract validation:** Calls `src/agents/resume_tailor/validator.py:validate_resume_tex(text, run_compile_check=False)` to verify `.tex` structure without compilation.

---

## 8. Config Schema Tests

### 8.1 `tests/test_config_schema.py`

**Locks in:**
- **Round-trip test** (line 37–59): Live `config/candidate_profile.yaml` parses via `CandidateProfile.model_validate(...)`, validates expected fields (work_authorized_us, sponsorship, tier2_confidence_threshold).
- **Defaults** (line 61–77): Missing apply_prefs block defaults tier2_confidence_threshold to 1.0 for backward compat.
- **Validation bounds** (line 80–99): tier2_confidence_threshold outside [0.0, 1.0] raises ValidationError.
- **Literal validation** (line 102–115): Invalid work_authorized_us literal (e.g., "maybe") raises ValidationError.

### 8.2 `tests/test_config_schema_location_prefs.py`

**Locks in:**
- **Default is tri-state** (line 22–28): Fresh LocationPrefs defaults willing_to_relocate to "open_to_discussion".
- **Tri-state accepted** (line 31–36): "yes", "no", "open_to_discussion" round-trip.
- **Unknown literal rejected** (line 39–44): "maybe" raises ValidationError.
- **Legacy boolean coercion** (line 47–62): False → "no", True → "yes" for backward compat.
- **End-to-end coercion** (line 64–81): Full CandidateProfile with legacy boolean survives with coerced value.
- **Education entries pass-through** (line 84–120): New structured education_entries survive validation without stripping unknown fields (`list[object]` permits that).
- **ApplyPrefs full round-trip** (line 123–138): New willing_to_relocate flows through the full ApplyPrefs model.

### 8.3 `tests/test_config_schema_apply_prefs.py`

**Locks in:**
- **Defaults** (line 36–58): Absent apply_prefs defaults sponsorship/work_auth to "unknown"; EEO defaults to "prefer_not_to_say"; languages list is empty.
- **Threshold boundary values** (line 66–83): [0.0, 0.5, 1.0] accepted; [-0.0001, 1.0001, 2.0, -1.0] rejected.
- **Language proficiency enum** (line 91–103): "basic", "conversational", "fluent", "native" accepted; "elite" rejected.
- **Structural validation** (line 111–115): Invalid sponsorship literal raises ValidationError.
- **Extra allow** (line 118–123): Unknown top-level keys are tolerated via `extra='allow'`.

### 8.4 `tests/test_job_filter_positive_keywords.py`

**Locks in:**
- **Empty config** (line 62–72): Empty positive_keywords or missing key returns None.
- **Single keyword match** (line 86–98): Description containing keyword returns (ACCEPT_QUALIFIED, reason).
- **No keyword match** (line 101–110): No matches return None.
- **Any semantics** (line 113–126): First matching keyword short-circuits; doesn't require all keywords.
- **Config order** (line 129–143): Reason string names the first keyword in config order that matches (for analytics).
- **Case-insensitive** (line 146–158): Matching is case-insensitive.
- **Non-string entries skipped** (line 161–173): None, 42, {} are silently skipped; Python strings are tested.
- **Empty description** (line 188–197): Empty description with keywords configured returns None.
- **Substring matching table** (line 200–230): Parametrized test covering various substring + case combinations.

---

## 9. Risk Ledger & Gotchas

### 9.1 Schema Drift

**Risk:** User edits candidate_profile.yaml manually and introduces invalid fields (e.g., typo in a literal, out-of-range threshold).

**Mitigation:**
- Pydantic v2 schema validated at API startup (not lazy on first read).
- ValidationError raised loudly with actionable output (field + error loc).
- All literal fields (sponsorship, work_auth, proficiency, tier2_confidence_threshold) have bounds checks.

### 9.2 Missing Files — No Boot on Error

**Risk:** If candidate_profile.yaml is missing, discovery loop crashes.

**Mitigation:**
- `load_optional_yaml()` returns {} on missing file; JobFilter defaults to no filters if filters.yaml is missing.
- If candidate_profile.yaml is missing, the `load_optional_yaml()` call returns {}, and CandidateProfile.model_validate({}) still succeeds because all fields have defaults.
- However, if defer_rules.yaml is missing, `load_defer_rules()` raises FileNotFoundError (not optional).

### 9.3 Backward Compat: Legacy Boolean willing_to_relocate

**Risk:** Profiles written before 2026-05-25 have boolean willing_to_relocate; new schema expects tri-state literal.

**Mitigation:** Pydantic field_validator (src/config/schema.py:95–109) coerces False → "no", True → "yes" automatically during validation.

### 9.4 Regex Pattern Errors

**Risk:** User writes invalid regex in exclude_title_patterns or defer_rules.yaml regex entries.

**Mitigation:**
- JobFilter._compile_patterns() logs warnings for invalid regexes but doesn't crash; invalid patterns are skipped.
- DeferRules._compile_patterns() raises re.error if any pattern is invalid; load_defer_rules() propagates the error loudly.

### 9.5 Answer Cache Schema Version Evolution

**Risk:** Future versions of answer_cache.yaml may need structural changes (e.g., new fields for LLM confidence scores).

**Mitigation:** Current schema pins `schema_version: 1`. Load function checks version on read; any mismatch could trigger migration logic (not yet implemented).

### 9.6 Wizard Incomplete State

**Risk:** User starts onboarding but closes browser; candidate_profile.yaml left in partial state.

**Mitigation:**
- Wizard writes backups to config/backups/ *before* overwriting the live file.
- If wizard crash leaves partial YAML, Pydantic validation surfaces errors on next boot.
- User can restore from backup or re-run wizard.

### 9.7 Filter Order Sensitivity

**Risk:** Hard filter check order matters (e.g., exclude_title before require_title could cause subtle bugs).

**Mitigation:** Order is explicit in JobFilter._apply_hard_filters() (lines 109–154); documented in comments and locked in by tests.

### 9.8 Soft Filter Any-vs-All Semantics

**Risk:** Positive keywords using all() semantics means a job is ACCEPT_QUALIFIED only if *all* keywords are present; this breaks non-software profiles whose job descriptions don't hit every skill.

**Mitigation:** Bug fix applied: changed from all() to any() semantics (line 375–378). Now a single matching keyword is sufficient. Tests locked in this behavior (tests/test_job_filter_positive_keywords.py:113–126).

---

## 10. Summary of Data Flow

```
User edits YAML files
  ↓
startup_hook validates candidate_profile.yaml via Pydantic
  ↓
discovery loop:
  - loads companies.yaml (required)
  - loads filters.yaml (optional)
  - loads candidate_profile.yaml (optional)
  - loads search_criteria.yaml (optional)
  - instantiates JobFilter(filters_config)
  ↓
for each job posting fetched:
  - JobFilter.filter_job(job) → hard filters, then soft filters
  - job stored in database with status FILTERED, QUALIFIED, or NEW
  ↓
apply_finisher loads:
  - candidate_profile.yaml (raw text)
  - defer_rules.yaml (compiled patterns)
  - answer_cache.yaml (question-answer pairs)
  ↓
for each form field:
  - defer_rules.classify(label, field_type) → tier 1/2/3
  - tier-1: fill from profile
  - tier-2: draft with LLM, flag needs_review
  - tier-3: defer to human
  - tier-1/2 candidates first check answer_cache for fuzzy hit
  ↓
finisher appends new answer to answer_cache.yaml, persists atomically
  ↓
resume_tailor loads candidate_profile.yaml to build context
resume_reviewer loads resume.tex (after migration) as source-of-truth
```

---

## 11. Files & Ownership Summary

| File | Purpose | Owner | Reads | Writes | Optional? |
|------|---------|-------|-------|--------|-----------|
| `src/filters/job_filter.py` | Hard/soft filter pipeline | Code | - | - | No |
| `src/config/schema.py` | Pydantic validation | Code | - | - | No |
| `config/filters.yaml` | Filter rules | User | discovery, insert_pipeline | wizard backups | Yes |
| `config/candidate_profile.yaml` | Full candidate profile | User | discovery, apply_finisher, resume_tailor | wizard backups | No (if CANDIDATE_PROFILE_PATH set) |
| `config/search_criteria.yaml` | Search filtering (Phase 2+) | User | (informational) | wizard backups | Yes |
| `config/companies.yaml` | Target company list | User | discovery (required) | wizard backups | No |
| `config/defer_rules.yaml` | Form field tier classification | User | apply_finisher | wizard backups | No |
| `data/answer_cache.yaml` | Cached Q&A pairs | Apply finisher | apply_finisher | apply_finisher (append + atomic) | Auto-created |
| `.env.example` | Env var defaults | Dev | CI/user reference | - | Yes (template) |
| `scripts/migrate_yaml_to_tex.py` | Resume migration | Code | - | - | No |
| `tests/test_config_schema*.py` | Schema validation tests | Code | - | - | No |
| `tests/test_job_filter*.py` | Filter behavior tests | Code | - | - | No |
| `tests/test_migrate_yaml_to_tex.py` | Migration script tests | Code | - | - | No |

