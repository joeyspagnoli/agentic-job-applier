# Interfaces

Six buckets:
1. HTTP API
2. CLI worker scripts
3. YAML config files
4. `.env` contract
5. Persistent artifact paths
6. External-process interfaces (tectonic, agent-browser, host Chrome CDP)

## 1. HTTP API

Single FastAPI app at port `${API_PORT:-8000}`. Single-user, localhost-scoped — no built-in auth. All errors follow `{ok: false, code, message, details}` (`api/errors.py:18-69`). Every JSON success body wraps the payload in `{ok: true, ...}`.

### Full endpoint table

| Method | Path | Router | Purpose | Side effects |
|---|---|---|---|---|
| GET | `/api/health` | `health.py` | Liveness + polling interval | none |
| GET | `/api/system/health` | `system.py` | Reports `openai_key_configured` | none |
| POST | `/api/system/stop` | `system.py` | Dispatches `scripts/docker/stop_stack.sh` | spawns subprocess |
| POST | `/api/system/restart` | `system.py` | Dispatches `scripts/docker/restart_stack.sh` | spawns subprocess |
| POST | `/api/system/fetch-jobs` | `system.py` | Triggers immediate discovery cycle | spawns subprocess |
| GET | `/api/status/autonomous-readiness` | `status.py` | Hard-requirement matrix for enabling autonomous mode | probes OpenAI key, profile, resume |
| GET | `/api/status/chrome?os=mac\|linux\|windows` | `status.py` | CDP reachability + OS-specific launch command hint | probes `${CHROME_CDP_URL}/json/version` |
| GET | `/api/settings/autonomous-mode` | `status.py` | Derived global toggle state from per-stage modes | DB read |
| POST | `/api/settings/autonomous-mode` | `status.py` | Flips all three stage modes between `both` (on) and `opt_in` (off) atomically | DB write + `supervisor.notify_mode_changed()` |
| GET | `/api/jobs?search=&page=&page_size=&status=&source=&has_tailor_run=` | `jobs.py` | Paginated jobs table; joins `job_postings` with latest tailor/review/apply rows | none |
| GET | `/api/jobs/{job_hash}/resume` | `jobs.py` | Returns latest tailored PDF | none |
| POST | `/api/jobs/import` | `jobs.py` | Manual posting import | inserts `job_postings` row |
| POST | `/api/jobs/{job_hash}/tailor` | `tailor_runs.py` | Enqueue tailor run; body `{apply_after: bool}`; 202 | inserts PENDING `tailor_runs`, queues `BackgroundTask` |
| GET | `/api/tailor-runs/{id}` | `tailor_runs.py` | Poll one tailor run | none |
| GET | `/api/tailor-runs/{id}/plan` | `tailor_runs.py` | Read planner-rationale JSON | file read |
| DELETE | `/api/tailor-runs/{id}` | `tailor_runs.py` | Soft-delete tailor run | sets `deleted_at`; best-effort artifact cleanup |
| POST | `/api/tailor-runs/{id}/retry` | `tailor_runs.py` | Soft-delete and re-enqueue atomically | DB transaction + BackgroundTask |
| POST | `/api/jobs/{job_hash}/apply` | `apply_runs.py` | Enqueue apply run; body `{resume_mode: "base" \| "tailored"}` | inserts PENDING `apply_runs`; on `resume_mode=base` also compiles base resume and synthesizes tailor + review rows; spawns detached `asyncio.create_task` |
| GET | `/api/apply-runs/{id}` | `apply_runs.py` | Poll one apply run | none |
| DELETE | `/api/apply-runs/{id}` | `apply_runs.py` | Soft-delete apply run | sets `deleted_at` |
| GET | `/api/human-review?search=&confidence=&page=&page_size=` | `human_review.py` | Handoff queue, paginated | none |
| POST | `/api/human-review/{id}/complete` | `human_review.py` | Mark APPROVED → flips job to APPLIED | atomic handoff + job_postings update |
| POST | `/api/human-review/{id}/dismiss` | `human_review.py` | Mark REJECTED → flips job to REJECTED | same |
| POST | `/api/human-review/{id}/answers` | `human_review.py` | Save reviewer's deferred-question answers | writes `user_answers_json`; appends to `data/answer_cache.yaml` |
| POST | `/api/human-review/{id}/relaunch-apply` | `human_review.py` | Re-enqueue apply with the saved answers | inserts new apply_run, flips handoff to APPROVED, spawns task |
| POST | `/api/human-review/by-job/{job_hash}/relaunch-apply` | `human_review.py` | Same flow, addressed by job_hash | same |
| GET | `/api/failures?search=&stage=&status=&page=` | `failures.py` | Unified failures feed across stages | none |
| POST | `/api/failures/{failure_id}/retry` | `failures.py` | Reset per-stage failure markers and requeue | stage-specific reset method |
| GET | `/api/dashboard/stats` | `dashboard.py` | KPI cards, funnel, source breakdown, applications over time | aggregate queries |
| GET | `/api/dashboard/discovery-trend?range=7d\|30d` | `dashboard.py` | Discovery trend points | aggregate query |
| GET | `/api/costs/stats` | `costs.py` | Total spend, avg-per-app, API calls today | aggregate |
| GET | `/api/costs/daily-trend?range=7d\|30d\|all` | `costs.py` | Per-day or per-month spend | aggregate |
| GET | `/api/costs/by-stage` | `costs.py` | Current-month spend per stage | aggregate |
| GET | `/api/pipeline/progress` | `pipeline.py` | SSE stream (heartbeat-only stub) | none |
| GET | `/api/settings/profile` | `settings_profile.py` | Read YAML + parsed structured form | none |
| PUT | `/api/settings/profile` | `settings_profile.py` | Write YAML text | backup + write + clear prompt cache |
| PUT | `/api/settings/profile/structured` | `settings_profile.py` | Write from structured form fields | same |
| POST | `/api/settings/profile` | `settings_profile.py` | Upload profile YAML file | same |
| GET | `/api/settings/profile/download` | `settings_profile.py` | Download profile YAML | none |
| GET | `/api/settings/resume` | `settings_resume.py` | Read `config/resume.tex` + contract pass + manifest preview | none |
| POST | `/api/settings/resume` | `settings_resume.py` | Upload `.tex`; validates contract; persists on pass | backup + write |
| GET | `/api/settings/resume/download` | `settings_resume.py` | Download `config/resume.tex` | none |
| PUT/POST | `/api/settings/resume/{pdf,tex,structured}` | `settings_resume.py` | Deprecated; returns 410 with `ENDPOINT_REMOVED` | none |
| GET | `/api/settings/api-keys` | `settings_api_keys.py` | List configured status of `ALLOWED_API_KEY_NAMES` | reads `.env` |
| PUT | `/api/settings/api-keys/{key_name}` | `settings_api_keys.py` | Upsert one key | writes `.env` |
| DELETE | `/api/settings/api-keys/{key_name}` | `settings_api_keys.py` | Remove one key | writes `.env` |
| POST | `/api/settings/api-keys/validate-adzuna` | `settings_api_keys.py` | Live-probe Adzuna API | HTTP call |
| GET | `/api/budget` | `settings_budget.py` | Monthly budget + current spend rollup | DB query |
| PUT | `/api/budget` | `settings_budget.py` | Update monthly budget | DB write |
| GET | `/api/settings/filters` | `settings_filters.py` | Read `config/filters.yaml` | none |
| PUT | `/api/settings/filters` | `settings_filters.py` | Write `config/filters.yaml` | backup + write |
| GET | `/api/settings/sources` | `settings_filters.py` | Read `config/companies.yaml` | none |
| PUT | `/api/settings/sources` | `settings_filters.py` | Write `config/companies.yaml` | backup + write |
| POST | `/api/settings/provider` | `settings_provider.py` | Persist OpenAI API key; rejects other providers with `UNSUPPORTED_PROVIDER` | writes `.env` |
| GET | `/api/settings/onboarding-status` | `settings_provider.py` | First-visit gating check (profile + resume present) | file existence checks |
| GET | `/api/settings/files` | `settings_files.py` | Settings file metadata (mtime, size) | file stat |
| GET | `/api/system-settings/automation` | `system_settings.py` | Read current per-stage automation modes | DB read |
| PATCH | `/api/system-settings/automation` | `system_settings.py` | Update one or more stage modes | DB write |

