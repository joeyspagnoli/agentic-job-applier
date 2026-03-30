# Agentic Job Applier Spec Index

This index is the primary entrypoint for AI assistants and operators.

## How to use this spec (AI-first routing)

1. Start with this file to choose the smallest relevant doc.
2. Prefer topic docs (`architecture.md`, `interfaces.md`, `workflows.md`, etc.) as source of truth.
3. **Ignore `spec.md` and `spec.pdf` for most QA/implementation questions** unless you explicitly want a narrative walkthrough; they intentionally restate material already covered in the topic docs.
4. If docs and code differ, treat code as authoritative and update docs.

## Repository at a glance

The system has two tightly-coupled runtime surfaces:

- A staged pipeline (discovery → gate → tailor → review → apply) backed by SQLite run tables and claim/retry leases (`main.py:1039-1266`, `scripts/process_new_jobs.py:266-345`, `scripts/process_qualified_jobs.py:404-534`, `scripts/process_reviewed_resumes.py:493-694`, `scripts/process_apply_jobs.py:437-859`).
- A FastAPI + React control plane for live monitoring, human review, failures, cost analytics, and settings file management (`api/main.py:1479-2630`, `api/main.py:2938-3659`, `dashboard/src/main.tsx:1-15`, `dashboard/src/lib/query-client.ts:1-30`).

## Documentation map

| File | Purpose | When to open |
|---|---|---|
| `.aqa/spec/codebase_info.md` | Languages, stack, repo map, supported/unsupported surfaces | Repo orientation, tooling questions |
| `.aqa/spec/architecture.md` | Runtime boundaries, deployment topology, cross-surface interactions | System design and hosting model |
| `.aqa/spec/components.md` | Component ownership and responsibilities | “Where does X logic live?” |
| `.aqa/spec/interfaces.md` | API contracts, DTOs, retry identifiers, external integrations | Endpoint/contract/integration work |
| `.aqa/spec/data_models.md` | Core entities, SQLite schema, statuses, claim/retry fields | DB and state progression questions |
| `.aqa/spec/workflows.md` | End-to-end and stage-by-stage control flow | Operational behavior and sequencing |
| `.aqa/spec/dependencies.md` | Python/frontend dependencies and external binaries/services | Environment/build/runtime setup |
| `.aqa/spec/review_notes.md` | Gaps, inconsistencies, deferred items, follow-ups | Risk review and QA planning |
| `.aqa/spec/checklist.md` | Run checklist and completion state | Audit trail for spec generation |
| `.aqa/spec/spec.md` | Narrative synthesis (non-canonical duplicate) | Optional executive narrative |

## Quick query routing

- “How does the pipeline move a job through stages?” → `workflows.md` + `data_models.md`
- “What does `/api/...` return and what can fail?” → `interfaces.md`
- “Where are settings and budget behaviors implemented?” → `components.md` + `interfaces.md`
- “What infra/tooling is required to run this?” → `dependencies.md` + `architecture.md`
- “What is risky or still inconsistent?” → `review_notes.md`

## Source-of-truth rule

When documentation and implementation conflict, trust the implementation first and refresh the docs afterward (`AGENTS.md:28-31`).
