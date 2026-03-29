# Agentic Job Applier Spec Index

This index is the primary entrypoint for assistants and maintainers.

## Repository At A Glance

The system now has two runtime surfaces:

1. Pipeline runtime (discovery + staged workers) backed by SQLite.
2. Product surface runtime (FastAPI + React dashboard) for live operations, review actions, retries, cost analytics, and settings file management.

Core lifecycle:
- Discovery writes `job_postings`.
- Gate worker transitions `NEW -> QUALIFIED/FILTERED`.
- Tailor worker writes `tailor_runs`.
- Review worker writes `review_runs`.
- Apply worker writes `apply_runs` and human-review `apply_handoffs`.
- API/dashboard consume and mutate this state via `/api/*`.

## Documentation Map

| File | Purpose |
|---|---|
| `.aqa/spec/spec.md` | End-to-end narrative of current system behavior. |
| `.aqa/spec/codebase_info.md` | Repository inventory, stack, and directory map. |
| `.aqa/spec/architecture.md` | Runtime boundaries and deployment topology. |
| `.aqa/spec/components.md` | Major subsystem responsibilities. |
| `.aqa/spec/interfaces.md` | External/internal interfaces, including HTTP API contracts. |
| `.aqa/spec/data_models.md` | Core entities and SQLite tables (including cost/budget tables). |
| `.aqa/spec/workflows.md` | Stage workflows and control-plane operations. |
| `.aqa/spec/dependencies.md` | Dependency and binary requirements across backend/frontend/workers. |
| `.aqa/spec/review_notes.md` | Known gaps and follow-up recommendations. |
| `.aqa/spec/checklist.md` | Spec-generation process checklist. |

## Query Routing Guide

- Pipeline execution semantics: `workflows.md` + `data_models.md`
- Dashboard/API behavior: `interfaces.md` + `components.md`
- Deployment/runtime setup: `architecture.md` + `dependencies.md`
- Known caveats: `review_notes.md`

## Source-Of-Truth Rule

If docs and implementation diverge, treat current source code as authoritative and update docs to match.