### Error codes

Stable machine-readable codes returned with HTTP status:

| Code | Status | Where it fires |
|---|---|---|
| `INVALID_YAML` | 400 | YAML body fails parse |
| `MISSING_API_KEY` | 400 | Provider POST without an API key |
| `UNSUPPORTED_PROVIDER` | 400 | Provider POST with anything but OpenAI |
| `JOB_NOT_FOUND` | 404 | Tailor/apply/resume endpoints when `job_hash` is unknown |
| `FILE_NOT_FOUND` | 404 | Resume/plan download when artifact is missing |
| `TAILOR_RUN_NOT_FOUND` / `APPLY_RUN_NOT_FOUND` | 404 | Direct run lookups |
| `MODE_AUTONOMOUS` | 409 | User-triggered tailor while `tailor_mode=autonomous` |
| `RUN_ALREADY_EXISTS` | 409 | Tailor enqueue when an active tailor row already exists for this job |
| `APPLY_RUN_IN_FLIGHT` | 409 | Apply enqueue when an active apply row already exists |
| `BUDGET_EXCEEDED` | 409 | Either enqueue path when monthly cost rollup has hit the budget |
| `AUTONOMOUS_REQUIREMENTS_NOT_MET` | 409 | Autonomous-toggle ON when OpenAI key / profile / resume are missing |
| `HANDOFF_ALREADY_RESOLVED` | 409 | Complete/dismiss/relaunch on a non-`PENDING_REVIEW` handoff |
| `ENDPOINT_REMOVED` | 410 | Deprecated resume PUT/POST variants |
| `NO_REVIEW_RUN` | 422 | Apply enqueue without a SUCCESS review run (and `resume_mode != base`) |
| `INVALID_RESUME_TEX` | 422 | Resume upload that fails contract validation; `details.errors` carries `ValidatorError` list |
| `BASE_COMPILE_FAILED` | 422 | `resume_mode=base` apply when `config/resume.tex` fails to compile |
| `SYSTEM_ACTION_DISPATCH_FAILED` | 500 | Shell subprocess exits non-zero |
| `ANSWER_CACHE_SEED_FAILED` | 500 | `data/answer_cache.yaml` append fails |
| `ADZUNA_AUTH_FAILED` | 401 | Adzuna validation rejects credentials |
| `ADZUNA_UNREACHABLE` / `ADZUNA_ERROR` | 502 | Adzuna network/API failure |
| `INVALID_RESPONSE_FORMAT` / `EMPTY_RESPONSE_BODY` | (client-side) | The dashboard client throws these when a 2xx response isn't JSON |

