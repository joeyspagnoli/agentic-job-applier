# Knowledge Base Index

Use this file as the primary context for assistants. It links to detailed specs with short summaries and guidance on where to look for specific answers.

## How to Use
- Start here. Follow the table below to jump to the right document.
- For architecture/flow questions, read `architecture.md` and `workflows.md`.
- For field-level or storage questions, use `data_models.md` and `dependencies.md`.
- For operational tasks or scripts, see `workflows.md` and `interfaces.md`.
- For open issues or risks, see `review_notes.md`.

## Table of Contents
| File | What it covers | When to read |
| --- | --- | --- |
| `architecture.md` | System overview (orchestrator, fetchers, DB, agent, deployment) with Mermaid diagram | Understanding high-level design or data/control flow |
| `components.md` | Responsibilities of each major module (orchestrator, DB, fetchers, dedup, agent, scripts, config, deployment) | Locating code by responsibility |
| `interfaces.md` | Public interfaces: fetcher contracts, DB manager methods, CLI entrypoints, config inputs, deployment units | Implementing/extending integrations or calling scripts |
| `data_models.md` | Pydantic JobPosting schema, SQLite tables, and agent I/O schema | Schema/field questions and persistence mapping |
| `workflows.md` | End-to-end discovery cycle, agent decision loop, utility CLIs, deployment flow (Mermaid sequences) | How processes run in order; operational runbooks |
| `dependencies.md` | Python deps, external services (Greenhouse, Apify, JobSpy), env vars, runtime/platform, systemd details | Environment setup, required keys, platform assumptions |
| `codebase_info.md` | Languages, directories, entrypoints, configs, deployment locations | Quick orientation to repo layout and tools |
| `review_notes.md` | Gaps/risks (systemd placeholders, token needs, salary intervals) and follow-ups | Known issues and remediation checklist |

## Quick Answers
- **Where is the main pipeline?** Discovery producer is `main.py`; gate consumer is `scripts/process_new_jobs.py`; queue boundary is SQLite `job_postings` NEW rows [architecture.md](architecture.md).
- **How are jobs stored?** SQLite schema (job_postings/crawl_history/daily_stats) in `schema.sql`; JobPosting maps via `to_db_dict()` [data_models.md](data_models.md).
- **How to run it autonomously?** Enable both `job-discovery.timer` and `job-agent-worker.service`; see deployment workflow docs [workflows.md](workflows.md).
- **How to decide apply/skip?** Configure `OPENAI_API_KEY` and run `scripts/process_new_jobs.py`; retries and terminal alerts are env-configurable.
- **What configs matter?** `companies.yaml`, `search_criteria.yaml`, `candidate_profile.yaml`, and `.env` runtime/retry/alert vars [dependencies.md](dependencies.md).

## Source of Truth
Citations in each document point to code paths and line numbers. If conflicting, prefer source code over narrative and update `review_notes.md` with discrepancies.
