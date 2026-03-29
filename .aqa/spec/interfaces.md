# Interfaces

## External Interfaces

### Job Sources

- Greenhouse boards API
- Apify Workday actor (`gooyer.co/myworkdayjobs`)
- JobSpy scraping interface

### Model Providers

- Gate stage uses ADK + OpenAI model wiring.
- Tailor/review/apply stages invoke their respective runtimes and tool contracts.

### Dashboard HTTP API (`api/main.py`)

Routes currently exposed:

- `GET /api/health`
- `GET /api/dashboard/stats`
- `GET /api/dashboard/discovery-trend?range=7d|30d`
- `GET /api/jobs`
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
- `GET /api/settings/files`
- `POST /api/settings/resume`
- `POST /api/settings/profile`
- `GET /api/settings/resume/download`
- `GET /api/settings/profile/download`

Error payloads are normalized as:

```json
{
  "ok": false,
  "code": "ERROR_CODE",
  "message": "Human-readable message",
  "details": {}
}
```

### Frontend API Client Contract

Dashboard consumes snake_case DTO payloads and adapts them in `dashboard/src/lib/api/adapters.ts`.

## Internal Interfaces

### Queue Claim APIs (`DatabaseManager`)

- Gate claim on `job_postings`
- Tailor claim on `tailor_runs`
- Review claim on `review_runs`
- Apply claim on `apply_runs`

### Failure Retry Identifier Contract

`/api/failures/{failure_id}/retry` expects stage-qualified IDs:

- `GATE:<job_hash>`
- `TAILOR:<tailor_run_id>`
- `REVIEW:<review_run_id>`
- `APPLY:<apply_run_id>`

### Cost Tracking Interface

Workers emit cost events through `record_stage_cost_event(...)` in `src/utils/cost_tracking.py`.

Each event stores:
- Stage
- Optional `job_hash`
- Optional `run_id`
- Resolved `cost_usd`
- Optional metadata JSON
