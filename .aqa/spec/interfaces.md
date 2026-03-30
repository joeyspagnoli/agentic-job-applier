# Interfaces

## External interfaces

### Job-source interfaces

- Greenhouse boards API (`src/fetchers/greenhouse_fetcher.py:157-188`).
- Workday via Apify actor/dataset (`src/fetchers/apify_fetcher.py:157-209`).
- JobSpy board scraping (`src/fetchers/jobspy_fetcher.py:17-333`).
- Ashby/Lever/LinkedIn/GitHub-listings/career-page surfaces (`src/fetchers/ashby_fetcher.py:72-233`, `src/fetchers/lever_fetcher.py:74-233`, `src/fetchers/linkedin_fetcher.py:127-234`, `src/fetchers/github_repo_fetcher.py:112-305`, `src/fetchers/career_page_watcher.py:117-194`).

### Model/tool interfaces

- Gate decider prompt/runtime contract is JSON-only decision output with bounded context formatting (`src/agents/root_apply_decider/prompts.py:351-507`, `src/agents/root_apply_decider/runtime.py:80-126`).
- Resume tailor/review CLIs expose deterministic `{"ok": true|false, ...}` wrappers (`scripts/resume_tailor_tools.py:30-247`, `scripts/resume_review_tools.py:35-344`).

## FastAPI HTTP interface (`api/main.py`)

### Core operational endpoints

- `GET /api/health`
- `GET /api/dashboard/stats`
- `GET /api/dashboard/discovery-trend?range=7d|30d`
- `GET /api/jobs`
- `GET /api/jobs/{job_hash}/resume`
- `GET /api/human-review`
- `POST /api/human-review/{handoff_id}/complete`
- `POST /api/human-review/{handoff_id}/dismiss`
- `GET /api/failures`
- `POST /api/failures/{failure_id}/retry`
- `GET /api/costs/stats`
- `GET /api/costs/daily-trend?range=7d|30d|all`
- `GET /api/costs/by-stage`
- `GET /api/budget`
- `PUT /api/budget`

### Settings endpoints

- `GET /api/settings/files`
- `GET /api/settings/profile`
- `POST /api/settings/profile`
- `POST /api/settings/profile/upload`
- `GET /api/settings/profile/download`
- `GET /api/settings/resume`
- `POST /api/settings/resume`
- `POST /api/settings/resume/upload`
- `POST /api/settings/resume/upload-tex`
- `GET /api/settings/resume/download`
- `GET /api/settings/filters`
- `POST /api/settings/filters`
- `GET /api/settings/sources`
- `POST /api/settings/sources`

Evidence: `api/main.py:1479-2630`, `api/main.py:2938-3659`.

## Contract notes and caveats

- API-level custom error envelope exists, but request validation failures can still emit framework-native FastAPI 422 payloads for typed/query validation paths (`api/main.py:472-496`, `api/main.py:1451-1476`, `api/main.py:1738-1742`).
- Retry IDs use stage-qualified forms (`GATE:<job_hash>`, `TAILOR:<id>`, `REVIEW:<id>`, `APPLY:<id>`), and malformed numeric segments can currently raise unhandled parsing errors (`api/main.py:2527-2629`).
- Settings routes are not fully uniform in response envelope keys (`metadata` vs `profile`/`resume`; some missing-file responses omit `metadata`) (`api/main.py:3147-3296`, `api/main.py:3448-3473`, `api/main.py:3529-3622`).

## Frontend client + DTO interface

- `dashboard/src/lib/api/client.ts` enforces JSON content-type and non-empty body rules, and normalizes API errors to `ApiError` with `code` and `details` (`dashboard/src/lib/api/client.ts:37-127`).
- DTO shapes are centralized in `dashboard/src/lib/api/types.ts` and adapted into UI models via `dashboard/src/lib/api/adapters.ts` (`dashboard/src/lib/api/types.ts:136-170`, `dashboard/src/lib/api/adapters.ts:48-216`).
