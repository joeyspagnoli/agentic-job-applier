# Worker Findings

- Worker: root-2
- Completed: 2026-03-12T04:43:25.048Z
- Task: Explore key repo files batch root-2

## Summary
Reviewed the project documentation and implementation notes to understand the Phase 1 Job Discovery scope, including multi-source fetching, SQLite persistence, status dashboarding, and readiness guides (`README.md:1-80`; `QUICKSTART.md:1-70`; `IMPLEMENTATION_COMPLETE.md:5-140`; `scripts/status.py:16-124`). I also examined the fetcher implementations and ADK agent wiring to see how job data is normalized and how the agent workflow is gated (`src/fetchers/*.py`; `src/agents/root_apply_decider.py`), ensuring the batch work is aligned across configuration (`config/companies.yaml`) and the agent runner (`scripts/process_new_jobs.py`).

## Findings
- `scripts/process_new_jobs.py` calls `get_decider_model()` before processing jobs, but `src/agents/root_apply_decider.get_decider_model()` is a stub that always raises a `RuntimeError`, so without wiring a concrete ADK model the script logs a warning and exits without consuming any NEW jobs (`scripts/process_new_jobs.py:156-241`; `src/agents/root_apply_decider.py:51-100`).
- The `JobSpyFetcher` cleans pandas NaNs/dates, normalizes salary ranges to annual cents across intervals (yearly/monthly/weekly/daily/hourly), and serializes cleaned raw data before building `JobPosting` objects, protecting downstream storage from inconsistent board data (`src/fetchers/jobspy_fetcher.py:15-202`).
- `ApifyWorkdayFetcher` requires `APIFY_API_TOKEN` before creating an `ApifyClient`; if the token is missing, `fetch_jobs()` logs the skip and returns an empty list, and when the actor runs it executes synchronously in an executor and reads from the default dataset (`src/fetchers/apify_fetcher.py:33-127`).

## Evidence
1. `scripts/process_new_jobs.py:156-241` shows the script aborts processing when `get_decider_model()` raises, and `src/agents/root_apply_decider.py:51-100` confirms `get_decider_model()` is a placeholder that raises `RuntimeError` until a real model is injected.
2. `src/fetchers/jobspy_fetcher.py:15-202` documents the sanitization helpers, salary normalization multipliers, and the creation of `JobPosting` instances with cleaned fields and raw data.
3. `src/fetchers/apify_fetcher.py:33-127` documents the token requirement, executor usage for the synchronous actor run, and dataset fetching logic.

## Recommendations
1. Provide a concrete implementation of `get_decider_model()` (or allow injecting a configured model via CLI/service startup) so that `scripts/process_new_jobs.py` can actually process NEW jobs instead of repeatedly warning and returning zero processed jobs (`src/agents/root_apply_decider.py:51-100`).
2. Consider expanding `_normalize_salary` (e.g., case-insensitive matching, logging for unmatched intervals) so that salary conversion is robust against additional interval labels returned by JobSpy, preventing silent fallback to the default annual multiplier (`src/fetchers/jobspy_fetcher.py:178-200`).
3. Ensure users are reminded to set `APIFY_API_TOKEN` before running the Workday fetcher (already noted in `README.md:24-52`) and optionally fail earlier or surface a clearer warning if the token is missing to avoid silently skipping Workday sources (`src/fetchers/apify_fetcher.py:46-89`; `README.md:24-52`).
