# Dependencies

## Python Packages (pyproject)
- Core: aiosqlite (SQLite async), httpx (HTTP), apify-client (Apify actors), python-jobspy (board scraping), loguru (logging), pydantic (models), pyyaml (config), python-dotenv (env), apscheduler (not used in main entrypoint but available), google-adk (agent), pytest/pytest-asyncio (tests) [pyproject.toml:5-18](pyproject.toml:5-18).

## External Services / APIs
- **Greenhouse public API**: no auth; fetcher uses `https://boards-api.greenhouse.io/v1/boards/{id}/jobs` [src/fetchers/greenhouse_fetcher.py:31-71](src/fetchers/greenhouse_fetcher.py:31-71).
- **Apify Workday actor**: requires `APIFY_API_TOKEN`; runs actor `gooyer.co/myworkdayjobs` and fetches dataset items [src/fetchers/apify_fetcher.py:21-86](src/fetchers/apify_fetcher.py:21-86).
- **JobSpy**: scraping library for job boards; no explicit API keys shown, but network/proxy requirements may apply (LinkedIn often needs proxies) [src/fetchers/jobspy_fetcher.py:28-96](src/fetchers/jobspy_fetcher.py:28-96).

## Environment Variables
- From `.env.example`: `APIFY_API_TOKEN`, `DATABASE_PATH`, `LOG_LEVEL`, `LOG_FILE`, `RUN_INTERVAL_MINUTES`, agent keys (GOOGLE_API_KEY/OPENAI_API_KEY/ANTHROPIC_API_KEY), `AGENT_BATCH_SIZE` [ .env.example:1-20](.env.example:1-20).
- Agent processing: optional `CANDIDATE_PROFILE_PATH`, `AGENT_BATCH_LIMIT`/`AGENT_BATCH_SIZE`, `AGENT_POLL_INTERVAL_SECONDS` [scripts/process_new_jobs.py:41-76](scripts/process_new_jobs.py:41-76) [scripts/process_new_jobs.py:130-200](scripts/process_new_jobs.py:130-200).

## Platform / Runtime
- Python 3.11 pinned (.python-version) [.python-version:1](.python-version:1).
- SQLite database stored at `DATABASE_PATH` default `data/jobs.db` [main.py:98-101](main.py:98-101) [ .env.example:4-8](.env.example:4-8).
- uv recommended for dependency management and running scripts [deploy/README.md:7-22](deploy/README.md:7-22).

## Deployment & Scheduling
- systemd oneshot service and 30-minute timer; requires editing placeholders (User, WorkingDirectory, PATH, ExecStart) before enabling [deploy/job-discovery.service:5-17](deploy/job-discovery.service:5-17) [deploy/job-discovery.timer:4-12](deploy/job-discovery.timer:4-12) [deploy/README.md:27-54](deploy/README.md:27-54).

## Data / Files
- `config/companies.yaml` drives source targets; `config/search_criteria.yaml` defines desired/undesired roles and signals for later filtering [config/companies.yaml:1-120](config/companies.yaml:1-120) [config/search_criteria.yaml:1-70](config/search_criteria.yaml:1-70).
