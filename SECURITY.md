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

Auto-submitting job applications is gated behind a strict binary condition evaluated in `src/agents/apply_worker/browser.py:_run_application_flow`. The gate passes only when **all three** of the following are true:

1. All required fields are filled.
2. No Tier-2 draft answers are pending review.
3. No Tier-3 questions have been deferred.

If the gate fails — for any reason — the apply writes an `apply_handoffs` row at `NEEDS_REVIEW` and stops. The operator finalizes those applications via the Human Review queue at `/human-review`.

The **`SAFE_MODE=true`** env var is a hard global kill switch: it disables auto-submit regardless of gate outcome. Forms are still filled; the result always lands `NEEDS_REVIEW`.

Scope: the finisher acts only on Greenhouse and Ashby forms. All other ATSes bypass the finisher and land `NEEDS_REVIEW` unconditionally.

**Do not write a wrapper that auto-submits forms outside of the gate.** If you do, you own the consequences — account bans, employer-side trust damage, and accidental wrong-job submissions are the operator's liability.

Pull requests that widen the gate or remove `SAFE_MODE` must, at a minimum:

1. Explain the updated threat model in the PR description.
2. Update this section with the new policy before the PR is merged.
