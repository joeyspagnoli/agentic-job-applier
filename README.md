# Agentic Job Applier

> ⚠️ **Alpha software.** Auto-submit fires only when a strict binary gate passes — all required fields filled, no pending Tier-2 drafts, no Tier-3 deferred questions. Otherwise the form lands in `NEEDS_REVIEW` for you to finish. `SAFE_MODE=true` disables auto-submit globally. See [Status & Safety](#status--safety) before running.

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

This project is **alpha software**. The discovery, gate, tailor, review, and dashboard pieces work end-to-end. The auto-apply finisher is live on Greenhouse and Ashby with a binary submit gate.

### What works
- Discovery across the sources listed above.
- Gate agent qualifies or filters each posting against your profile.
- Tailor agent generates a job-specific LaTeX resume + PDF.
- Review agent does a second-pass verdict on the tailored resume.
- Dashboard pipeline timeline updates as each job moves through.
- Apply worker opens a real browser, navigates to the posting, and triggers Simplify autofill on the form.
- **Apply finisher drives Greenhouse + Ashby form completion and auto-submits when the binary gate passes:** (a) all required fields are filled, (b) no Tier-2 drafts pending review, (c) no Tier-3 questions deferred. Otherwise the apply lands `NEEDS_REVIEW`. `SAFE_MODE=true` disables auto-submit globally regardless of gate outcome.

### What does NOT work, on purpose
- **Multi-provider BYOK.** Onboarding accepts only an OpenAI API key. The provider abstraction at `src/providers/factory.py` is ready for Anthropic, Gemini, OpenRouter, and Codex, but the tailor and review workers are still hardcoded to OpenAI — see [#35](https://github.com/joeyspagnoli/agentic-job-applier/issues/35).

### Recommended human-in-the-loop flow

1. Set `OPENAI_API_KEY` in `.env`.
2. Start host Chrome with the debug port (see [Host Chrome setup](#host-chrome-setup)).
3. `docker compose up -d`.
4. Open the dashboard, complete onboarding, then flip the **AUTONOMOUS** toggle in the top bar to ON.
5. Wait for jobs to flow through. When the binary gate passes the finisher auto-submits; otherwise the job lands in the **NEEDS_REVIEW** queue.
6. For each `NEEDS_REVIEW` job: open the job in your browser (the apply worker has already filled the form via Simplify autofill in your host Chrome), verify the application looks right, complete any deferred questions, click Submit yourself, then click "Mark Complete" in the dashboard.

Treat the AI's output as a draft. Read the tailored resume before letting it represent you. **Do not write a wrapper that auto-submits forms.** If you do, you own the consequences. The disclosure process for security-relevant changes is in [`SECURITY.md`](SECURITY.md).

## Quickstart (Docker)

Docker is the recommended way to run the project. One image, one
service, one command — `docker compose up -d` brings the entire app
online. The image bundles the FastAPI API, the React dashboard, and
the tectonic LaTeX engine; the discovery / gate / tailor / apply
loops run as asyncio tasks inside the API process.

```bash
git clone https://github.com/joeyspagnoli/agentic-job-applier.git
cd agentic-job-applier
cp .env.example .env
# Open .env and set OPENAI_API_KEY.
docker compose up -d
```

Open `http://localhost:8000` once the `app` container is healthy.
The first visit redirects to the in-app onboarding wizard described below.

By default the gate, tailor, and apply loops idle so a brand-new
user does not burn LLM dollars. Flip the **AUTONOMOUS** toggle in
the top bar to ON to enable them. Discovery always runs.

To stop the stack while preserving data:

```bash
docker compose down
```

To stop and discard all SQLite state and logs:

```bash
docker compose down -v
```

### Host Chrome setup

The apply loop drives your **host Chrome** over the Chrome DevTools
Protocol — there is no Chromium bundled inside the container any
more. Start Chrome with the debug port before enabling autonomous
mode (or before clicking the Apply button on a job):

```bash
# macOS
open -a "Google Chrome" --args --remote-debugging-port=9222

# Linux
google-chrome --remote-debugging-port=9222 &

# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

The top-bar **Chrome ready / offline** chip mirrors reachability and
shows the right command for your OS. The apply loop sleeps without
claiming whenever Chrome is unreachable, so closing Chrome never
produces FAILED rows.

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

### Adzuna (optional job board)

Adzuna is a free, API-backed job aggregator covering 12+ countries. It's used here as a stable alternative to scraping Glassdoor — it returns structured listings (including salary ranges) without needing proxies or browser automation. You can skip it during onboarding and enable it later from Settings.

**Getting your credentials**

1. Go to [developer.adzuna.com](https://developer.adzuna.com) and create a free account.
2. Once logged in, create a new application — any name works.
3. You'll receive an **App ID** and an **App Key**. You need both.

Enter them in Step 5 of the onboarding wizard (or under **Settings → API Keys**). The wizard validates the credentials against the live API before saving, so typos are caught immediately. Once saved, `adzuna.enabled` in `config/companies.yaml` is flipped on automatically and the fetcher runs on every discovery cycle.

## Operational commands

```bash
docker compose ps                      # service status
docker compose logs -f app             # tail the single app container
docker compose restart app             # restart the app
docker compose exec app bash           # shell into the running container
./scripts/docker/start_stack.sh        # host-level start
./scripts/docker/stop_stack.sh         # host-level stop
./scripts/docker/restart_stack.sh      # host-level restart
```

## Configuration

`.env.example` is the canonical list of every environment variable the pipeline reads. Copy it to `.env` and fill in the keys you need. The most important ones:

| Variable                         | Required for                                | Notes                                                     |
| -------------------------------- | ------------------------------------------- | --------------------------------------------------------- |
| `OPENAI_API_KEY`                 | Gate, tailor, review                        | Required. Workers idle gracefully if unset.               |
| `NTFY_TOPIC`                     | Push alerts on terminal failures            | Blank disables alerts.                                    |
| `RUN_INTERVAL_MINUTES`           | Discovery cadence                           | Defaults to 30.                                           |
| `API_PORT`                       | Host port for the dashboard                 | Defaults to 8000.                                         |
| `CHROME_CDP_URL`                 | Apply loop → host Chrome CDP endpoint       | Defaults to `http://host.docker.internal:9222`. The probe + Playwright handshake force `Host: localhost:<port>` so Chrome 148+'s host-check accepts the request regardless of the hostname in the URL. |
| `SAFE_MODE`                      | Apply finisher kill switch                  | Set `true` to disable auto-submit globally; forms still fill, outcome lands `NEEDS_REVIEW`. Defaults to `false`. |
| `LITELLM_LOCAL_MODEL_COST_MAP`   | Cost tracking                               | Use litellm's bundled pricing table; avoids outbound calls for price data. Defaults to `true`. |

User-facing YAML files live under `config/` and are persisted via the Docker `./config:/app/config` bind mount:

| File                          | Owner                                  |
| ----------------------------- | -------------------------------------- |
| `config/candidate_profile.yaml` | About You + Target Roles wizard steps |
| `config/resume_content.yaml`  | Resume wizard step                     |
| `config/filters.yaml`         | Filters wizard step                    |
| `config/companies.yaml`       | Watchlist wizard step                  |


## Local development

Use this path if you are contributing or running individual workers without Docker.

Prerequisites: Python 3.11+, [`uv`](https://docs.astral.sh/uv/), Node.js 20+. The tailor worker requires `tectonic` (`brew install tectonic` on macOS); the apply worker needs a host Chrome running with `--remote-debugging-port=9222`. Playwright drives that host Chrome over CDP — no in-image browser is installed.

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
| Apply     | `scripts/process_apply_jobs.py`              | Successful `review_runs`                | `apply_runs` rows; auto-submitted when binary gate passes, otherwise `apply_handoffs` at `NEEDS_REVIEW` |

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