### Background-task lifecycle

Two flavors of background work:

- **`BackgroundTasks.add_task` for tailor.** Runs after the HTTP 202 is sent. Opens its own `DatabaseManager`. On success, if `apply_after=true` was persisted, calls `enqueue_apply_run_for_job` which itself spawns the apply task via `asyncio.create_task` (`api/routers/tailor_runs.py:63-125,306-314`).
- **`asyncio.create_task` for apply.** Detached, fires immediately so the browser flow doesn't wait for the autonomous loop's poll cycle. Reads supervisor config (output dir, CDP URL) if a supervisor is active, else falls back to env (`api/routers/apply_runs.py:48-115`).

The race between a user-triggered task and the autonomous loop is resolved at the database layer: the per-job single-slot constraint on `(job_hash, status IN (PENDING, RUNNING), deleted_at IS NULL)` makes whoever inserts the PENDING row first win.

## 2. CLI worker scripts

Each worker script supports `--once`, `--loop`, and `--limit` flags and is also importable for the supervisor.

### `python main.py`

Runs one discovery cycle and exits. Used by:
- `python main.py` directly for local dev
- `deploy/job-discovery.service` (oneshot) triggered by `deploy/job-discovery.timer` every 30 minutes

The supervisor calls `run_discovery_loop(interval_minutes=30)` directly, not the CLI form.

