# Bug Report

## Run Metadata

- Run ID: codebase-only-03122026-004912
- Repo Root: /Users/josephspagnoli/Projects/agentic-job-applier
- Run Timestamp (UTC): 2026-03-12T04:53:00Z
- Base URL: N/A
- Ground Truth Path: N/A
- Web Findings Path: N/A

## Severity Criteria

| Severity | Definition                                                                       |
| -------- | -------------------------------------------------------------------------------- |
| Critical | Exploitable in production. Data loss, corruption, or unauthorized access likely. |
| High     | Significant defect in a core flow. Realistic exploitation or failure.            |
| Medium   | Degrades quality, performance, or security posture. Not immediately exploitable. |
| Low      | Code quality or maintainability issue. No direct user or security impact.        |

## Issue Summary

- Total Issues: 6
- Critical: 0
- High: 2
- Medium: 4
- Low: 0

## Executive Summary

The codebase cleanly implements the job discovery pipeline across Greenhouse, Workday (Apify), and JobSpy with structured models and SQLite persistence, but several operational gaps block reliable use. The ADK agent pathway is intentionally stubbed and causes the Phase 2 processor to skip all jobs, meaning apply/skip automation cannot function until a model is wired. Deployment automation is also not ready: the systemd unit ships with placeholder user/paths and no environment loading, so scheduled runs will fail without manual edits.

Operational tooling shows configuration drift: both the status dashboard and query CLI hardcode `data/jobs.db` instead of honoring the documented `DATABASE_PATH`, so monitoring/query commands will misreport or fail in non-default deployments. Data quality is at risk in JobSpy salary normalization because interval values are treated case-sensitively, leading to incorrect annualization for common variants like "Hourly" or "Per Year." Finally, the project declares MIT in the README but ships no LICENSE file or `license` metadata, leaving the distribution legally ambiguous.

## Findings

### Critical

_No Critical findings._

### High

#### [H-001] Agent pipeline disabled by stubbed model

- **Domain:** Architecture
- **File:** `src/agents/root_apply_decider.py`, `scripts/process_new_jobs.py`
- **Line(s):** 51-68; 156-165
- **Description:** `get_decider_model()` raises a RuntimeError stub; `process_new_jobs.py` catches this and returns early, so the apply/skip processor never runs and no NEW jobs can be classified.
- **Evidence:** `root_apply_decider.get_decider_model()` explicitly raises "Decider model not configured" [src/agents/root_apply_decider.py:51-68]; `_process_once` logs the stub error and exits with 0 processed jobs [scripts/process_new_jobs.py:156-165].
- **Impact:** Phase 2 automation is non-functional; all NEW jobs remain unprocessed, blocking any apply/skip decisions.
- **Suggested Next Step:** Wire a real ADK model (env-driven) into `get_decider_model()` or pass an injected model to `build_root_agent`, and add a failing test to prevent silent skips when the model is missing.

#### [H-002] systemd service uses placeholders and no env/venv loading

- **Domain:** Configuration
- **File:** `deploy/job-discovery.service`
- **Line(s):** 7-10
- **Description:** Service unit ships with `User`, `WorkingDirectory`, `PATH`, and `ExecStart` placeholders and does not load the project `.env` or virtualenv.
- **Evidence:** Placeholder values at lines 7-10 (`YOUR_USERNAME`, `/path/to/...`, bare `python main.py`) [deploy/job-discovery.service:7-10].
- **Impact:** Timer-based runs will fail on deployment hosts until the unit is edited; may run with system Python and missing secrets/log paths.
- **Suggested Next Step:** Populate real user and paths, point `ExecStart` to the project venv (or `uv run`), and load an EnvironmentFile for `.env` before enabling the timer.

### Medium

#### [M-001] Status dashboard ignores DATABASE_PATH override

