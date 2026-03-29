#!/usr/bin/env bash
set -euo pipefail

# Purpose: Provide a forward-only execution checklist for deferred dashboard wiring features.
# Usage: bash scripts/handoff_deferred_features.sh

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf '\nDeferred Feature Handoff Script\n'
printf 'Repository: %s\n\n' "$REPO_ROOT"

printf '1) Implement Human Review CSV export\n'
printf '   - File: dashboard/src/pages/HumanReviewPage.tsx\n'
printf '   - Command skeleton:\n'
printf '     rg -n "Export CSV" dashboard/src/pages/HumanReviewPage.tsx\n'
printf '     # TODO: Add client-side CSV builder for current filtered queue rows\n\n'

printf '2) Implement advanced dropdown filters (deferred by decision)\n'
printf '   - Files:\n'
printf '     dashboard/src/pages/JobsPage.tsx\n'
printf '     dashboard/src/pages/FailuresPage.tsx\n'
printf '     dashboard/src/pages/HumanReviewPage.tsx\n'
printf '   - Command skeleton:\n'
printf '     rg -n "All Statuses|All Sources|All Stages" dashboard/src/pages/*.tsx\n'
printf '     # TODO: Add backend query params + UI controls beyond interactive controls first scope\n\n'

printf '3) Add API-level integration tests for dashboard contracts\n'
printf '   - Files to add:\n'
printf '     tests/api/test_dashboard_routes.py\n'
printf '     tests/api/test_human_review_routes.py\n'
printf '     tests/api/test_cost_routes.py\n'
printf '   - Command skeleton:\n'
printf '     mkdir -p tests/api\n'
printf '     uv run pytest -q tests/api\n\n'

printf '4) Add frontend integration tests for page-level query/mutation flows\n'
printf '   - Files to add:\n'
printf '     dashboard/src/pages/__tests__/HumanReviewPage.test.tsx\n'
printf '     dashboard/src/pages/__tests__/CostTrackingPage.test.tsx\n'
printf '   - Command skeleton:\n'
printf '     npm --prefix dashboard run test\n\n'

printf '5) Optional perf pass for large bundle warning\n'
printf '   - Command skeleton:\n'
printf '     npm --prefix dashboard run build\n'
printf '     # TODO: Introduce route-level code splitting if needed\n\n'

printf '6) Full local run verification\n'
printf '   - Terminal A: uv run uvicorn api.main:app --host 127.0.0.1 --port 8000\n'
printf '   - Terminal B: npm --prefix dashboard run dev\n'
printf '   - Smoke checks:\n'
printf '     curl -sS http://127.0.0.1:8000/api/health\n'
printf '     curl -sS http://127.0.0.1:8000/api/dashboard/stats\n\n'

printf 'Done. See docs/handoff/deferred_features.md for scope detail.\n'
