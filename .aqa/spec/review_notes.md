# Review Notes

## Gaps / Risks
- **OpenAI credential required**: the root decider remains wired to a fixed OpenAI model; worker sends startup alert but cannot process without valid model credentials.
- **Deployment placeholders**: systemd unit templates still contain placeholder user/path values and must be edited before enablement.
- **Apify token required**: Workday fetching is skipped without `APIFY_API_TOKEN`; ensure env is set in deployment [src/fetchers/apify_fetcher.py:21-65](src/fetchers/apify_fetcher.py:21-65) [main.py:59-78](main.py:59-78).
- **Retry tuning risk**: Backoff and retry limits are env-controlled; poor settings can delay recovery or generate alert noise.
- **SQLite runtime variance**: runtime SQLite version should be monitored when using WAL mode; deployments on older sqlite builds should follow preflight guidance.
- **JobSpy salary interval mapping**: `_normalize_salary` normalizes common mixed-case and `per <period>` labels, but truly unexpected intervals still fall back to annual and may mis-scale [src/fetchers/jobspy_fetcher.py:153-205](src/fetchers/jobspy_fetcher.py:153-205).
- **Salary source label mismatch**: Model restricts `salary_source` to `direct|parsed|not_listed` while schema comments mention `parsed_from_description`; align labels or update docs to avoid downstream confusion [src/models/job_posting.py:27-101](src/models/job_posting.py:27-101) [src/database/schema.sql:21-25](src/database/schema.sql:21-25).

## Completeness Follow-ups
- Add explicit operator tooling for requeueing terminal failures (currently SQL/manual API usage).
- Add integration tests that include real connector mocks per source family in one pipeline run.
- Consider richer alert payloads (company/title/url) with rate limiting.
- Expand salary normalization and logging for unmatched intervals to aid debugging.

## Data / Config Checks
- Verify `config/companies.yaml` entries are current and trimmed to desired targets for rate limits.
- Keep `config/candidate_profile.yaml` aligned with the active user profile and internship preferences.
