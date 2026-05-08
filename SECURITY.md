# Security Policy

## Supported Versions

This project is in active development. Only the latest commit on `main` is supported. Older releases or forks are not maintained.

## Reporting a Vulnerability

If you discover a security issue, please **do not** open a public GitHub issue. Instead, email the maintainer directly:

**jspagnoli1705@gmail.com**

Include:

- A description of the issue and its impact
- Steps to reproduce (proof-of-concept welcome, but not required)
- The affected file(s) or component(s)
- Your suggested fix, if you have one

You can expect an initial acknowledgement within 7 days. If the issue is confirmed, a fix will be prepared on a private branch and disclosed once a patch lands on `main`.

## Scope

In scope:

- The Python pipeline under `src/`, `api/`, and `scripts/`
- The React dashboard under `dashboard/`
- The Docker images defined in `Dockerfile` and `docker-compose.yml`
- Default configuration shipped in `.env.example` and `config/`

Out of scope:

- Vulnerabilities in third-party dependencies (please report those upstream)
- Issues that require physical access to the host running the pipeline
- Misconfigurations that result from a user deviating from `.env.example` defaults

## Disclosure

This is a self-hosted personal project, not a service. There is no production deployment to coordinate around, so disclosure happens as soon as a fix is merged to `main`.

## Auto-submit policy

Auto-submitting job applications on a user's behalf is **intentionally disabled in code**. The apply worker (`scripts/process_apply_jobs.py`) hardcodes `dry_run = True` at the call site; no env var, CLI flag, or config option flips it back on. The worker fills forms in a real browser and stops before clicking Submit, leaving an `apply_handoffs` row at `PENDING_REVIEW` for the operator to finalize.

This is a deliberate safety boundary, not a feature gap. Pull requests that re-enable auto-submit must, at a minimum:

1. Explain the threat model in the PR description (account bans, employer-side trust, accidental wrong-job submissions).
2. Add a positive opt-in stronger than a single env var (e.g., a per-job confirmation, a daily rate cap, an audit log signed by the operator).
3. Update this section with the new policy.

Until those bars are met, please review and submit applications yourself.