Env knobs: `RUN_INTERVAL_MINUTES`, `LOG_FILE`, `LOG_LEVEL`.

### `python -m scripts.process_new_jobs`

Gate worker.

| Flag | Default | Meaning |
|---|---|---|
| `--once` | (default) | One batch then exit |
| `--loop` | | Continuous polling |
| `--limit N` | 25 (`AGENT_BATCH_LIMIT`/`AGENT_BATCH_SIZE`) | Max jobs claimed per cycle |

Env knobs: `OPENAI_API_KEY` (required; idles with warning if missing), `AGENT_POLL_INTERVAL_SECONDS` (60), `AGENT_MAX_RETRIES` (3), `AGENT_RETRY_BACKOFF_SECONDS` (300), `AGENT_RETRY_BACKOFF_MULTIPLIER` (3), `AGENT_CLAIM_LEASE_SECONDS` (900), `CANDIDATE_PROFILE_PATH`.

### `python -m scripts.process_qualified_jobs`

Tailor + review worker (single pipeline).

| Flag | Default | Meaning |
|---|---|---|
| `--once` | (default) | One claim + run then exit |
| `--loop` | | Continuous polling |

Env knobs: `TAILOR_POLL_INTERVAL_SECONDS` (30), `TAILOR_MAX_RETRIES` (2), `TAILOR_CLAIM_LEASE_SECONDS` (7200), `TAILOR_OUTPUT_DIR` (`data/tailored_resumes`), `RESUME_TAILOR_MODEL` (`openai/gpt-5.4`), `RESUME_REVIEWER_MODEL` (`openai/gpt-5-mini`), `TAILOR_RESUME_TEX_PATH`, `RESUME_COMPILER` (`tectonic` | `latexmk`), `TECTONIC_TIMEOUT_SECONDS` (240).

### `python -m scripts.process_apply_jobs`

Apply worker.

| Flag | Default | Meaning |
|---|---|---|
| `--once` | (default) | One claim + browser flow then exit |
| `--loop` | | Continuous polling (with Chrome reachability preflight) |
| `--cdp-url` | `CHROME_CDP_URL` env | Override Chrome CDP endpoint |

Env knobs: `APPLY_POLL_INTERVAL_SECONDS` (60), `APPLY_MAX_RETRIES` (2), `APPLY_CLAIM_LEASE_SECONDS` (1800), `APPLY_RETRY_BACKOFF_SECONDS` (1800), `APPLY_RETRY_BACKOFF_MULTIPLIER` (2), `APPLY_OUTPUT_DIR` (`data/apply_runs`), `CHROME_CDP_URL` (`http://host.docker.internal:9222` in Docker, `http://localhost:9222` on systemd), `SAFE_MODE` (`false`), `LITELLM_LOCAL_MODEL_COST_MAP` (`true`).

### Other operator scripts

- `scripts/run_pipeline_once.py --limit N` — discovery + gate in one pass for smoke testing
- `scripts/status.py` — print pipeline state from the database
- `scripts/query_jobs.py` — ad-hoc job-table queries
- `scripts/migrate_yaml_to_tex.py` — idempotent migration from legacy `resume_content.yaml` to `config/resume.tex` (`scripts/migrate_yaml_to_tex.py:1-120`)
- `scripts/build_greenhouse_slug_table.py` — refresh `dashboard/src/data/greenhouse_known_slugs.json` for the onboarding watchlist
- `scripts/find_greenhouse_id.py`, `scripts/discover_taleo_portals.py` — operator helpers for adding new companies
- `scripts/docker/start_stack.sh`, `stop_stack.sh`, `restart_stack.sh` — Docker wrappers

## 3. YAML config files

