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
- Gate retry controls: `AGENT_MAX_RETRIES`, `AGENT_RETRY_BACKOFF_SECONDS`, `AGENT_RETRY_BACKOFF_MULTIPLIER`
- Tailor worker controls: `TAILOR_POLL_INTERVAL_SECONDS` (default 30), `TAILOR_MAX_RETRIES` (default 2), `TAILOR_RETRY_BACKOFF_SECONDS` (default 600), `TAILOR_RETRY_BACKOFF_MULTIPLIER` (default 2), `TAILOR_CLAIM_LEASE_SECONDS` (default 7200), `TAILOR_OUTPUT_DIR` (default data/tailored_resumes)
- Review worker controls: `REVIEW_POLL_INTERVAL_SECONDS` (default 30), `REVIEW_MAX_RETRIES` (default 2), `REVIEW_RETRY_BACKOFF_SECONDS` (default 600), `REVIEW_RETRY_BACKOFF_MULTIPLIER` (default 2), `REVIEW_CLAIM_LEASE_SECONDS` (default 7200), `REVIEW_OUTPUT_DIR` (default data/tailored_resumes)
- Review base refs: `REVIEW_BASE_RESUME_YAML_PATH`, `REVIEW_BASE_RESUME_TEX_PATH`, `REVIEW_BASE_RESUME_PDF_PATH`
- Notification controls: `NTFY_TOPIC`, `NTFY_SERVER`, `NTFY_TOKEN`, `NTFY_PRIORITY`
- Profile override: `CANDIDATE_PROFILE_PATH`
- Resume tailor command override: `PI_CODING_AGENT_COMMAND`
- Optional review model override: `RESUME_REVIEW_MODEL`

## Platform / Runtime
- Python 3.11 pinned (.python-version) [.python-version:1](.python-version:1).
- SQLite database stored at `DATABASE_PATH` default `data/jobs.db` [main.py:98-101](main.py:98-101) [ .env.example:4-8](.env.example:4-8).
- uv recommended for dependency management and running scripts [deploy/README.md:7-22](deploy/README.md:7-22).
- Resume tailoring/review compile helpers require local TeX tooling (`latexmk`).
- Review geometry/text tooling requires poppler CLIs: `pdfinfo`, `pdftotext`, `pdftoppm`.

## Deployment & Scheduling
- Producer: `job-discovery.service` + `job-discovery.timer` (30-minute cadence)
- Gate consumer: `job-agent-worker.service` (`process_new_jobs --loop`)
- Tailor consumer: `job-tailor-worker.service` (`process_qualified_jobs --loop`), `Restart=always`, 30s backoff
- Review consumer: `job-review-worker.service` (`process_reviewed_resumes --loop`), `Restart=always`, 30s backoff
- Optional systemd failure hook: `job-agent-alert@.service`
- System dependencies for tailor/review: texlive-full, latexmk, poppler-utils, pi-mono (or `PI_CODING_AGENT_COMMAND`)

## Data / Files
- `config/companies.yaml` drives source targets and board query terms.
- `config/search_criteria.yaml` defines role/title and keyword targeting defaults.
- `config/candidate_profile.yaml` defines gate prompt profile and default board terms.
- `config/resume_content.yaml` is the YAML-canonical resume source used by the pi-mono tailor workflow.
