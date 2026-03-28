# Knowledge Base Index

Use this file as the primary context for assistants. It links to detailed specs with short summaries and guidance on where to look for specific answers.

## Snapshot
- Spec sync date: 2026-03-26
- Source commit: `5bc956cb6bb5eb6c58087a6d91660466276ca2ce`
- Prior commit: `9a9a21963754b07ec8d35ddc67c39cfdd8f9620b`

## How to Use
- Start here and jump into the relevant file by topic.
- For runtime flow and queue boundaries, read `architecture.md` then `workflows.md`.
- For DB fields and state transitions, read `data_models.md` and `interfaces.md`.
- For operational setup and prerequisites, read `dependencies.md` and `review_notes.md`.

## Table of Contents
| File | What it covers | When to read |
| --- | --- | --- |
| `architecture.md` | High-level producer/consumer design, queue tables, and all workers (gate, tailor, review, browser apply) | Understanding system shape and control flow |
| `components.md` | Module-by-module responsibilities with current line counts | Locating implementation by responsibility |
| `interfaces.md` | Fetcher contracts, DB manager methods (2188 lines), worker CLIs, deployment interfaces | Calling/extending code paths correctly |
| `data_models.md` | `JobPosting`, SQLite tables (`job_postings`, `crawl_history`, `daily_stats`, `tailor_runs`, `review_runs`, `apply_runs`, `apply_handoffs`), and agent I/O models | Schema questions and persistence mapping |
| `workflows.md` | End-to-end sequence diagrams and runbooks for discovery, gate, tailor, review, and apply loops | Operational understanding and troubleshooting |
| `dependencies.md` | Python/runtime/system dependencies, env vars, service assumptions | Host setup and production readiness |
| `codebase_info.md` | Repository orientation, key directories, entrypoints, and deployment assets | Fast onboarding |
| `review_notes.md` | Known gaps, risks, and unresolved autonomy issues | Planning hardening work |

## Quick Answers
- **Main pipeline stages?** `main.py` (discovery), `scripts/process_new_jobs.py` (gate), `scripts/process_qualified_jobs.py` (tailor), `scripts/process_reviewed_resumes.py` (review), `scripts/process_apply_jobs.py` (browser apply).
- **Queue boundaries?** `job_postings` (`NEW` -> `QUALIFIED/FILTERED`) and run tables (`tailor_runs`, `review_runs`, `apply_runs`) with claim-token leasing; `apply_handoffs` stores human-review checkpoints for `NEEDS_REVIEW` apply outcomes.
- **Does apply auto-submit now?** No. Current browser worker records diagnostics and returns `NEEDS_REVIEW`; submit action is intentionally not implemented yet.
- **Does status CLI show apply/tailor/review metrics?** Not currently. `scripts/status.py` mainly reports job/crawl/daily stats plus gate retry metrics.

## Source of Truth
If code and docs conflict, treat source code as authoritative and update these spec files accordingly.
