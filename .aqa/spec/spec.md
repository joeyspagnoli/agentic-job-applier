# Agentic Job Applier Specification

## Executive Summary

Agentic Job Applier is a staged job automation pipeline with an operational control plane.

- Pipeline: discovery + gate + tailor + review + apply.
- State: persisted in SQLite with explicit run tables and retry metadata.
- Control plane: FastAPI endpoints consumed by a React dashboard.
- Cost tracking: forward-only stage event telemetry and configurable monthly budget.

## System Scope

Primary goals:

1. Discover and normalize jobs from multiple sources.
2. Process jobs through increasingly expensive automation stages.
3. Keep all state and failures inspectable/retriable through a live dashboard.
4. Operate autonomously on a homeserver with minimal human intervention.

## Current Architecture

### Pipeline Runtime

- `main.py` populates `job_postings`.
- Worker scripts claim work atomically and write stage outcomes.
- Human review handoffs are persisted in `apply_handoffs`.

### Control Plane Runtime

- `api/main.py` serves `/api/*`, runs startup migrations, and serves built dashboard assets.
- `dashboard/` uses React Query and typed adapters for all page-level fetch/mutation flows.

## Data Progression

- `NEW` jobs enter from discovery.
- Gate transitions to `QUALIFIED` or `FILTERED`.
- Tailor/review/apply stage tables capture attempt outcomes.
- Apply stage may emit `PENDING_REVIEW` handoffs for manual resolution.
- Cost events are recorded per stage attempt to `cost_events`.

## Interface Contracts

- API responses are snake_case and deterministic.
- Error payload shape is normalized (`ok=false`, `code`, `message`, `details`).
- Dashboard adapts DTOs to rendering models without mutating backend contracts.

## Operational Model

Recommended Linux runtime uses systemd timer/services for discovery and workers, plus Chrome CDP service for apply automation.

## Known Constraints

- Apply flow remains review-first for many outcomes.
- Some frontend hardening items are intentionally deferred (CSV export and expanded filters are documented under `docs/handoff/deferred_features.md`).
