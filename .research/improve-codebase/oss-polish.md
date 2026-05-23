# OSS Polish Plan

## 8 Specific Polish Items for Tonight

1. **Add badge row** to README top: License (MIT), Python (3.11+), CI status (after workflow lands), `code style: ruff`, `Docker: ready`, `PRs welcome`. Use shields.io.
2. **Add `.github/workflows/ci.yml`** — two jobs:
   - Python: `astral-sh/setup-uv@v7` + `uv sync` + `pytest` + `ruff`
   - Dashboard: `setup-node@v4` + `npm ci` + `npm run build` + `npm test`
   - Run on push to main + PRs.
3. **Add `.github/dependabot.yml`** — watch `pip` (root), `npm` (`/dashboard`), `docker` (root), `github-actions` (root); weekly; max 5 PRs.
4. **Add `.editorconfig`** at repo root: UTF-8, LF, final newline, 4-space Python / 2-space TS-YAML-JSON.
5. **Add `.github/ISSUE_TEMPLATE/`** — `bug_report.yml`, `feature_request.yml`, `config.yml` (link Discussions for questions).
6. **(Optional)** Capture demo GIF/screenshot of dashboard + embed near top of README. SKIP if no time — placeholder in README is fine.
7. **Update README "Why?" section** — 3-5 line hook explaining problem solved (auto-applies to filtered jobs, local-first, you stay in control).
8. **Tag `v0.1.0` and publish GitHub Release** + enable Discussions in repo settings. Skip if user wants to do this themselves.

## Skip / Stretch
- pre-commit hooks (nice-to-have, not table stakes for solo pet project)
- Architecture diagram (mermaid)
- Makefile/justfile

## Sources
Artifacts in `.codex-review-artifacts/kindly-web-search/` (6 JSON files)
