# Codebase Information

## Repository Identity

`agentic-job-applier` is a multi-stage automation pipeline with an operations UI.

- Backend/runtime language: Python 3.11+
- Frontend/runtime language: TypeScript/React
- Storage: SQLite
- Package manager: `uv` (Python), `npm` (dashboard)

## Current Technology Stack

### Backend and Workers

- `aiosqlite` for async SQLite access
- `pydantic` and `pyyaml` for data contracts/config
- `google-adk` + LiteLLM/OpenAI for gate decision runtime
- Playwright for apply automation
- FastAPI + Uvicorn for API/runtime serving

### Frontend

- React + TypeScript + Vite
- React Query for polling/caching/mutations
- Recharts for dashboard visualizations

## High-Level Filesystem Map

```text
agentic-job-applier/
├── api/                 # FastAPI app + SPA/static serving
├── dashboard/           # React UI
├── scripts/             # Worker entrypoints and operational tooling
├── src/
│   ├── agents/          # Gate/tailor/review/apply runtimes
│   ├── database/        # DB manager and schema
│   ├── fetchers/        # Discovery adapters
│   ├── models/          # Canonical job model
│   └── utils/           # Shared helpers (dedup, logging, cost tracking, paths)
├── deploy/              # Systemd units and deployment docs
├── config/              # YAML configs and resume/profile files
├── tests/               # Integration/unit coverage
└── main.py              # Discovery orchestrator
```

## Architectural Style Snapshot

- Queue-backed staged workers (claims/retries via SQLite transactions)
- Forward-only run/event logging for observability (`*_runs`, `cost_events`)
- FastAPI control plane exposing deterministic JSON payloads
- Frontend adapter layer consuming snake_case API contracts
