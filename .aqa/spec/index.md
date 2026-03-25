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
| `architecture.md` | System overview (orchestrator, fetchers, DB, agents, deployment) with Mermaid diagram; shared agent infrastructure; claim-based queue processing | Understanding high-level design or data/control flow |
| `components.md` | Responsibilities of each major module (orchestrator, DB, fetchers, dedup, agents, shared model helper, scripts, config, deployment, test suite) with line counts | Locating code by responsibility |
| `interfaces.md` | Public interfaces: fetcher contracts, DB manager methods (1784 lines), CLI entrypoints, config inputs, deployment units | Implementing/extending integrations or calling scripts |
| `data_models.md` | Pydantic JobPosting schema (223 lines), SQLite tables (148 lines schema), agent I/O schema, resume tailor/review models | Schema/field questions and persistence mapping |
| `workflows.md` | End-to-end discovery cycle (with title filtering), agent decision loop, tailor/review worker loops, utility CLIs, deployment flow (Mermaid sequences) | How processes run in order; operational runbooks |
| `dependencies.md` | Python deps (26 runtime + 3 dev), external services (Greenhouse, Apify, JobSpy, OpenAI/LiteLLM), env vars, runtime/platform, systemd details | Environment setup, required keys, platform assumptions |
| `codebase_info.md` | Languages, directories, entrypoints, configs, deployment locations, test suite (33 files) | Quick orientation to repo layout and tools |
| `review_notes.md` | Gaps/risks (claim lease, credential needs, salary intervals) and follow-ups | Known issues and remediation checklist |

## Quick Answers
- **Where is the main pipeline?** Discovery producer is `main.py` (693 lines); gate consumer is `scripts/process_new_jobs.py` (483 lines); queue boundary is SQLite `job_postings` NEW rows claimed via atomic tokens [architecture.md](architecture.md).
- **How are jobs stored?** SQLite schema (148 lines) includes `job_postings` (with claim columns), `crawl_history`, `daily_stats`, `tailor_runs`, and `review_runs`; JobPosting maps via `to_db_dict()` [data_models.md](data_models.md).
- **How to run it autonomously?** Enable `job-discovery.timer`, `job-agent-worker.service`, `job-tailor-worker.service`, and `job-review-worker.service`; see deployment workflow docs [workflows.md](workflows.md).
- **How to decide apply/skip?** Configure `OPENAI_API_KEY` and run `scripts/process_new_jobs.py`; uses `openai/gpt-5.1-codex-mini` via LiteLLM; retries and terminal alerts are env-configurable.
- **How to run resume tailoring?** Use `scripts/migrate_resume_tex_to_yaml.py` to bootstrap YAML, then either `scripts/run_resume_tailor.py` for one-shot or `scripts/process_qualified_jobs.py --loop` for autonomous daemon. Requires pi-mono and latexmk.
- **How to run resume review?** Use `scripts/process_reviewed_resumes.py --once` for one-shot or `--loop` for autonomous review queue processing. Requires pi-mono, latexmk, and poppler CLIs (`pdfinfo`, `pdftotext`, `pdftoppm`).
- **How to check pipeline status?** Run `scripts/status.py` for a terminal summary of job counts, crawl history, tailor/review statistics.
- **What configs matter?** `companies.yaml`, `search_criteria.yaml`, `candidate_profile.yaml`, `resume_content.yaml`, `resume_base.{tex,pdf}`, and `.env` runtime/retry/alert vars [dependencies.md](dependencies.md).

## Source of Truth
Citations in each document point to code paths and line numbers. If conflicting, prefer source code over narrative and update `review_notes.md` with discrepancies.
