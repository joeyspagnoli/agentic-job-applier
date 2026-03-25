# Codebase Info

## Overview
- Name: agentic-job-applier
- Primary language: Python 3.11+ (`.python-version` pins 3.11; `pyproject.toml` requires >=3.11)
- Purpose: Discover job postings from multiple sources (Greenhouse, Workday via Apify, JobSpy), deduplicate, store in SQLite, run an ADK gate to decide apply/skip, autonomously tailor qualified resumes, and run a post-tailor pi-mono review stage.

## Key Directories
- `src/`: core library
  - `agents/`: decision/tailor/review runtimes organized as per-agent packages:
    - `shared/` (centralized model construction helpers for LiteLLM/OpenAI)
    - `root_apply_decider/` (ADK apply/skip gate with runtime, prompts, schemas, agent builder)
    - `resume_tailor_pi/` (pi-mono YAML-canonical resume tailoring loop)
    - `resume_review_pi/` (pi-mono post-tailor review with report handshake)
  - `fetchers/`: source-specific fetchers (`greenhouse_fetcher.py`, `apify_fetcher.py`, `jobspy_fetcher.py`) plus `base_fetcher.py` and `errors.py` (FetchError)
  - `database/`: SQLite manager (1784 lines) and schema (148 lines)
  - `models/`: shared Pydantic models (JobPosting, 223 lines)
  - `utils/`: logging, deduplication, path resolution, ntfy notification helper
- `scripts/`: operational CLIs (query/find/test/decide/process/status), one-shot pipeline command, autonomous tailor/review workers, and resume tool scripts
- `config/`: `companies.yaml`, `search_criteria.yaml`, `candidate_profile.yaml`, `resume_content.yaml`, `resume_base.tex`, `resume_base.pdf`
- `deploy/`: producer timer/service, consumer worker services, optional alert hook, deployment README
- `tests/`: 33 test files covering unit, integration, e2e, concurrency, and robustness scenarios

## Tooling & Dependencies
- Runtime: Python >=3.11 (.python-version, pyproject)
- Key deps: aiosqlite, httpx, apify-client, python-jobspy, loguru, pydantic, pyyaml, python-dotenv, google-adk, litellm, aiohttp, authlib, cryptography, markdownify, protobuf, python-multipart, apscheduler
- Dev deps: pytest, pytest-asyncio, pip-audit
- Package manager: uv (noted in deploy docs)

## Config & Environment
- `.env.example` documents source credentials, gate model keys, retry/backoff settings, ntfy settings, profile override, and journal mode override.
- `config/companies.yaml` lists target Greenhouse boards, Workday URLs, and JobSpy board settings.
- `config/search_criteria.yaml` captures desired/undesired titles, locations, salary/experience bounds, keywords (used for title filtering and future filtering).
- `config/candidate_profile.yaml` provides gate profile, default board-search terms, and title include patterns.
- `config/resume_content.yaml` is the YAML-canonical resume source used by the pi-mono tailor workflow.
- `config/resume_base.tex` and `config/resume_base.pdf` are pre-compiled base resume reference artifacts for review comparisons.

## Data & Persistence
- SQLite schema for `job_postings` (with agent claim columns), `crawl_history`, `daily_stats`, `tailor_runs`, and `review_runs`; queue retry fields, claim tokens, and indexes are migrated automatically by `DatabaseManager`.

## Execution Entrypoints
- Discovery orchestrator: `main.py` (693 lines; async cycle over sources with title filtering, dedup, stats, logging)
- Agent processor: `scripts/process_new_jobs.py` (483 lines; pull NEW/retry-ready jobs via claim tokens, run ADK decider, persist success/retry/terminal failure state)
- Resume tailor processor: `scripts/run_resume_tailor.py` (284 lines; one job selector + one-page loop + optional branch isolation)
- Resume migration utility: `scripts/migrate_resume_tex_to_yaml.py` (500 lines; LaTeX to canonical YAML conversion)
- Resume tool surface: `scripts/resume_tailor_tools.py` (250 lines; DB/YAML/render/compile/page-count/backup/restore commands)
- Resume review processor: `scripts/process_reviewed_resumes.py` (824 lines; queue worker for post-tailor review verdicts)
- Resume review tool surface: `scripts/resume_review_tools.py` (347 lines; tailor tools + geometry/log/text/compare/report commands)
- One-shot pipeline: `scripts/run_pipeline_once.py` (143 lines; discovery then one gate batch)
- Database status: `scripts/status.py` (252 lines; terminal summary of database state across all pipeline stages)
- Utility CLIs: query (138 lines), find IDs (140 lines), test fetchers (112 lines), single-job decider (88 lines)

## Deployment
- systemd producer timer/service (`job-discovery.*`) + continuous gate worker (`job-agent-worker.service`) + continuous tailor worker (`job-tailor-worker.service`) + continuous review worker (`job-review-worker.service`) for autonomous runtime.
- Tailor/review workers require: pi-mono (or `PI_CODING_AGENT_COMMAND` / `PI_CODING_AGENT_COMMAND_ARGV`), texlive-full, latexmk; review also requires poppler tools (`pdfinfo`, `pdftotext`, `pdftoppm`).