All under `config/`. The Docker bind mount maps `./config:/app/config`. The wizard writes backups to `config/backups/<name>_YYYYMMDD_HHMMSS.yaml` before any overwrite.

### `config/candidate_profile.yaml` (mandatory for autonomous mode)

Validated by `src/config/schema.py:CandidateProfile` at startup via `_validate_candidate_profile_on_startup` (`api/services/migrations.py:24-65`). Top-level shape:

```yaml
profile:
  summary: str
  contact:
    full_name: str
    email: str
    phone: str
    location: str
    linkedin: str | null
    portfolio: str | null
  work_authorization:
    citizenship_country_label: str
    authorized_to_work_us: "yes" | "no" | "unknown"
    requires_sponsorship_now_or_future: "yes" | "no" | "unknown"
  education_entries:
    - school: str
      degree_name: str
      field_of_study: str
      start_year: int
      end_year: int
      is_current: bool
      gpa: str | null
      minors: list | null
  target_roles: [str]
  strongest_areas: [str]
  experience_highlights: [str]
  hard_filters: [regex]
  preferences: [str]
  domains: [str]   # 8 user-facing domains; optional
search_defaults:
  job_board_search_terms: [str]
apply_prefs:
  pronouns: str
  eeo_defaults:
    gender: str
    race_ethnicity: str
    veteran_status: str
    disability_status: str
  sponsorship_required_now_or_future: "yes" | "no" | "unknown"
  work_authorized_us: "yes" | "no" | "unknown"
  compensation:
    expected_salary_min_usd: int | null
    expected_salary_max_usd: int | null
    expected_hourly_rate_usd: int | null
  availability:
    earliest_start_date: str
    notice_period_weeks: int | null
  location_preferences:
    willing_to_relocate: "yes" | "no" | "open_to_discussion"
    preferred_cities: [str]
    willing_remote: bool
    willing_hybrid: bool
  application_defaults:
    how_did_you_hear: str
    tier2_confidence_threshold: float  # [0.0, 1.0]; default 1.0
  languages:
    - language: str
      proficiency: "basic" | "conversational" | "fluent" | "native"
```

Every model uses `ConfigDict(extra="allow")` so the schema evolves backward-compatibly. A field validator on `willing_to_relocate` coerces legacy `bool` (False → "no", True → "yes") to the tri-state literal (`src/config/schema.py:95-109`).

### `config/filters.yaml` (optional)

```yaml
hard_filters:
  exclude_job_types: [str]          # e.g., "Full-time" if you only want internships
  exclude_title_patterns: [regex]   # case-insensitive
  require_title_patterns: [regex]   # at least one must match
  exclude_locations: [str]          # substring match
  require_remote: bool
  exclude_companies: [str]          # exact, case-insensitive
  max_days_old: int                 # 0 disables
  min_salary_usd: int               # 0 disables
  max_salary_usd: int               # 0 disables
soft_filters:
  negative_keywords: [str]          # any match → REJECT_FILTERED
  positive_keywords: [str]          # any match → ACCEPT_QUALIFIED (any-semantics, not all)
  max_experience_years: int         # parses "N+ years" in description
```

Read by `src/orchestrator/discovery.py` and consumed by `src/filters/job_filter.py:JobFilter`. Empty / missing file → no filters applied.

### `config/companies.yaml` (mandatory for discovery)

```yaml
greenhouse_companies:
  Anthropic:
    greenhouse_id: anthropic
    industry: software_tech
    priority: 1
workday_companies:
  Merck:
    workday_url: https://merck.wd5.myworkdayjobs.com/...
    industry: pharma_biotech
    priority: 3
taleo_companies: { ... }
icims_companies: { ... }
lever_companies: { ... }
ashby_companies: { ... }

adzuna:
  enabled: bool
  search_terms: [str]
linkedin:
  enabled: bool
  search_terms: [str]
job_boards:
  indeed:
    enabled: bool
    search_terms: [str]
github_repos:
  - repo: "SimplifyJobs/Summer2025-Internships"
    enabled: bool
    domains: [str]   # optional per-entry filter
watched_pages:
  - url: ...
    company: ...
```

