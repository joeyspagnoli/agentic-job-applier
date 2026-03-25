# Dependencies

## Python Packages (pyproject.toml)
- Core runtime: aiosqlite (SQLite async), httpx (HTTP), apify-client (Apify actors), python-jobspy (board scraping), loguru (logging), pydantic (models), pyyaml (config), python-dotenv (env), google-adk (agent framework), litellm (multi-provider LLM), aiohttp (async HTTP), markdownify (HTML to markdown)
- Auth/crypto: authlib, cryptography
- Serialization: protobuf, python-multipart
- Scheduling: apscheduler (available but not used in main entrypoint)
- Dev: pytest, pytest-asyncio, pip-audit

## External Services / APIs
- **Greenhouse public API**: no auth; fetcher uses `https://boards-api.greenhouse.io/v1/boards/{id}/jobs`; handles 404/429 gracefully.
- **Apify Workday actor**: requires `APIFY_API_TOKEN`; runs actor `gooyer.co/myworkdayjobs` and fetches dataset items. Bridges sync actor calls via asyncio executor.
- **JobSpy**: scraping library for job boards; scrapes with `hours_old=72`; no explicit API keys shown, but network/proxy requirements may apply (LinkedIn often needs proxies).
- **OpenAI via LiteLLM**: gate decider uses `openai/gpt-5.1-codex-mini` through LiteLLM wrapper in ADK; requires `OPENAI_API_KEY`.
- **ntfy.sh**: optional push notifications for terminal failures; requires `NTFY_TOPIC` and optionally `NTFY_TOKEN`.

## Environment Variables
- Core runtime: `DATABASE_PATH`, `LOG_LEVEL`, `LOG_FILE`, `SQLITE_JOURNAL_MODE`
- Source credentials: `APIFY_API_TOKEN` (Workday via Apify)
- Model credentials: `OPENAI_API_KEY` (required for live root gate and pi-mono execution), optional other provider keys (`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`)
- Gate queue controls: `AGENT_BATCH_SIZE`, `AGENT_BATCH_LIMIT`, `AGENT_POLL_INTERVAL_SECONDS`, `AGENT_CLAIM_LEASE_SECONDS` (default 900)
- Gate retry controls: `AGENT_MAX_RETRIES`, `AGENT_RETRY_BACKOFF_SECONDS`, `AGENT_RETRY_BACKOFF_MULTIPLIER`
- Tailor worker controls: `TAILOR_POLL_INTERVAL_SECONDS` (default 30), `TAILOR_MAX_RETRIES` (default 2), `TAILOR_RETRY_BACKOFF_SECONDS` (default 600), `TAILOR_RETRY_BACKOFF_MULTIPLIER` (default 2), `TAILOR_CLAIM_LEASE_SECONDS` (default 7200), `TAILOR_OUTPUT_DIR` (default data/tailored_resumes)
- Review worker controls: `REVIEW_POLL_INTERVAL_SECONDS` (default 30), `REVIEW_MAX_RETRIES` (default 2), `REVIEW_RETRY_BACKOFF_SECONDS` (default 600), `REVIEW_RETRY_BACKOFF_MULTIPLIER` (default 2), `REVIEW_CLAIM_LEASE_SECONDS` (default 7200), `REVIEW_OUTPUT_DIR` (default data/tailored_resumes)
- Review base refs: `REVIEW_BASE_RESUME_YAML_PATH`, `REVIEW_BASE_RESUME_TEX_PATH`, `REVIEW_BASE_RESUME_PDF_PATH`
- Notification controls: `NTFY_TOPIC`, `NTFY_SERVER`, `NTFY_TOKEN`, `NTFY_PRIORITY`
- Profile override: `CANDIDATE_PROFILE_PATH`
- Pi command config: `PI_CODING_AGENT_COMMAND`, `PI_CODING_AGENT_COMMAND_ARGV` (JSON string array)
- Optional model overrides: `RESUME_REVIEW_MODEL`

## Platform / Runtime
- Python 3.11 pinned (.python-version).
- SQLite database stored at `DATABASE_PATH` default `data/jobs.db`; resolved via `src/utils/paths.resolve_database_path()`.
- uv recommended for dependency management and running scripts.
- Resume tailoring/review compile helpers require local TeX tooling (`latexmk`).
- Review geometry/text tooling requires poppler CLIs: `pdfinfo`, `pdftotext`, `pdftoppm`.

## Deployment & Scheduling
- Producer: `job-discovery.service` + `job-discovery.timer` (30-minute cadence)
- Gate consumer: `job-agent-worker.service` (`process_new_jobs --loop`), claim-based with 900s lease
- Tailor consumer: `job-tailor-worker.service` (`process_qualified_jobs --loop`), `Restart=always`, 30s backoff
- Review consumer: `job-review-worker.service` (`process_reviewed_resumes --loop`), `Restart=always`, 30s backoff
- Optional systemd failure hook: `job-agent-alert@.service`
- System dependencies for tailor/review: texlive-full, latexmk, poppler-utils, pi-mono (or `PI_CODING_AGENT_COMMAND` / `PI_CODING_AGENT_COMMAND_ARGV`)

## Data / Files
- `config/companies.yaml` drives source targets and board query terms.
- `config/search_criteria.yaml` defines role/title and keyword targeting defaults, including title include patterns.
- `config/candidate_profile.yaml` defines gate prompt profile, default board terms, and title include patterns.
- `config/resume_content.yaml` is the YAML-canonical resume source used by the pi-mono tailor workflow.
- `config/resume_base.tex` and `config/resume_base.pdf` are pre-compiled base resume reference artifacts for review comparisons.
