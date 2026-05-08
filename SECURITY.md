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
