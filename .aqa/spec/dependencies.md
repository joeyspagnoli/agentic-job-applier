# Dependencies

## Python Packages (pyproject)
- Core: aiosqlite (SQLite async), httpx (HTTP), apify-client (Apify actors), python-jobspy (board scraping), loguru (logging), pydantic (models), pyyaml (config), python-dotenv (env), apscheduler (not used in main entrypoint but available), google-adk (agent), pytest/pytest-asyncio (tests) [pyproject.toml:5-18](pyproject.toml:5-18).

## External Services / APIs
- **Greenhouse public API**: no auth; fetcher uses `https://boards-api.greenhouse.io/v1/boards/{id}/jobs` [src/fetchers/greenhouse_fetcher.py:31-71](src/fetchers/greenhouse_fetcher.py:31-71).
- **Apify Workday actor**: requires `APIFY_API_TOKEN`; runs actor `gooyer.co/myworkdayjobs` and fetches dataset items [src/fetchers/apify_fetcher.py:21-86](src/fetchers/apify_fetcher.py:21-86).
- **JobSpy**: scraping library for job boards; no explicit API keys shown, but network/proxy requirements may apply (LinkedIn often needs proxies) [src/fetchers/jobspy_fetcher.py:28-96](src/fetchers/jobspy_fetcher.py:28-96).

## Environment Variables
- Core runtime: `DATABASE_PATH`, `LOG_LEVEL`, `LOG_FILE`, `SQLITE_JOURNAL_MODE`
- Source credentials: `APIFY_API_TOKEN` (Workday via Apify)
- Model credentials: `OPENAI_API_KEY` (required for live root gate execution), optional other provider keys
- Gate queue controls: `AGENT_BATCH_SIZE`, `AGENT_BATCH_LIMIT`, `AGENT_POLL_INTERVAL_SECONDS`
- Retry controls: `AGENT_MAX_RETRIES`, `AGENT_RETRY_BACKOFF_SECONDS`, `AGENT_RETRY_BACKOFF_MULTIPLIER`
- Notification controls: `NTFY_TOPIC`, `NTFY_SERVER`, `NTFY_TOKEN`, `NTFY_PRIORITY`
- Profile override: `CANDIDATE_PROFILE_PATH`

## Platform / Runtime
- Python 3.11 pinned (.python-version) [.python-version:1](.python-version:1).
- SQLite database stored at `DATABASE_PATH` default `data/jobs.db` [main.py:98-101](main.py:98-101) [ .env.example:4-8](.env.example:4-8).
- uv recommended for dependency management and running scripts [deploy/README.md:7-22](deploy/README.md:7-22).

## Deployment & Scheduling
- Producer: `job-discovery.service` + `job-discovery.timer` (30-minute cadence)
- Consumer: `job-agent-worker.service` (`process_new_jobs --loop`)
- Optional systemd failure hook: `job-agent-alert@.service`

## Data / Files
- `config/companies.yaml` drives source targets and board query terms.
- `config/search_criteria.yaml` defines role/title and keyword targeting defaults.
- `config/candidate_profile.yaml` defines gate prompt profile and default board terms.
