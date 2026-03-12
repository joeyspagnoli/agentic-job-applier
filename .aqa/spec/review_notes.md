# Review Notes

## Gaps / Risks
- **Agent not wired**: `get_decider_model()` intentionally raises; `scripts/process_new_jobs.py` and `scripts/decide_job.py` will warn/exit until a concrete ADK model is injected. This blocks APPLY/SKIP automation until resolved [src/agents/root_apply_decider.py:51-74](src/agents/root_apply_decider.py:51-74) [scripts/process_new_jobs.py:156-164](scripts/process_new_jobs.py:156-164).
- **Deployment placeholders**: `deploy/job-discovery.service` uses placeholder User/WorkingDirectory/PATH/ExecStart; must be edited before enabling or the timer will fail [deploy/job-discovery.service:5-17](deploy/job-discovery.service:5-17).
- **Apify token required**: Workday fetching is skipped without `APIFY_API_TOKEN`; ensure env is set in deployment [src/fetchers/apify_fetcher.py:21-65](src/fetchers/apify_fetcher.py:21-65) [main.py:59-78](main.py:59-78).
- **Agent throughput controls**: Batch size/interval controlled by env; defaults may need tuning for production (AGENT_BATCH_SIZE/AGENT_POLL_INTERVAL_SECONDS) [scripts/process_new_jobs.py:130-200](scripts/process_new_jobs.py:130-200).
- **JobSpy salary interval mapping**: `_normalize_salary` supports yearly/monthly/weekly/daily/hourly; other intervals fall back to annual, which may mis-scale if JobSpy returns unexpected labels [src/fetchers/jobspy_fetcher.py:153-193](src/fetchers/jobspy_fetcher.py:153-193).
- **Salary source label mismatch**: Model restricts `salary_source` to `direct|parsed|not_listed` while schema comments mention `parsed_from_description`; align labels or update docs to avoid downstream confusion [src/models/job_posting.py:27-101](src/models/job_posting.py:27-101) [src/database/schema.sql:21-25](src/database/schema.sql:21-25).

## Completeness Follow-ups
- Provide a concrete ADK model wiring example (env-driven) and document how to configure it.
- Add automated tests for fetchers and dedup behavior beyond the provided smoke script.
- Consider explicit error surfacing when Workday token is missing rather than silent skip in cron contexts.
- Expand salary normalization and logging for unmatched intervals to aid debugging.

## Data / Config Checks
- Verify `config/companies.yaml` entries are current and trimmed to desired targets for rate limits.
- Ensure `CANDIDATE_PROFILE_PATH` is set in deployment for meaningful agent prompts [scripts/process_new_jobs.py:41-74](scripts/process_new_jobs.py:41-74).
