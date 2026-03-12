# Worker Findings

- Worker: root-2
- Completed: 2026-03-12T04:51:19.212Z
- Task: QA explore: fetchers, agent, scripts, README

## Summary
Reviewed the documentation (`README.md`, `QUICKSTART.md`), the job-processing and monitoring scripts (`scripts/process_new_jobs.py`, `scripts/status.py`), the fetchers (`src/fetchers/apify_fetcher.py`, `src/fetchers/greenhouse_fetcher.py`, `src/fetchers/jobspy_fetcher.py`), the integration tests (`tests/test_integration.py`), the agent implementation (`src/agents/root_apply_decider.py`, `src/agents/__init__.py`), and the companies config (`config/companies.yaml`). Key findings focus on the status dashboard’s hard-coded database path (which conflicts with the documented `DATABASE_PATH` override) and the JobSpy fetcher’s salary normalization being case-sensitive, which risks missing valid interval matches.

## Findings
- **Status dashboard ignores `DATABASE_PATH`**, so anyone who sets a custom database path (per README/Quickstart guidance) will still have `scripts/status.py` look for `data/jobs.db` and report “Database not found,” despite the actual database living elsewhere. (`README.md:44-75`, `scripts/status.py:16-127`)
- **JobSpy fetcher lower-bound salary normalization is case-sensitive**, meaning interval values like `"Hourly"` or `"Per Year"` that JobSpy may emit will not match the lowercase keys in `multipliers`, so salaries fall back to the 1× multiplier and annualized amounts can be wrong or missing. (`src/fetchers/jobspy_fetcher.py:144-202`)

## Evidence
- `README.md:44-75` documents `DATABASE_PATH` as the canonical SQLite path and directs users to override it via the environment. `scripts/status.py:16-127` unconditionally binds to `data/jobs.db` (lines 18–24), so it never honors that environment variable and therefore can’t report status for non-default installations.
- `src/fetchers/jobspy_fetcher.py:144-202` shows `_normalize_salary` building a `multipliers` dict with lowercase keys (`"yearly"`, `"monthly"`, etc.) but never lowercasing `interval` before the lookup (`multiplier = multipliers.get(interval if interval else "", 1)`), so any interval string that contains uppercase letters or additional text will miss the intended multiplier.

## Recommendations
- Update `scripts/status.py` so it reads `DATABASE_PATH` (with the same default as other components) instead of hard-coding `data/jobs.db`, mirroring the README/Quickstart guidance. This could be as simple as adding `db_path = Path(os.getenv("DATABASE_PATH", "data/jobs.db"))` near line 18 and letting the script use that path, ensuring status checks work for any configured database location.
- Normalize the `interval` value before looking it up in `multipliers` (e.g., `interval_normalized = interval.lower().strip()` or using a helper that extracts the keyword). This prevents the routine from falling back to the default multiplier whenever JobSpy emits values like “Hourly,” “Per Year,” or any capitalization variation, ensuring reported salaries stay consistent with source data.
