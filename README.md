# Agentic Job Applier

> ⚠️ **Alpha software.** Auto-submit is intentionally **disabled** in this release. The apply worker fills forms in a real browser but stops before submitting — you review the filled form and click Submit yourself. See [Status & Safety](#status--safety) before running.

A self-hosted, AI-driven job discovery and application pipeline. It crawls a long list of ATSes, aggregators, and remote-only boards (full list below), decides which postings are worth applying to, generates a tailored LaTeX resume per job, runs a second-pass review, and drives a real browser to fill the application form (you submit it yourself). State lives in a local SQLite database, and a FastAPI + React dashboard exposes everything that happens at runtime.

### Supported sources

| Category                     | Sources                                                              |
| ---------------------------- | -------------------------------------------------------------------- |
| ATS / company career portals | Greenhouse, Workday, Lever, Ashby, iCIMS, Taleo                      |
| Aggregators (via JobSpy)     | Indeed, LinkedIn, Glassdoor                                          |
| Direct LinkedIn scraper      | LinkedIn (separate from JobSpy)                                      |
| Remote-only boards           | Remotive, Himalayas, Working Nomads                                  |
| General job boards           | The Muse, Adzuna, Startup Jobs                                       |
| Curated GitHub repos         | e.g. SimplifyJobs internships repos via the GitHub fetcher           |
| Custom company watchers      | Direct career-page polling for non-ATS sites                         |

<!-- screenshots TBD -->

## Status & Safety

This project is **alpha software**. The discovery, gate, tailor, review, and dashboard pieces work end-to-end. The auto-apply piece intentionally **does not** auto-submit — see below.

### What works
- Discovery across the sources listed above.
- Gate agent qualifies or filters each posting against your profile.
- Tailor agent generates a job-specific LaTeX resume + PDF.
- Review agent does a second-pass verdict on the tailored resume.
- Dashboard pipeline timeline updates as each job moves through.
- Apply worker opens a real browser, navigates to the posting, and triggers Simplify autofill on the form.

### What does NOT work, on purpose
- **Auto-submit is hard-disabled in code.** The apply worker fills the form and stops before clicking Submit. There is no env var, CLI flag, or config option that enables auto-submit in this release. The worker creates a `PENDING_REVIEW` handoff visible in the dashboard's Human Review queue. You review the filled form in the browser, click Submit yourself, and mark the application complete in the dashboard.
- **Multi-provider BYOK.** Onboarding accepts only an OpenAI API key. The provider abstraction at `src/providers/factory.py` is ready for Anthropic, Gemini, OpenRouter, and Codex, but the tailor and review workers are still hardcoded to OpenAI — see [#35](https://github.com/joeyspagnoli/agentic-job-applier/issues/35).

### Recommended human-in-the-loop flow

1. Set `OPENAI_API_KEY` in `.env`.
2. `docker compose --profile full up -d`.
3. Open the dashboard, complete onboarding.
4. Wait for jobs to flow through to **PENDING_REVIEW** (Human Review queue).
5. For each pending review: open the job in your browser (the apply worker has already filled the form via Simplify autofill in your local Chrome profile), verify the application looks right, click Submit yourself, then click "Mark Complete" in the dashboard.

Treat the AI's output as a draft. Read the tailored resume before letting it represent you. **Do not write a wrapper that auto-submits forms.** If you do, you own the consequences. The disclosure process for security-relevant changes is in [`SECURITY.md`](SECURITY.md).

## Quickstart (Docker)

Docker is the recommended way to run the project. The image is split into three build targets so you only install what you need.

```bash
git clone https://github.com/joeyspagnoli/agentic-job-applier.git
cd agentic-job-applier
cp .env.example .env
# Open .env and set OPENAI_API_KEY.
docker compose up -d
```

Open `http://localhost:8000` once the `api` container is healthy. The first visit redirects to the in-app onboarding wizard described below.

The default `docker compose up` starts the **base** profile (api, discovery, gate). Tailoring (which also runs the reviewer in-process) and browser-driven apply are opt-in profiles documented under [Profiles and opt-in tiers](#profiles-and-opt-in-tiers).

To stop the stack while preserving data:

```bash
docker compose down
```

To stop and discard all SQLite state and logs:

```bash
docker compose down -v
```

## Onboarding

The dashboard refuses to load until `config/candidate_profile.yaml`, `config/resume_content.yaml`, and `config/filters.yaml` are populated. The onboarding wizard at `/onboarding` walks through the six steps below and writes the YAML files for you. It runs automatically the first time you open the dashboard.

| Step | Label              | What it captures                                                                                                  |
| ---- | ------------------ | ----------------------------------------------------------------------------------------------------------------- |
| 1    | About You          | Name, email, phone, location, LinkedIn, professional summary. Written to `config/candidate_profile.yaml`.         |
| 2    | Target Roles       | Target titles, strongest areas, experience highlights for the resume tailor, and job-board search terms.          |
| 3    | Resume             | Upload a `.pdf`, `.tex`, `.yaml`, or `.yml` resume. Parsed into the structured `config/resume_content.yaml`.       |
| 4    | Filters            | Salary range, job types, remote/hybrid requirement, title exclusion patterns, company blocklist. Writes `config/filters.yaml`. |
| 5    | AI Provider        | Enter your OpenAI API key. Multi-provider BYOK (Anthropic, Gemini, OpenRouter, Codex) is tracked in [#35](https://github.com/joeyspagnoli/agentic-job-applier/issues/35). |
| 6    | Watchlist          | Optional list of companies to track explicitly. Resolved against known Greenhouse slugs and written to `config/companies.yaml`. |

After the final step the dashboard becomes available. Re-run any step later from **Settings** in the sidebar; raw YAML is editable there too.

## Profiles and opt-in tiers

The Compose file ships three docker compose profiles. Each one inherits the layers of the previous tier, so opting up later only builds the delta.

| Profile  | Build target | Services started                            | Adds to image                                       | Approx. extra build time |
| -------- | ------------ | ------------------------------------------- | --------------------------------------------------- | ------------------------ |
| _(none)_ | `base`       | `api`, `discovery`, `gate`                  | Python deps, FastAPI, prebuilt React dashboard      | ~3-5 min                 |
| `tailor` | `latex`      | base + `tailor` (runs review in-process)    | TeX Live, `latexmk`, poppler-utils                  | +8-12 min                |
| `full`   | `full`       | base + tailor + `apply`                     | Chromium (via Playwright) and Xvfb virtual display  | +3-5 min                 |

Bring up a higher tier with:

```bash
docker compose --profile tailor up -d
docker compose --profile full up -d
```

Adding a profile to a running stack is safe. Existing containers stay up and the new services share the same `app-data` and `app-logs` volumes.

Useful operational commands:

```bash
docker compose ps                      # status of all services
docker compose logs -f gate            # tail one service
docker compose restart tailor          # restart one service
docker compose exec api bash           # shell into a running container
./scripts/docker/start_stack.sh        # host-level start
./scripts/docker/stop_stack.sh         # host-level stop
./scripts/docker/restart_stack.sh      # host-level restart
```

The dashboard's TopBar power menu can also dispatch Stop/Restart while the stack is up. When everything is already down, use the host-level scripts.

### Chrome profile (apply service only)

The apply worker runs without a Chrome profile, but the Simplify autofill extension only loads if you import yours. From a workstation already signed in:

```bash
bash scripts/docker/profile_export.sh        # produces chrome-profile.tar.gz
# Copy the tarball to the server, then on the server:
bash scripts/docker/profile_import.sh chrome-profile.tar.gz
docker compose --profile full up -d
```

## Configuration

`.env.example` is the canonical list of every environment variable the pipeline reads. Copy it to `.env` and fill in the keys you need. The most important ones:

| Variable                         | Required for                                | Notes                                                     |
| -------------------------------- | ------------------------------------------- | --------------------------------------------------------- |
| `OPENAI_API_KEY`                 | Gate, tailor, review                        | Required. Workers idle gracefully if unset.               |
| `NTFY_TOPIC`                     | Push alerts on terminal failures            | Blank disables alerts.                                    |
| `RUN_INTERVAL_MINUTES`           | Discovery cadence                           | Defaults to 30.                                           |
| `API_PORT`                       | Host port for the dashboard                 | Defaults to 8000.                                         |
| `CDP_PORT`                       | Chrome remote-debug port                    | Apply service only. Defaults to 9222.                     |
| `TAILORED_RESUME_DOWNLOAD_TOKEN` | Remote download of tailored PDFs            | Leave blank to keep the endpoint local-only.              |

User-facing YAML files live under `config/` and are persisted via the Docker `./config:/app/config` bind mount:

| File                          | Owner                                  |
| ----------------------------- | -------------------------------------- |
| `config/candidate_profile.yaml` | About You + Target Roles wizard steps |
| `config/resume_content.yaml`  | Resume wizard step                     |
| `config/filters.yaml`         | Filters wizard step                    |
| `config/companies.yaml`       | Watchlist wizard step                  |

Cost telemetry rates (`COST_RATE_GATE_USD`, `COST_RATE_TAILOR_USD`, `COST_RATE_REVIEW_USD`, `COST_RATE_APPLY_USD`, `COST_RATE_DISCOVERY_USD`) default to `0.0` if unset and feed the dashboard cost charts.

## Local development

Use this path if you are contributing or running individual workers without Docker.

Prerequisites: Python 3.11+, [`uv`](https://docs.astral.sh/uv/), Node.js 20+. The tailor worker also requires `latexmk` (TeX Live); the apply worker additionally needs Chrome and Playwright.

```bash
git clone https://github.com/joeyspagnoli/agentic-job-applier.git
cd agentic-job-applier
uv sync
npm --prefix dashboard install
cp .env.example .env
```

Run the API and dashboard:

```bash
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
npm --prefix dashboard run dev      # Vite dev server with HMR
npm --prefix dashboard run build    # production bundle, served by FastAPI fallback
```

Run the pipeline stages individually:

```bash
uv run python main.py                                                   # one discovery cycle
uv run python -m scripts.process_new_jobs --once --limit 25             # gate
uv run python -m scripts.process_qualified_jobs --once                  # tailor + review (single pipeline)
uv run python -m scripts.process_apply_jobs --once                      # apply
uv run python -m scripts.run_pipeline_once --limit 25                   # discovery + gate one-shot
```

Smoke-check the API:

```bash
curl -sS http://127.0.0.1:8000/api/health
curl -sS http://127.0.0.1:8000/api/dashboard/stats
curl -sS "http://127.0.0.1:8000/api/jobs?page=1&page_size=20"
```

## Architecture

The pipeline is a chain of workers that move rows through a SQLite database (`data/jobs.db`).

```
discovery -> gate -> tailor + review -> apply
   |          |              |              |
fetchers   apply-       Instructor +    Playwright
           decider      LaTeX/latexmk   + Simplify
```

| Stage     | Producer / consumer                          | Inputs                                  | Outputs                                                |
| --------- | -------------------------------------------- | --------------------------------------- | ------------------------------------------------------ |
| Discovery | `main.py`                                    | `config/companies.yaml`, fetchers       | New rows in `job_postings`, `crawl_history`            |
| Gate      | `scripts/process_new_jobs.py`                | `NEW` postings, candidate profile       | `QUALIFIED` or `FILTERED` status; cost events          |
| Tailor + Review | `scripts/process_qualified_jobs.py`    | `QUALIFIED` postings, `resume_content.yaml` | `tailor_runs` + matching `review_runs` rows, tailored LaTeX/PDF artifacts |
| Apply     | `scripts/process_apply_jobs.py`              | Successful `review_runs`                | `apply_runs` rows, `apply_handoffs` at `PENDING_REVIEW` (forms filled, never auto-submitted in this release) |

State lives in:

- `data/jobs.db` — primary SQLite database (schema: `src/database/schema.sql`).
- `data/tailored_resumes/<job_hash>/` — generated LaTeX, PDF, and tailoring metadata.
- `logs/job_monitor.log` — rolling log file.
- `config/` — user-edited YAML, mounted into containers.

Key directories:

- `api/` — FastAPI app and dashboard fallback routes.
- `dashboard/` — Vite + React app served at `/`.
- `src/` — fetchers, agents, database manager, utilities.
- `scripts/` — worker entry points and operator helpers.
- `deploy/` — systemd units and helper scripts for Linux deployments.

By default `GET /api/jobs/{job_hash}/resume` is restricted to localhost. Set `TAILORED_RESUME_DOWNLOAD_TOKEN` and pass it via the `x-tailored-resume-token` header to enable remote downloads.

## Testing

Backend (Python):

```bash
uv run pytest -q                                              # deterministic, network-free
uv run pytest -q tests/test_scraper_to_agent_integration.py   # focused integration
uv run pytest -q --run-live-agent-e2e -m live_agent_e2e       # opt-in live model E2E
uv run mypy                                                   # strict, project-wide
```

Frontend (dashboard):

```bash
npm --prefix dashboard run lint        # ESLint with --max-warnings 0
npm --prefix dashboard run typecheck   # tsc --noEmit
npm --prefix dashboard run test        # Vitest with coverage
npm --prefix dashboard run format:check
```

CI runs the same commands. Run them locally before opening a PR.

## Deployment (Linux/systemd)

For long-running deployments on a Linux host without Docker, systemd units live in `deploy/`. They cover the discovery timer, all four worker loops, the apply-side Chrome service, and an alert helper. End-to-end setup, including required environment variables and `texlive-full` install, is documented in [`deploy/README.md`](deploy/README.md).

## Contributing

Bug reports, fetcher additions, dashboard polish, and documentation updates are all welcome. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) for the dev environment, coding standards, commit message format, and PR flow.

## Security

Do not file public GitHub issues for security vulnerabilities. The disclosure process and supported versions are in [`SECURITY.md`](SECURITY.md).

## License

Released under the [MIT License](LICENSE).