- **Domain:** Configuration
- **File:** `scripts/status.py`
- **Line(s):** 16-25
- **Description:** The status CLI hardcodes `data/jobs.db` and never reads `DATABASE_PATH`, conflicting with README guidance to override the DB path.
- **Evidence:** `db_path = Path(__file__).parent.parent / "data" / "jobs.db"` with no env lookup [scripts/status.py:16-25]; README documents `DATABASE_PATH` as configurable.
- **Impact:** On deployments using a non-default database location, status checks fail with "Database not found" or report the wrong database.
- **Suggested Next Step:** Resolve DB path via `os.getenv("DATABASE_PATH", "data/jobs.db")` (and optionally load `.env`) to mirror the main pipeline configuration.

#### [M-002] Query CLI hardcodes database path

- **Domain:** Configuration
- **File:** `scripts/query_jobs.py`
- **Line(s):** 21-37
- **Description:** Query script connects to `data/jobs.db` without checking `DATABASE_PATH`, so it cannot query custom database locations.
- **Evidence:** Hardcoded `db_path = ... / "data" / "jobs.db"` and existence check [scripts/query_jobs.py:21-37]; `.env.example` exposes `DATABASE_PATH` for configurability.
- **Impact:** Users with non-default DB paths get "Database not found" and cannot query their live data.
- **Suggested Next Step:** Read `DATABASE_PATH` (loading `.env` as needed) with a sane default, aligning with the orchestrator's configuration.

#### [M-003] JobSpy salary normalization is case-sensitive

- **Domain:** Code Quality
- **File:** `src/fetchers/jobspy_fetcher.py`
- **Line(s):** 143-199
- **Description:** `_normalize_salary` looks up interval multipliers using the raw `interval` string without normalizing case/whitespace, so values like "Hourly" or "Per Year" miss the intended multiplier and fall back to 1.
- **Evidence:** `interval` is converted to `str` but not lowercased before `multipliers.get(interval if interval else "", 1)` [src/fetchers/jobspy_fetcher.py:143-199].
- **Impact:** Annualized salary fields can be wrong or zero for common interval variants, degrading data quality and downstream filtering.
- **Suggested Next Step:** Normalize `interval` (e.g., `interval_normalized = interval.lower().strip()` and handle tokens like "per year") before lookup; add tests covering mixed-case intervals.

#### [M-004] License declaration missing

- **Domain:** Licensing
- **File:** `pyproject.toml`, (missing `LICENSE` file)
- **Line(s):** 1-22
- **Description:** No `license` field in `pyproject.toml` and no `LICENSE` file in the repo, despite README referencing MIT.
- **Evidence:** `pyproject.toml` lacks a `license` entry [pyproject.toml:1-22]; `ls` shows no LICENSE file.
- **Impact:** Legal terms for distribution/use are ambiguous, which can block adoption or packaging.
- **Suggested Next Step:** Add a `LICENSE` file (MIT as stated) and set the `license` field in `pyproject.toml` to match.

## Analysis Coverage

| Analysis Domain    | Status      | Files Reviewed | Notes |
| ------------------ | ----------- | -------------- | ----- |
| Code Quality       | ✅ Complete | 7 | Reviewed fetchers, agent stub, CLI scripts for data correctness and structure. |
| Security           | ✅ Complete | 5 | Checked for secrets in tracked files, env handling, and dangerous patterns; none found. |
| Performance        | ✅ Complete | 4 | Assessed fetcher loops and salary normalization; no major perf bugs beyond data accuracy noted. |
| Error Handling     | ✅ Complete | 5 | Reviewed orchestrator, agent processor, and CLIs for error paths and logging. |
| Architecture       | ✅ Complete | 4 | Mapped orchestrator, DB manager, agent pipeline, dedup. |
| Dependencies       | ✅ Complete | 2 | pyproject dependencies reviewed; uv.lock noted but not analyzed due to size. |
| License Compliance | ✅ Complete | 2 | Verified absence of LICENSE and metadata. |
| Configuration      | ✅ Complete | 6 | Examined env usage, systemd unit, CLIs' DB path handling. |
| Documentation      | ✅ Complete | 3 | README/QUICKSTART present; no blocking issues beyond license mismatch. |