`src/orchestrator/domains.py:apply_domain_filter_to_config` filters watchlist sections by the candidate's domains. Untagged companies always pass — keeps unknown-industry companies from being silently dropped.

### `config/defer_rules.yaml`

Loaded by `src/agents/apply_finisher/defer_rules.py:load_defer_rules`.

```yaml
always_defer_labels:
  - regex: '(?i)sponsor|visa|authorize.*sponsor'
  - regex: '(?i)salary|compensation|desired pay'
draft_and_flag_labels:
  - regex: '(?i)why .{0,30}(this role|this position|us|company|interest)'
  - regex: '(?i)tell us about|describe.*experience|hardest problem'
  - regex: '(?i)cover letter'
bypass_field_types: [file, hidden, submit, button]
never_defer_overrides: []
```

The classifier checks `always_defer_labels` first (Tier 3 unless `never_defer_overrides` matches), then `draft_and_flag_labels` (Tier 2), else Tier 1 (auto-fill from profile or cached answer).

### `config/resume.tex` (mandatory for tailor / autonomous)

LaTeX source-of-truth for the resume. Validated against `docs/resume-tex-contract.md` at upload and on every tailor pipeline run. The contract enforces:

- `\section{...}` headings must match the tailorable allowlist (Experience / Work Experience / Professional Experience / Employment / Employment History / Work History / Career Experience for entries with `kind="experience"`; Projects / Side Projects / Personal Projects / Open Source Projects / Selected Projects for `kind="projects"`).
- Each entry under a tailorable section must start with one of six entry-header macros (`\resumeSubheading`, `\cventry`, `\cvitem`, `\cvevent`, `\runsubsection \descript \location`, `\item {\textbf{Role}}\hfill{\textbf{Dates}}`) or one of two fallbacks (`\textbf{Role at Company}` or `\textbf{Role}\hfill Dates` on a line by itself).
- Bullets must be `\resumeItem{body}`, `\cvline{label}{body}`, or `\item ...` inside an itemize-like block under a recognized header.
- All braces in bullet bodies must balance.

Contract violations fail upload with `INVALID_RESUME_TEX` + line-numbered errors (`src/agents/resume_tailor/validator.py`).

### `data/answer_cache.yaml`

Owned by the apply finisher; machine-mutable.

```yaml
schema_version: 1
entries:
  - question_text: "Why do you want to work here?"
    question_normalized: "why do you want to work here"
    answer: "At $COMPANY I admire ..."
    category: "motivation"
    company_specific: false
    company: null
```

Lookup: normalize → exact-hash match → RapidFuzz `token_set_ratio >= 85%`. Per-company entries beat anonymized at equal scores. `$COMPANY` is substituted at retrieval (`src/agents/apply_finisher/answer_cache.py:195-237`). Writes are atomic temp-file + rename to avoid mid-write corruption.

## 4. `.env` contract

Loaded by `dotenv.load_dotenv` at startup of every process (worker scripts and API). `.env.example` is the canonical template.

