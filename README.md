# Agentic Job Applier

SQLite-backed autonomous job discovery and application pipeline with a live FastAPI + React dashboard.

## What The System Does

1. Discovers jobs from Greenhouse, Workday (Apify), and JobSpy-backed boards.
2. Normalizes and deduplicates postings into `job_postings`.
3. Runs staged workers:

- Gate (`NEW -> QUALIFIED/FILTERED`)
- Resume tailor (`QUALIFIED -> tailor_runs`)
- Resume review (`tailor_runs SUCCESS -> review_runs`)
- Apply worker (`review_runs SUCCESS -> apply_runs` + `apply_handoffs`)

1. Exposes operational state in a FastAPI backend (`api/main.py`) and React dashboard (`dashboard/`).
2. Tracks per-stage cost telemetry (`cost_events`) and monthly budget (`budget_settings`).

## Runtime Architecture

- Producer: `main.py` discovery cycle.
- Consumers: `scripts/process_new_jobs.py`, `scripts/process_qualified_jobs.py`, `scripts/process_reviewed_resumes.py`, `scripts/process_apply_jobs.py`.
- Persistence: `src/database/db_manager.py` + `src/database/schema.sql`.
- API + static serving: `api/main.py`.
- Frontend: Vite/React app in `dashboard/`, wired to `/api/*` via React Query.

## Prerequisites

- Python 3.11+
- `uv`
- Node.js 20+
- `latexmk` (tailor/review pipeline)
- `pi` command (tailor/review runtime)
- Chrome + Playwright CDP target (apply worker)

## Setup

```bash
git clone <your-repo-url>
cd agentic-job-applier
uv sync
cp .env.example .env
```

Optional frontend install for local dashboard development:

```bash
npm --prefix dashboard install
```

## Core Commands

Discovery once:

```bash
uv run python main.py
```

Gate worker:

```bash
uv run python -m scripts.process_new_jobs --once --limit 25
```

Tailor worker:

```bash
uv run python -m scripts.process_qualified_jobs --once
```

Review worker:

```bash
uv run python -m scripts.process_reviewed_resumes --once
```

Apply worker:

```bash
uv run python -m scripts.process_apply_jobs --once
```

Pipeline one-shot helper:

```bash
uv run python -m scripts.run_pipeline_once --limit 25
```

## FastAPI + Dashboard

Run backend:

