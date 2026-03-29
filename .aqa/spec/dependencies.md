# Dependencies

## Python Dependencies (Runtime)

Key runtime packages declared in `pyproject.toml` include:

- `aiosqlite`
- `httpx`
- `apify-client`
- `python-jobspy`
- `google-adk`
- `litellm`
- `pydantic`
- `python-dotenv`
- `pyyaml`
- `playwright`
- `fastapi`
- `uvicorn`

## Frontend Dependencies (Dashboard)

Key dashboard packages include:

- `react`, `react-dom`
- `@tanstack/react-query`
- `recharts`
- `vite` + TypeScript toolchain

## Dependency-To-Subsystem Mapping

- Fetchers: `httpx`, `apify-client`, `python-jobspy`
- Persistence: `aiosqlite`
- Agent logic: `google-adk`, `litellm`, provider API keys
- Apply automation: `playwright` + Chrome CDP
- API runtime: `fastapi`, `uvicorn`, `python-multipart`
- Dashboard runtime: React + React Query + charting stack

## External Binaries/Services

- `pi` command (tailor/review)
- `latexmk` and PDF tools (tailor/review)
- Chrome CDP target (apply worker)
- Optional `ntfy` endpoint for notifications

## Configuration Dependencies

Operational settings come from `.env`, including:

- Stage polling/retry knobs
- Provider keys
- Optional cost-rate keys (`COST_RATE_*_USD`)
- Database path and logging config