| Variable | Default | Required for | Notes |
|---|---|---|---|
| `OPENAI_API_KEY` | — | gate / tailor / review / finisher | Workers idle with warning if unset |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | — | Adzuna fetcher | Optional pair; both or neither |
| `NTFY_TOPIC` | "" | ntfy alerts | Empty disables alerts entirely |
| `NTFY_SERVER` | `https://ntfy.sh` | ntfy alerts | Override for self-hosted ntfy |
| `NTFY_TOKEN` | "" | ntfy alerts | Bearer auth for private topics |
| `NTFY_PRIORITY` | `default` | ntfy alerts | |
| `RUN_INTERVAL_MINUTES` | `30` | discovery loop | |
| `API_PORT` | `8000` | Docker host port mapping | |
| `CHROME_CDP_URL` | `http://host.docker.internal:9222` | apply worker | Linux maps `host.docker.internal:host-gateway` |
| `SAFE_MODE` | `false` | apply submit gate | Kill switch; gate returns `(False, "safe_mode")` |
| `LITELLM_LOCAL_MODEL_COST_MAP` | `true` | cost tracking | Force litellm bundled prices; no network lookup |
| `DATABASE_PATH` | `data/jobs.db` | every process | Absolute or repo-relative |
| `SQLITE_JOURNAL_MODE` | `WAL` | aiosqlite | |
| `LOG_FILE` | `logs/job_monitor.log` | logger | Auto-creates parent dir |
| `LOG_LEVEL` | `INFO` | logger | |
| `AGENT_BATCH_LIMIT` / `AGENT_BATCH_SIZE` | `25` | gate | |
| `AGENT_POLL_INTERVAL_SECONDS` | `60` | gate | |
| `AGENT_MAX_RETRIES` | `3` | gate | |
| `AGENT_RETRY_BACKOFF_SECONDS` | `300` | gate | |
| `AGENT_RETRY_BACKOFF_MULTIPLIER` | `3` | gate | Exponential |
| `AGENT_CLAIM_LEASE_SECONDS` | `900` | gate | |
| `CANDIDATE_PROFILE_PATH` | `config/candidate_profile.yaml` | gate prompt cache | |
| `TAILOR_POLL_INTERVAL_SECONDS` | `30` | tailor | |
| `TAILOR_MAX_RETRIES` | `2` | tailor | |
| `TAILOR_CLAIM_LEASE_SECONDS` | `7200` | tailor | Stale-row reaper threshold |
| `TAILOR_OUTPUT_DIR` | `data/tailored_resumes` | tailor | |
| `TAILOR_RESUME_TEX_PATH` | `config/resume.tex` | tailor | |
| `RESUME_TAILOR_MODEL` | `openai/gpt-5.4` | tailor | Prose-tuned model required |
| `RESUME_REVIEWER_MODEL` | `openai/gpt-5-mini` | reviewer | |
| `RESUME_COMPILER` | `tectonic` | tailor | `latexmk` falls back to legacy path |
| `TECTONIC_TIMEOUT_SECONDS` | `240` | tailor | Cold CTAN cache compiles can run long |
| `APPLY_POLL_INTERVAL_SECONDS` | `60` | apply | |
| `APPLY_MAX_RETRIES` | `2` | apply | |
| `APPLY_CLAIM_LEASE_SECONDS` | `1800` | apply | |
| `APPLY_RETRY_BACKOFF_SECONDS` | `1800` | apply | |
| `APPLY_RETRY_BACKOFF_MULTIPLIER` | `2` | apply | |
| `APPLY_OUTPUT_DIR` | `data/apply_runs` | apply | |
| `GATE_MODE` / `TAILOR_MODE` / `APPLY_MODE` | unset | first boot only | Seeds `system_settings.automation.*_mode` if rows don't exist; never overrides existing rows on restart |

API keys are persisted unencrypted in `.env`. The `cryptography` library is a declared dependency but currently unused for key storage — operators on shared machines should add a reverse proxy or secrets manager themselves.

## 5. Persistent artifact paths

```
data/
├── jobs.db                                  # SQLite, single file
├── tailored_resumes/
│   └── <job_hash>/
│       ├── base/
│       │   ├── base.tex
│       │   ├── base.pdf
│       │   └── base.log
│       ├── tailored_v1/
│       │   ├── tailored_v1.tex
│       │   ├── tailored_v1.pdf
│       │   ├── tailored_v1.log
│       │   └── tailored_v1.plan.json        # planner rationale
│       └── tailored_v2/                     # optional, only on retry
│           └── tailored_v2.{tex,pdf,log}
├── base_resume/
│   └── <sha256-of-config-resume-tex>.pdf    # cache for resume_mode=base apply path
├── apply_runs/
│   └── <apply_run_id>/
│       ├── screenshot_pre_submit.png
│       └── dom_snapshot.html
├── answer_cache.yaml                        # finisher's durable Q&A cache
├── codex/                                   # CODEX_HOME (reserved)
└── (named volume mount points)

logs/
└── job_monitor.log                          # loguru, 10MB rotation, 1-week retention

config/
├── candidate_profile.yaml
├── resume.tex
├── filters.yaml
├── companies.yaml
├── defer_rules.yaml
├── search_criteria.yaml                     # informational; not currently enforced
└── backups/
    └── <name>_YYYYMMDD_HHMMSS.yaml          # wizard writes these on every save
```