```bash
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Run dashboard dev server:

```bash
npm --prefix dashboard run dev
```

Build dashboard static assets (served by FastAPI fallback routes):

```bash
npm --prefix dashboard run build
```

Useful API checks:

```bash
curl -sS http://127.0.0.1:8000/api/health
curl -sS http://127.0.0.1:8000/api/dashboard/stats
curl -sS "http://127.0.0.1:8000/api/jobs?page=1&page_size=20"
```

## API Surface (Current)

- Dashboard: `GET /api/dashboard/stats`, `GET /api/dashboard/discovery-trend`
- Jobs: `GET /api/jobs`, `GET /api/jobs/{job_hash}/resume`
- Human review: `GET /api/human-review`, `POST /api/human-review/{handoff_id}/complete`, `POST /api/human-review/{handoff_id}/dismiss`
- Failures: `GET /api/failures`, `POST /api/failures/{failure_id}/retry`
- Costs: `GET /api/costs/stats`, `GET /api/costs/daily-trend`, `GET /api/costs/by-stage`
- Budget: `GET /api/budget`, `PUT /api/budget`
- Settings files: `GET /api/settings/files`, `GET /api/settings/profile`, `PUT /api/settings/profile`, `PUT /api/settings/profile/structured`, `POST /api/settings/profile`
- Resume settings: `GET /api/settings/resume`, `PUT /api/settings/resume`, `PUT /api/settings/resume/structured`, `POST /api/settings/resume`, `POST /api/settings/resume/tex`
- Settings downloads: `GET /api/settings/resume/download`, `GET /api/settings/profile/download`

## Database Tables

- Core: `job_postings`, `crawl_history`, `daily_stats`
- Stage runs: `tailor_runs`, `review_runs`, `apply_runs`, `apply_handoffs`
- Cost/budget: `cost_events`, `budget_settings`

## Cost Tracking Configuration

Cost events are forward-only and written by workers per execution attempt. Stage rates are configurable:

- `COST_RATE_GATE_USD`
- `COST_RATE_TAILOR_USD`
- `COST_RATE_REVIEW_USD`
- `COST_RATE_APPLY_USD`
- `COST_RATE_DISCOVERY_USD`

If unset/invalid, stage cost defaults to `0.0`.

## Tailored Resume Download Access

- By default, `GET /api/jobs/{job_hash}/resume` is restricted to local clients (`127.0.0.1`, `::1`, `localhost`).
- To allow remote access intentionally, set `TAILORED_RESUME_DOWNLOAD_TOKEN` and send it via `x-tailored-resume-token`.

## Testing

Deterministic suite:

```bash
uv run pytest -q
```

Focused scraper->agent integration:

```bash
uv run pytest -q tests/test_scraper_to_agent_integration.py
```

Opt-in live model E2E:

```bash
uv run pytest -q --run-live-agent-e2e -m live_agent_e2e
```

Type checking (strict, backend settings surfaces):

```bash
uv run mypy
```

## Docker

Docker is the recommended way to run this on a server. The image is split into three build targets so you only install what you need.

### Image tiers

| Target  | What's included                            | Compose profile | Approx. build time |
| ------- | ------------------------------------------ | --------------- | ------------------ |
| `base`  | Job discovery, gate agent, API + dashboard | _(default)_     | ~3–5 min           |
| `latex` | base + LaTeX + poppler + Node + pi CLI     | `tailor`        | +8–12 min          |
| `full`  | latex + Chromium + Xvfb                    | `full`          | +3–5 min           |

Each tier inherits from the one above it. Docker's layer cache means opting into a higher tier later only builds the delta — already-built layers are reused.

### Profiles and what they run

```
docker compose up -d                   # api, discovery, gate
docker compose --profile tailor up -d  # + tailor, review
docker compose --profile full up -d    # + tailor, review, apply
```

### Quick start

```bash
# 1. Install Docker Engine (Ubuntu)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # then log out and back in

# 2. Clone and configure
git clone <repo-url> && cd agentic-job-applier
cp .env.docker.example .env     # fill in API keys
# ensure config/ files are present (candidate_profile.yaml, resume_content.yaml, etc.)

# 3. Start core pipeline
docker compose up -d

# 4. Opt into tailoring when ready (zero downtime, reuses cached base layers)
docker compose --profile tailor up -d

# 5. Opt into browser apply when ready
docker compose --profile full up -d
```

Dashboard is available at `http://<server-ip>:8000` once `api` is healthy.

### Upgrading an existing stack

Adding a profile to a running stack is safe. Existing containers are left untouched; Compose only starts the new services against the shared data volume.

```bash
git pull
docker compose build          # rebuilds only changed layers
docker compose --profile <current-profile> up -d
```

### Useful commands

```bash
docker compose ps                      # status of all services
docker compose logs -f workers         # tail logs for a service
docker compose restart gate            # restart one service
docker compose down                    # stop all (data volumes preserved)
docker compose down -v                 # stop all and delete volumes (destructive)
docker compose exec api bash           # shell into a running container
```

### Chrome profile (apply service only)

The apply service works without a Chrome profile, but the Simplify autofill extension requires one. To import your profile:

```bash
# On your local machine
bash scripts/docker/profile_export.sh

# Copy tarball to server, then on the server:
bash scripts/docker/profile_import.sh chrome-profile.tar.gz
docker compose --profile full up -d
```

## Deployment (Linux/Systemd)

Systemd units live in `deploy/` for discovery timer and continuous workers. See `deploy/README.md` for end-to-end setup, including:

- `job-discovery.timer` + `job-discovery.service`
- `job-agent-worker.service`
- `job-tailor-worker.service`
- `job-review-worker.service`
- `job-apply-worker.service`
- `job-apply-chrome.service`

## Source Of Truth Docs

- Operational/spec docs: `.aqa/spec/index.md`
- Agent collaboration rules: `AGENTS.md`

## License

MIT
