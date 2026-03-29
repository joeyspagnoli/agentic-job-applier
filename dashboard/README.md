# AutoApply Dashboard

React + TypeScript + Vite frontend for the Agentic Job Applier control plane.

## Purpose

The dashboard is fully wired to the FastAPI backend and provides:

- Pipeline KPIs and trend visualizations
- Jobs table with filters and expansion panels
- Human review queue with approve/dismiss actions
- Unified failures view with stage-specific retry
- Cost tracking (daily trend + stage spend)
- Settings panel (budget edit + resume/profile upload/download)

## Local Development

Install dependencies:

```bash
npm install
```

Run backend first (required for `/api` proxy targets):

```bash
cd ..
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Run dashboard dev server:

```bash
npm run dev
```

The Vite dev proxy forwards `/api/*` to `http://localhost:8000`.

## Validation Commands

```bash
npm run typecheck
npm run build
```

## Runtime Notes

- React Query is configured globally with 30s polling.
- `Sync now` in the top bar invalidates active queries.
- API contracts use `snake_case`; frontend adapters map DTOs for UI usage.

## Production Serving

Build static assets:

```bash
npm run build
```

Then serve through FastAPI (`api/main.py`), which mounts built assets and handles SPA fallback routing.