The Docker named volumes are `app-data` (everything under `/app/data`), `app-logs` (`/app/logs`), and `tectonic-cache` (`/tectonic-cache`, mapped via `XDG_CACHE_HOME`). `./config:/app/config` is a bind mount so users edit YAML files directly on the host.

## 6. External-process interfaces

### Tectonic

Invoked by `src/agents/resume_tailor/compiler.py:compile_resume_tex` as:

```
tectonic -X compile --outdir <variant_dir> <variant>.tex
```

`XDG_CACHE_HOME=/tectonic-cache` (Docker volume) so CTAN packages survive container restart. Build-time prewarm compiles `deploy/tectonic-prewarm.tex` to populate the cache (`Dockerfile:61-72`).

Multi-arch binaries vendored under `deploy/tectonic/tectonic-{amd64,arm64}.tar.gz`. `deploy/tectonic/fetch.sh` refreshes both in one shot (`TECTONIC_VERSION=0.15.0` default).

### agent-browser

Rust CDP CLI vendored under `deploy/agent-browser/agent-browser-{amd64,arm64}`. Used by the apply finisher's `tools.py:agent_browser` tool (generic escape hatch) and the `_FILL_COMBOBOX_JS_TEMPLATE` (which the CLI executes against the connected Chrome). The CLI has a per-process lock (`browser_cli.py:47`) as a runtime backstop in case Pydantic-AI ever fires parallel tool calls.

In Docker the binary is bundled but the apply flow drives host Chrome via Playwright instead. The CLI's session-attach pattern (`agent-browser connect <cdp_url>`) is used by the finisher tab-management helper to ensure subsequent `snapshot` / `click` / `fill` commands target the right page.

### Host Chrome CDP

The user starts Chrome on the host with `--remote-debugging-port=9222` before turning on autonomous apply. Inside the container the apply loop connects to:

- **Docker (Mac/Windows):** `http://host.docker.internal:9222` resolved by Docker Desktop automatically
- **Docker (Linux):** `host.docker.internal` mapped to `host-gateway` via `extra_hosts:` in compose
- **systemd:** `http://localhost:9222` (Chrome runs on the same host)

The HTTP `Host` header is forced to `localhost:<port>` for both the `/json/version` probe (`httpx`) and the Playwright WebSocket upgrade — Chrome 148+ rejects requests whose Host header doesn't match `localhost` or an IP literal. The override is skipped if the URL already uses localhost or an IP (`src/agents/apply_worker/browser.py:158-199`).

`check_chrome_reachable` runs every apply-loop cycle before claiming. If it returns False the loop sleeps without claiming, which is intentional — it prevents FAILED rows when the user closes Chrome.

### Simplify Copilot browser extension

Detected by polling for the `simplify-jobs-shadow-root` element with one of the autofill labels (`Autofill`, `Autofill all fields with AI`, `Fill`, `Continue filling`). The apply worker uploads the tailored resume *before* clicking Simplify (Simplify's click navigates to a preview URL and clobbers the file input), then re-uploads after Simplify settles to make sure the tailored version wins. Settle is polling-based: filled-field count stable for 2s or 30s elapsed (`src/agents/apply_worker/browser.py:567-625`).

Version dependency: Simplify v2.4.x shadow-root structure is hardcoded. Future major versions could change aria-labels or DOM structure.

### ntfy.sh (optional)

Outbound POST to `${NTFY_SERVER}/${NTFY_TOPIC}` with title, message, priority, optional tags, and `Authorization: Bearer ${NTFY_TOKEN}`. Fire-and-forget: a failed POST logs a warning at the call site, never raises. The systemd path has `deploy/job-agent-alert@.service` which triggers on worker `OnFailure=` and sends a templated ntfy message.
