# Dependencies

## Python Packages (from `pyproject.toml`)
- Runtime packages: 18
  - `aiosqlite`, `httpx`, `apify-client`, `python-jobspy`, `loguru`, `pydantic`, `pyyaml`, `python-dotenv`
  - `google-adk`, `litellm`
  - `playwright` (browser automation client)
  - `aiohttp`, `authlib`, `cryptography`, `markdownify`, `protobuf`, `python-multipart`, `apscheduler`
- Dev packages: 3 (`pytest`, `pytest-asyncio`, `pip-audit`)

## External Services / APIs
- Greenhouse public API (no key).
- Apify actor (`gooyer.co/myworkdayjobs`) with `APIFY_API_TOKEN`.
- JobSpy-backed board scraping.
- OpenAI via LiteLLM/ADK (`OPENAI_API_KEY`) for gate + pi workflows.
- ntfy (optional alerts) via `NTFY_TOPIC`.

## Local System Dependencies
- Python 3.11+.
- SQLite runtime via stdlib `sqlite3`.
- `uv` for environment management.
- Resume tailor/review: `latexmk` (and typically full TeX install).
- Resume review: poppler tools (`pdfinfo`, `pdftotext`, `pdftoppm`).
- Browser apply stage:
  - Chrome/Chromium with CDP enabled.
  - X display (typically Xvfb on Linux server).
  - Playwright Python package installed.
  - Simplify extension installed/authenticated in the Chrome profile used by the worker.

## Environment Variables

### Core
- `DATABASE_PATH`, `LOG_LEVEL`, `LOG_FILE`, `SQLITE_JOURNAL_MODE`

### Discovery / Gate
- `APIFY_API_TOKEN`
- `OPENAI_API_KEY` (required for decider)
- `AGENT_BATCH_SIZE`, `AGENT_BATCH_LIMIT`, `AGENT_POLL_INTERVAL_SECONDS`
- `AGENT_MAX_RETRIES`, `AGENT_RETRY_BACKOFF_SECONDS`, `AGENT_RETRY_BACKOFF_MULTIPLIER`
- `AGENT_CLAIM_LEASE_SECONDS`
- `CANDIDATE_PROFILE_PATH`

### Tailor
- `TAILOR_POLL_INTERVAL_SECONDS`, `TAILOR_MAX_RETRIES`, `TAILOR_RETRY_BACKOFF_SECONDS`, `TAILOR_RETRY_BACKOFF_MULTIPLIER`, `TAILOR_CLAIM_LEASE_SECONDS`, `TAILOR_OUTPUT_DIR`, `TAILOR_RESUME_YAML_PATH`
- `PI_CODING_AGENT_COMMAND`, `PI_CODING_AGENT_COMMAND_ARGV`
- `RESUME_TAILOR_MODEL`

### Review
- `REVIEW_POLL_INTERVAL_SECONDS`, `REVIEW_MAX_RETRIES`, `REVIEW_RETRY_BACKOFF_SECONDS`, `REVIEW_RETRY_BACKOFF_MULTIPLIER`, `REVIEW_CLAIM_LEASE_SECONDS`, `REVIEW_OUTPUT_DIR`
- `REVIEW_BASE_RESUME_YAML_PATH`, `REVIEW_BASE_RESUME_TEX_PATH`, `REVIEW_BASE_RESUME_PDF_PATH`
- `RESUME_REVIEW_MODEL`

### Apply Worker
- `CHROME_CDP_URL` (default `http://localhost:9222`)
- `APPLY_POLL_INTERVAL_SECONDS`, `APPLY_MAX_RETRIES`, `APPLY_RETRY_BACKOFF_SECONDS`, `APPLY_RETRY_BACKOFF_MULTIPLIER`, `APPLY_CLAIM_LEASE_SECONDS`
- `APPLY_DRY_RUN` (default true)

### Alerts
- `NTFY_TOPIC`, `NTFY_SERVER`, `NTFY_TOKEN`, `NTFY_PRIORITY`

## Deployment Dependencies
- systemd units currently provided for discovery, gate, tailor, review, apply worker, and Chrome CDP.
- Apply worker unit requires Chrome service and writable paths for artifacts and X socket.

## Noted Config Drift
- `.env.example` currently documents gate/tailor/review variables but does not yet include the `APPLY_*` and `CHROME_CDP_URL` knobs used by `scripts/process_apply_jobs.py`.
