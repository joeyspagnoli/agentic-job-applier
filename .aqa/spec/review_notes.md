# Review Notes

## Gaps / Risks
- **OpenAI credential required**: the root decider remains wired to a fixed OpenAI model; worker sends startup alert but cannot process without valid model credentials.
- **Deployment placeholders**: systemd unit templates still contain placeholder user/path values and must be edited before enablement.
- **Apify token required**: Workday fetching is skipped without `APIFY_API_TOKEN`; ensure env is set in deployment [src/fetchers/apify_fetcher.py:21-65](src/fetchers/apify_fetcher.py:21-65) [main.py:59-78](main.py:59-78).
- **Retry tuning risk**: Backoff and retry limits are env-controlled; poor settings can delay recovery or generate alert noise.
- **SQLite runtime variance**: runtime SQLite version should be monitored when using WAL mode; deployments on older sqlite builds should follow preflight guidance.
- **JobSpy salary interval mapping**: `_normalize_salary` normalizes common mixed-case and `per <period>` labels, but truly unexpected intervals still fall back to annual and may mis-scale [src/fetchers/jobspy_fetcher.py:153-205](src/fetchers/jobspy_fetcher.py:153-205).
- **Salary source label mismatch**: Model restricts `salary_source` to `direct|parsed|not_listed` while schema comments mention `parsed_from_description`; align labels or update docs to avoid downstream confusion [src/models/job_posting.py:27-101](src/models/job_posting.py:27-101) [src/database/schema.sql:21-25](src/database/schema.sql:21-25).
- **pi-coding-agent command required**: resume tailor runner needs `--pi-coding-agent-command` or `PI_CODING_AGENT_COMMAND`; runs fail fast when missing.
- **LaTeX toolchain dependency**: resume tailoring requires local `latexmk`; page checks prefer `pdfinfo` and fall back to log parsing.
- **Branch mode assumptions**: `--create-git-branch` requires running inside a git worktree and may fail if branch naming/policy conflicts exist.

## Tailor Worker Risks (New)
- **YAML baseline race**: concurrent tailor workers share `config/resume_content.yaml` without file locking; current design assumes single-worker operation.
- **Path traversal**: `job_hash` is used to construct output paths without format validation (see bug report C-001).
- **Error recovery fragility**: exception handler calls `get_tailor_runs_for_job` without secondary error handling; DB failures in error path mask original errors.
- **Missing compound index**: `tailor_runs(job_hash, status)` compound index would improve claim query performance.
- **Config dir writable**: systemd `ReadWritePaths` includes config directory; should be restricted to data/logs only.

## Completeness Follow-ups
- Add explicit operator tooling for requeueing terminal failures (currently SQL/manual API usage; `reset_tailor_failure_state` exists but has no CLI wrapper).
- Add integration tests that include real connector mocks per source family in one pipeline run.
- Consider richer alert payloads (company/title/url) with rate limiting.
- Expand salary normalization and logging for unmatched intervals to aid debugging.
- Add an explicit wrapper or skill for non-interactive `pi-coding-agent` invocation so operators do not handcraft command strings.
- Add concurrent tailor claim tests under actual asyncio task contention.
- Update `deploy/README.md` to document `job-tailor-worker.service`.

## Data / Config Checks
- Verify `config/companies.yaml` entries are current and trimmed to desired targets for rate limits.
- Keep `config/candidate_profile.yaml` aligned with the active user profile and internship preferences.
