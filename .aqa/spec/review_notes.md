# Review Notes

## Consistency check (enabled)

### Confirmed inconsistencies

1. **API error envelope is not universal.** Custom API errors are normalized, but framework validation errors can still return FastAPI-native 422 payloads (`api/main.py:472-496`, `api/main.py:1451-1476`, `api/main.py:1738-1742`).
2. **Failures retry ID parsing can raise 500 for malformed numeric IDs** (`TAILOR:abc`, etc.) due unguarded `int(...)` conversion (`api/main.py:2527-2629`).
3. **Settings response envelopes are not uniform** across profile/resume/filters/sources read/write routes (`api/main.py:3147-3296`, `api/main.py:3448-3473`, `api/main.py:3529-3622`).
4. **Schema-readiness checks are sentinel-based** and may miss partially migrated companion tables (tailor/apply/cost settings surfaces) (`src/database/db_manager.py:982-1060`, `src/database/db_manager.py:1793-1866`, `src/database/db_manager.py:2386-2428`).
5. **Claim-token enforcement is uneven**: apply-stage writes are claim-token guarded, while some gate/tailor completion paths are not (`tests/test_apply_worker_and_retry_semantics.py:778-1193`, `src/database/db_manager.py:1171-1255`, `src/database/db_manager.py:591-929`).
6. **Greenhouse salary parsing/label drift**: schema comment vs stored `salary_source` value and regex separator behavior diverge (`src/database/schema.sql:1-98`, `src/fetchers/greenhouse_fetcher.py:157-188`).

## Completeness check (enabled)

### Areas still under-documented or operationally risky

1. `/api` vs `/api/*` SPA fallback boundary behavior is subtle and easy to mis-assume (`api/main.py:3663-3685`).
2. Asset mounting/build ordering can require API restart when frontend artifacts appear after boot (`api/main.py:1445-1448`).
3. Failures/Human Review pages have stale or incomplete user-feedback copy in some error/retry paths (`dashboard/src/pages/FailuresPage.tsx:204-215`, `dashboard/src/pages/HumanReviewPage.tsx:189-205`).
4. LinkedIn and career-page watcher source semantics can be misread (delta URL watcher, conservative LinkedIn scrape behavior) (`src/fetchers/linkedin_fetcher.py:127-234`, `src/fetchers/career_page_watcher.py:117-194`).
5. Field scanner unresolved detection has edge cases (e.g., unchecked radio/checkbox groups) (`src/agents/apply_worker/field_scanner.py:20-264`).

## Carried-forward deferred/product notes

- Human Review CSV export remains deferred.
- Expanded jobs filtering UX beyond current controls remains deferred.
- Frontend bundle-size/code-splitting follow-up remains advisable.

(These remain consistent with prior review notes and current UI/test coverage discussions: `dashboard/src/pages/HumanReviewPage.tsx:98-309`, `dashboard/src/pages/JobsPage.tsx:163-186`, `dashboard/package.json:30-63`.)

## Scope warnings and mapping notes

- User-directed analysis scope excluded `.aqa/**`, `uv.lock`, `package-lock.json`, all `.svg`, `.yaml`, and `.md` files during worker planning; conclusions therefore prioritize runtime source/tests over documentation/config assets.
- No worker failures/timeouts occurred in this run.

## Byte-preservation note

- Core spec docs were broadly refreshed because drift affected API, dashboard, workers, fetchers, schema, and runtime tooling. No intentionally untouched core doc set remained for byte-identical verification in this pass.
