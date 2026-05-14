# Contributing to Agentic Job Applier

Thanks for your interest in contributing. This project is a self-hosted, AI-driven job
discovery and application pipeline with a FastAPI backend and a React dashboard. We
welcome bug reports, fixes, new fetchers, dashboard improvements, and documentation
updates from contributors of any experience level. This guide explains how to get a
working dev environment, run the checks CI runs, and submit changes that have a good
chance of being merged.

## Code of Conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you
agree to uphold it.

## Setting Up a Development Environment

### Prerequisites

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/) for Python dependency management
- Node.js 20 or newer (for the dashboard)
- Optional: `latexmk` and the `pi` CLI for the resume tailor / review pipelines
- Optional: Chrome + Playwright for the apply worker

### Option 1: Local Setup

```bash
git clone https://github.com/joeyspagnoli/agentic-job-applier.git
cd agentic-job-applier
uv sync
npm --prefix dashboard install
cp .env.example .env
```

Edit `.env` to fill in any API keys you need for the area you are working on. Most
contributions to backend logic, fetchers, or the dashboard do not require live API keys
because the test suite is network-free by default.

Sanity check:

```bash
uv run python -c "import src; print('ok')"
npm --prefix dashboard run typecheck
```

### Option 2: Docker

Docker is the recommended way to run the full stack on a server, and it also works for
local development if you prefer container isolation. See the Docker section of the
[README](README.md) for image tiers and Compose profiles. The short version:

```bash
cp .env.docker.example .env
docker compose up -d           # core: api, discovery, gate
docker compose --profile tailor up -d   # add tailor + review
docker compose --profile full up -d     # add apply worker
```

The dashboard is served at `http://localhost:8000` once `api` is healthy.

## Running Tests and Checks

CI runs the same commands listed below. Please run them locally before opening a PR.

### Backend (Python)

```bash
# Deterministic test suite (network-free, this is what CI runs)
uv run pytest -q

# Strict type checking across api/, src/, scripts/, tests/
uv run mypy

# Opt-in live model end-to-end tests (require OPENAI_API_KEY, not run in CI)
uv run pytest -q --run-live-agent-e2e -m live_agent_e2e
```

Mypy is configured in strict mode (`pyproject.toml`). New code is expected to pass
strict checks without `# type: ignore` unless there is a clear third-party reason.

### Frontend (Dashboard)

```bash
npm --prefix dashboard run lint        # ESLint, --max-warnings 0
npm --prefix dashboard run typecheck   # tsc --noEmit
npm --prefix dashboard run test        # Vitest with coverage
npm --prefix dashboard run format:check  # Prettier
npm --prefix dashboard run build       # production build
```

If you change formatting, run `npm --prefix dashboard run format` to apply Prettier
across the dashboard tree.

### Pre-push hook (recommended)

The repo ships a `pre-push` hook in `.githooks/` that runs every CI check
locally before the push leaves your machine. Activate it once per clone:

```bash
git config core.hooksPath .githooks
```

After that, `git push` automatically runs backend pytest + mypy and dashboard
lint + typecheck + vitest. Use `git push --no-verify` to bypass in an
emergency.

## Coding Standards

These standards are enforced by code review and, where possible, by mypy / ESLint /
test gates. They reflect conventions already in use across the codebase.

### Python

- Type-annotate every function signature and class attribute. The repo runs `mypy
  --strict` over `api/`, `src/`, `scripts/`, and `tests/`.
- Every public callable starts with a plain-English sentence describing what it does,
  followed by `Purpose:`, `Args:`, and `Output:` sections in the docstring. The only
  exception is the `if __name__ == "__main__":` guard. See `AGENTS.md` for the full
  documentation standard.
- Inline comments should explain normalization rules, persistence choices, guardrails,
  and non-obvious control flow. Prefer comments on logical blocks over per-line.
  Avoid comments that merely restate syntax or repeat a function name.
- Pin every new Python dependency with `==` in `pyproject.toml`. Do not introduce `>=`
  or other range specifiers.
- No commented-out code. Delete it; git remembers.
- Keep modules under roughly 300 lines where reasonable. If a file is growing past
  that, look for a split that mirrors an existing subsystem boundary
  (`fetchers/`, `agents/`, `database/`, `utils/`, ...).
- Replace magic numbers and repeated literals with named constants at module scope.
- Prefer `loguru` for logging (already a project dependency). Use `pydantic` models
  for structured data crossing module boundaries.

### TypeScript / React (Dashboard)

- TypeScript strict mode is on. ESLint runs with `--max-warnings 0`, so warnings fail
  the build.
- Follow the existing component structure under `dashboard/src/components/`,
  `dashboard/src/pages/`, and `dashboard/src/hooks/`. Co-locate component tests with
  the component when adding coverage.
- Use React Query for any new server state. Avoid ad-hoc `useEffect` + `fetch`.
- Prefer Tailwind utility classes consistent with the existing dashboard styling.

### Tests

- Add or update tests for any behavior change. The deterministic suite must remain
  network-free.
- Match the style of the existing tests in `tests/` (function-style pytest, fixtures
  in `tests/conftest.py` and `tests/fixtures/`). Property-based tests using
  `hypothesis` are encouraged for fetchers and parsers.
- Frontend tests use Vitest plus Testing Library. Co-located `*.test.ts(x)` files run
  via `npm --prefix dashboard run test`.

## Commit Message Format

This repo uses Conventional Commits. Recent history:

```
feat: expand company coverage to 284 portals across 15+ industries
test: harden TaleoFetcher coverage with property-based and integration tests
fix: persist partial insert counts when crawl insert loop raises
chore: anonymize resume template and refresh coverage report
docs(simplify-loop): final SUMMARY + 6/6 PASS confirmation
```

Use one of: `feat`, `fix`, `test`, `refactor`, `chore`, `docs`, `perf`, `build`,
`ci`. An optional scope in parentheses (for example `feat(apply-worker): ...`) is
welcome when a change is concentrated in one subsystem. Keep the subject under 72
characters and write it in the imperative mood. Add a body if the rationale is not
obvious from the subject.

## Branch and Pull Request Flow

1. Fork the repository on GitHub.
2. Create a topic branch off `main`: `git checkout -b feat/short-description`.
3. Make your changes in small, focused commits.
4. Run the full local check set:
   ```bash
   uv run pytest -q
   uv run mypy
   npm --prefix dashboard run lint
   npm --prefix dashboard run typecheck
   npm --prefix dashboard run test
   ```
5. Push your branch and open a PR against `main`.
6. CI must pass before review. Address review feedback with additional commits on the
   branch (avoid force-pushing during review unless asked).

A good PR description includes: a short summary of the change, why it is needed, any
behavior or schema changes, and a brief test plan.

## Reporting Issues

We accept bug reports, feature requests, and questions. When the
`.github/ISSUE_TEMPLATE/` directory is published, please use the matching template.
Until then, a useful issue includes:

- What you ran (commands, environment, OS, Python and Node versions).
- What you expected versus what happened.
- A minimal reproduction. For fetcher and parser bugs, the smallest input that
  reproduces the failure is ideal.
- Relevant logs (`logs/`) or stack traces, with secrets redacted.

## Reporting Security Issues

Please do **not** file public GitHub issues for security vulnerabilities. Follow the
disclosure process in [SECURITY.md](SECURITY.md).

## License

This project is released under the [MIT License](LICENSE). By contributing, you agree
that your contributions will be licensed under the same MIT License.
