# Testing Conventions & Architecture

## Purpose

This repository's testing philosophy prioritizes **deterministic, secret-free default suites** with explicit opt-in gates for tests requiring live model API calls. The test suite validates core job-scraping, application, and resume-tailoring workflows with ~100 pytest tests covering backend logic, ~20 Vitest tests covering frontend components, and specialized property-based + mutation testing for critical invariants.

The testing strategy:
- **Default tests are deterministic**: No live API calls, no external dependencies, no secrets required
- **Live-LLM tests are opt-in**: Guarded by `@pytest.mark.live_agent_e2e` and `--run-live-agent-e2e` flag
- **Property-based tests stress invariants**: Using Hypothesis for normalize/substitute round-trips, patcher ordering, fetcher parsing
- **Mutation testing targets high-risk areas**: LinkedIn fetcher is mutmut-instrumented to catch logic drift
- **API contract tests ensure schema parity**: Between frontend, backend, and scrapers
- **Type checking is strict**: `mypy --strict` enforced project-wide on `api/`, `src/`, `scripts/`, `tests/`

What's **not** tested: Live third-party integrations (Greenhouse, Ashby, Workday) run without mocks in integration scenarios, but individual fetcher parsing is isolated. Dashboard e2e flows are component-based, not full-page e2e. Cost/budget flows are tested in isolation with fake LLM responses.

---

## Test Layout

**Directory structure** balances flat organization with semantic grouping:

```
tests/
├── conftest.py                              # Global markers, CLI flags, skip logic
├── test_*.py                                # 86 root-level pytest files (>27k LOC)
├── _fixtures/                               # Binary/HTML fixtures for tool testing
│   └── finisher/                            # Form HTML: ashby_basic_form.html, greenhouse_basic_form.html
├── fixtures/                                # Data files for parsing tests
│   ├── icims_*.html                         # Scraper test data
│   ├── taleo_wipo_*.{html,json}             # ATS parsing fixtures
│   ├── workday_imf_*.json                   # Workday schema examples
│   ├── manifests/                           # Resume bullet manifests (YAML)
│   ├── resumes/                             # .tex source files for tailor tests
│   │   ├── synthetic_minimal.tex            # Unit test canonical fixture
│   │   ├── external/                        # Real-world resumes
│   │   └── synthetic_failures/              # Edge-case LaTeX structures
├── helpers/                                 # Factory functions and test doubles
│   ├── pipeline_factories.py                # make_tailor_result(), make_reviewer_result()
│   └── fake_finisher_page.py                # FakeFinisherPage / FakeLocator mocks
├── agents/resume_tailor/                    # Agent-specific tests
│   └── test_*.py                            # Patcher, manifest, LLM call tests
├── api/                                     # Router contract tests
│   ├── test_apply_runs_router.py            # Apply worker endpoints
│   ├── test_jobs_router_*.py                # Job filtering, filtering, import
│   ├── test_resume_download_*.py            # Resume artifact access
│   ├── test_settings_*.py                   # Profile/resume settings
│   ├── test_tailor_runs_router.py           # Tailor run queries
│   └── test_system_settings_router.py       # System-level config
└── services/                                # Cross-cutting service tests
    └── test_env_keys.py                     # Environment key validation
```

**Naming conventions**:
- `test_<feature>_<scenario>.py` — most common (e.g., `test_apply_finisher_answer_cache.py`)
- `test_<module>_property.py` — hypothesis property-based tests (e.g., `test_patcher_property.py`)
- `test_<module>_properties.py` — plural variant (e.g., `test_workday_fetcher_properties.py`)
- `test_<module>_integration.py` — end-to-end orchestrator flow (e.g., `test_apply_finisher_integration.py`)
- `test_<module>_smoke.py` — narrow happy-path validation (when present)

**Not flattened but organized by subsystem**:
- `tests/agents/resume_tailor/` — 4 test files for manifest, latex sanitize, LLM, JD enrichment
- `tests/api/` — 9 test files for each router and contract scenario
- `tests/services/` — 1 test file for shared service validation

This hybrid layout keeps the root level scannable (most tests) while grouping agent and API tests by concern.

---

## conftest.py — Marker & CLI Gate Mechanism

**File**: `/Users/jspags/Projects/agentic-job-applier/tests/conftest.py`

**Purpose**: Register the `live_agent_e2e` marker and implement opt-in skipping for live-model tests.

**Global mechanism** (conftest.py:16–77):

1. **`pytest_addoption()`** — Registers CLI flag `--run-live-agent-e2e` (conftest.py:16–32)
   - No arguments; a boolean flag (action="store_true")
   - Default: False (live tests are skipped unless explicitly requested)
   - Help text: "Run live model end-to-end tests marked with live_agent_e2e."

2. **`pytest_configure()`** — Registers marker definition (conftest.py:35–50)
   - Avoids "unknown marker" warnings
   - Makes `pytest --markers` output document the marker
   - Describes semantics: "marks tests that require live model API calls"

3. **`pytest_collection_modifyitems()`** — Applies skip logic (conftest.py:53–77)
   - Inspected every collected test item after collection
   - If `live_agent_e2e` marker is present AND flag not provided:
     - Add `pytest.mark.skip(reason="requires --run-live-agent-e2e")` to item
   - If flag is provided: all tests run (live and deterministic)

**Example usage**:
```bash
# Default: skip all live tests, run deterministic suite in CI
uv run pytest -q

# Explicit opt-in: run only live tests (+ deterministic ones)
uv run pytest --run-live-agent-e2e
```

**Key insight**: The marker gates are applied at collection time, before test execution, so no secrets are loaded unless the flag is present. Tests themselves can check `OPENAI_API_KEY` env var (as in `test_live_agent_e2e.py:38`) for extra safety.

---

## Fixture Catalogs

### `_fixtures/` — Binary & HTML Test Doubles

**Location**: `/Users/jspags/Projects/agentic-job-applier/tests/_fixtures/`

**Contents**:
- `finisher/ashby_basic_form.html` — Minimal Ashby ATS form (button, input, select)
- `finisher/greenhouse_basic_form.html` — Minimal Greenhouse ATS form

**Purpose**: Provide deterministic DOM structures for `tests/test_apply_finisher_browser_cli.py` and related tests that exercise the Playwright-mocking layer. The `FakeFinisherPage` helper reads these to initialize `aria-ref` mappings and test selector matching.

### `fixtures/` — Data Files for Parsing Tests

**Location**: `/Users/jspags/Projects/agentic-job-applier/tests/fixtures/`

**Contents**:
1. **Scraper test data** (HTML/JSON responses):
   - `icims_*.html` — iCIMS job listing pages (empty, page 0, page 1, class-before-href variant)
   - `taleo_wipo_*.{html,json}` — Taleo WIPO career portal pages
   - `workday_imf_*.json` — Workday IMF API job listing and detail responses

2. **Resume fixtures** (`resumes/`):
   - `synthetic_minimal.tex` — Canonical 3-section, multi-bullet resume for unit tests
   - `external/` — Real-world resumes (imported from external sources for end-to-end tailor tests)
   - `synthetic_failures/` — Edge cases: missing sections, malformed LaTeX, empty bullets

3. **Manifest fixtures** (`manifests/`):
   - YAML files representing parsed bullet manifests (sections, entries, bullets with IDs)
   - Used by tests that verify manifest → proposal → patched resume round-trips

**Key pattern**: `helpers/pipeline_factories.py:67–83` exposes `resume_tex_fixture_path()` which resolves `synthetic_minimal.tex` at runtime, and `build_minimal_bullet_manifest()` which parses it. Every factory-based test imports these to avoid scattering fixture paths.

### `helpers/` — Factory Functions & Test Doubles

**Location**: `/Users/jspags/Projects/agentic-job-applier/tests/helpers/`

**Files**:

1. **`pipeline_factories.py`** — Builders for domain models (conftest.py:1–210)
   - `row_int() / row_str()` — Safe DB row field extraction
   - `resume_tex_fixture_path()` — Resolve `synthetic_minimal.tex`
   - `build_minimal_bullet_manifest()` — Parse fixture into `BulletManifest`
   - `make_tailor_result()` — Stub `LlmCallResult[TailorOutput]` with deterministic token usage
   - `make_reviewer_result()` — Stub `LlmCallResult[ReviewerOutput]` with verdict + scores
   - `single_valid_patch_proposal()` — Generate one proposal that targets the synthetic fixture

   **Design principle**: Every factory returns fully validated Pydantic models so tests fail fast on schema drift. Factories accept kwargs to customize fields (e.g., `verdict=ReviewerVerdict.BETTER_THAN_BASE`) without exposing all internal structure.

2. **`fake_finisher_page.py`** — Playwright doubles (lines 1–110+)
   - `FakeLocatorState` — Configurable behavior for one ref/selector (return value, click behavior, etc.)
   - `FakeFinisherPage` — Implements `Page` / `Locator` async surface
   - Maps selectors to refs via regex (`_ref_from_selector()`) for tool tests that build locators via `page.locator(f"aria-ref={ref}")`
   - Records call history (logs) for assertions

   **Purpose**: Replace `playwright.async_api.Page` in tests so tool behavior can be asserted without a real browser. Tests construct state, call tools, then read the log to verify clicks/fills/selects.

---

## Pytest Markers

**Registered markers** (conftest.py:47–50):

1. **`live_agent_e2e`** — Tests requiring live LLM API calls
   - Default: Skipped (requires `--run-live-agent-e2e`)
   - Example: `tests/test_live_agent_e2e.py:23`
   - Preconditions: Must set `OPENAI_API_KEY` env var

2. **`asyncio`** — Async test marker
   - Provided by `pytest-asyncio` plugin
   - Used on all async test functions (most worker / agent tests)
   - Example: `test_apply_finisher_answer_cache.py:22`

3. **`parametrize`** — Pytest built-in parameter variation
   - Not custom-registered, but heavily used for scenario coverage
   - Example: `test_api_jobs_source_filter.py` parametrizes job source enums

**Default behavior**: A test marked `@pytest.mark.live_agent_e2e` will be skipped unless explicitly opted in. Skipped tests do not consume API quota or load secrets during CI.

---

## Property-Based Tests

**Philosophy**: Stress invariants with generated inputs to catch edge cases and off-by-one errors that concrete tests miss.

**Framework**: Hypothesis (installed as dev dependency)

**Files** (~5 dedicated property test files):

1. **`test_apply_finisher_answer_cache_properties.py`** (lines 1–239)
   - `test_normalize_is_idempotent()` — `normalize(normalize(x)) == normalize(x)` for arbitrary safe text
   - `test_normalize_lowercases_output()` — Result contains no uppercase
   - `test_substitute_company_replaces_every_token()` — `$COMPANY` token is fully replaced
   - `test_substitute_company_no_placeholder_is_noop()` — No token = no change
   - **Settings**: `@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])`
   - **Alphabet strategy**: `st.text(whitelist_categories=("Lu", "Ll", "Nd", "Zs", "Po"), whitelist_characters=" \t\n")`
   - Also includes concrete tests (e.g., per-company vs. anonymized tie-breaking at equal fuzzy scores)

2. **`test_patcher_property.py`** (lines 1–50+)
   - `@given(st.lists(..., min_size=..., max_size=...))` — Generate random patch counts
   - `@given(st.permutations(...))` — Generate random patch orderings
   - Verifies non-overlapping patches land at correct byte offsets regardless of order
   - Complements fixed-order `test_patcher.py` examples

3. **`test_icims_fetcher_property.py`** — Hypothesis for iCIMS pagination parsing

4. **`test_workday_fetcher_properties.py`** — Hypothesis for Workday job parsing

5. **`tests/agents/resume_tailor/test_latex_sanitize_properties.py`** — LaTeX escape/unescape invariants

**Pattern**: Property tests often complement concrete tests rather than replace them. For example:
- `test_apply_finisher_answer_cache.py` covers exact-hash hits, fuzzy hits, company-specific behavior
- `test_apply_finisher_answer_cache_properties.py` stresses the same functions with random text + company names to catch parsing edge cases

**Health checks**: Tests suppress `HealthCheck.too_slow` because model construction or DB operations can take 100+ ms, which triggers Hypothesis health-check warnings.

---

## Mutation Tests

**Tool**: `mutmut` (configured in `pyproject.toml`)

**Configuration** (pyproject.toml:92–96):
```toml
[tool.mutmut]
paths_to_mutate = "src/fetchers/linkedin_fetcher.py"
tests_dir = "tests/"
runner = "python -m pytest tests/test_linkedin_fetcher.py -x -q"
```

**Scope**: Only `src/fetchers/linkedin_fetcher.py` is instrumented.

**Why this module?**: LinkedIn is a high-volume job source for the platform; parsing errors directly impact job quality in the queue. The fetcher's filter logic (e.g., title matching, location parsing) is deterministic and safe to mutate.

**Why not dashboard or agents?**: Dashboard is component-tested (not mutation-friendly); agent orchestration involves many side effects (notifications, DB writes, API calls) that make mutation testing noise-prone.

**Usage**:
```bash
mutmut run --paths-to-mutate=src/fetchers/linkedin_fetcher.py
```

Mutmut will generate 1000s of code variants (e.g., `>` becomes `>=`, `append()` becomes no-op) and re-run the test suite for each. High survival rate indicates weak test coverage of that module.

---

## API Contract Tests

**Location**: `tests/api/`

**Philosophy**: Validate that request/response shapes match between frontend, backend, and data sources (scrapers).

**Test files** (9 routers):

1. **`test_apply_runs_router.py`** — Apply worker status queries
   - Schema: `ApplyRunDump` response shape
   - Assertions on job fields, cost tracking, telemetry

2. **`test_apply_runs_router_extra.py`** — Additional apply scenarios
   - Error paths, retry semantics, cost event persistence

3. **`test_jobs_router_*.py`** (3 files) — Job listing & filtering
   - `test_jobs_router_import.py` — Job insert/query round-trip
   - `test_jobs_router_review_reason.py` — Review reason field contract
   - `test_jobs_router_tailor_filters.py` — Tailor run filtering by job status

4. **`test_resume_download_serves_correct_pdf.py`** — Artifact access
   - Ensures `/api/jobs/{job_hash}/resume` resolves the correct PDF
   - Validates artifact path logic under different deploy configs

5. **`test_settings_provider.py`** — Settings endpoint shape
   - Profile / resume draft struct

6. **`test_settings_validate_adzuna.py`** — Input validation
   - Adzuna-specific settings constraints

7. **`test_system_settings_router.py`** — System-level config
   - Budget, max concurrency, automation mode

8. **`test_tailor_runs_router.py`** — Tailor run endpoints
   - Start, pause, fetch status, resume

**Key pattern**: Each test imports the Pydantic model from `src/` and asserts:
```python
result = api_call(...)  # e.g., POST /api/tailor-runs
assert isinstance(result, ExpectedDumpModel)
assert result.field_1 == expected_value
```

This catches schema drift where a field is renamed, removed, or typed differently on the backend without frontend updates (or vice versa).

---

## Dashboard Tests

**Framework**: Vitest + React Testing Library

**Location**: `dashboard/src/**/*.test.ts*` and `dashboard/src/**/*.integration.test.ts*`

**Configuration**:
- `package.json` scripts (lines 6–16):
  - `npm run test` → `vitest run --coverage` (CI mode, single run with coverage)
  - `npm run test:watch` → `vitest` (watch mode for development)
- Vitest config: No dedicated `vitest.config.ts`; inherits from Vite via `vite.config.ts`
- **Coverage tool**: `@vitest/coverage-v8` v4.1.2
- **DOM environment**: `jsdom` (configured implicitly in vitest defaults for `.test.ts*` files)

**Test files** (~20 files):

1. **Unit tests** (function/component isolation):
   - `JobsPage.test.ts` — URL sanitization (`toSafeJobPostingUrl()`)
   - `MissingKeyBanner.test.tsx` — Component rendering
   - `TopBar.test.ts` — Sync invalidation behavior
   - `client.test.ts` — API client shape parsing

2. **Integration tests** (page/feature level):
   - `JobsPage.integration.test.tsx` — Job list + apply + tailor flows
   - `OnboardingPage.integration.test.tsx` — Multi-step wizard
   - `HumanReviewPage.textarea.test.tsx` — Review answer input
   - `JobsPage.apply-button.test.tsx` — Apply button state + modal
   - `JobsPage.modal-flows.test.tsx` — Multiple modal scenarios

3. **Behavioral tests** (specific bug regression):
   - `JobsPage.delete-error.test.tsx` — Error handling on delete
   - `JobsPage.no-improvement-copy.test.tsx` — UI text for no-improvement status

**Naming convention**: 
- `JobsPage.test.ts` — Core unit tests (naming, parsing)
- `JobsPage.integration.test.tsx` — Full-page flow
- `JobsPage.<feature>.test.tsx` — Focused scenario (e.g., `apply-button.test.tsx`)

**Setup**:
- Imports `describe`, `it`, `expect` from `vitest`
- Uses `@testing-library/react` for render/screen/userEvent
- Mocks API client with `vi.mock()`
- Tests are written in TSX (inline JSX syntax)

**Example** (JobsPage.test.ts:1–27):
```typescript
describe("toSafeJobPostingUrl", () => {
  it("accepts https URLs", () => {
    expect(toSafeJobPostingUrl("https://example.com/jobs/1"))
      .toBe("https://example.com/jobs/1");
  });
  it("rejects javascript protocol URLs", () => {
    expect(toSafeJobPostingUrl("javascript:alert(1)")).toBeNull();
  });
});
```

**Coverage baseline**: The test plan (test-plan.md:7) notes "Vitest + React Testing Library (recommended for untested frontend)" as a recommended addition. Current dashboard coverage is ~20 tests (enough to catch major regressions but not comprehensive).

---

## Type Checking

**Tool**: `mypy` (strict mode)

**Configuration** (pyproject.toml:99–109):
```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_unused_configs = true
follow_imports = "silent"
files = [
    "api",
    "src",
    "scripts",
    "tests",
]
```

**Scope**: All four subsystems (API, source, scripts, tests) are checked with `strict=true`.

**Strict mode enforces**:
- No implicit `Any` types
- All function parameters and returns must be typed
- Optional fields must use `Optional[T]` or `T | None`
- `cast()` is documented and explicit
- No unguarded `@overload` functions

**Usage in CI**:
```bash
uv run mypy  # Runs against python_version=3.11
```

**Errors block PR** (per `.github/workflows/ci.yml:40–41`):
```yaml
- name: Run mypy (strict)
  run: uv run mypy
```

Mypy failure in CI causes the backend job to fail, blocking merge.

**Dashboard**: TypeScript in `dashboard/` uses `npm run typecheck` (tsc --noEmit) instead of mypy.

---

## CI Matrix

**File**: `.github/workflows/ci.yml`

**Jobs** (2 parallel, independent):

### Backend Job (Python 3.11)

**Runs on**: ubuntu-latest

**Steps**:
1. Checkout code (actions/checkout@v4)
2. Setup Python 3.11 (actions/setup-python@v5)
3. Install `uv` tool (astral-sh/setup-uv@v3 with cache)
4. Sync dependencies (uv sync --frozen)
5. **Run pytest (deterministic only)**
   ```bash
   uv run pytest -q
   ```
   - `-q` flag: quiet output (failures only)
   - **No `--run-live-agent-e2e` flag** → live tests are skipped
   - Must pass deterministic suite in <30s (typical)

6. **Run mypy (strict)**
   ```bash
   uv run mypy
   ```
   - All files must type-check strictly
   - Must complete in <20s (typical)

### Frontend Job (Node 22)

**Runs on**: ubuntu-latest, `working-directory: dashboard`

**Steps**:
1. Checkout code
2. Setup Node 22 (actions/setup-node@v4 with npm cache)
3. Install dependencies (npm ci)
4. **Lint** (npm run lint)
   - ESLint with max-warnings=0
   - All files must pass rules

5. **Typecheck** (npm run typecheck)
   - `tsc --noEmit`
   - No generated .js files, just type errors

6. **Test (vitest)**
   ```bash
   npm test
   ```
   - Runs `vitest run --coverage`
   - Must collect coverage in CI mode

7. **Build (production)**
   ```bash
   npm run build
   ```
   - Runs `tsc -b && vite build`
   - Ensures no TypeScript errors block bundle

**Branch protection**: A PR must pass both jobs (backend + frontend) before merge is allowed.

---

## Risks & Gotchas

### 1. Live-Test Cost Gating

**Risk**: Accidental `--run-live-agent-e2e` in CI = API quota burned.

**Mitigation**:
- CI config (`ci.yml`) explicitly runs `uv run pytest -q` with no flag (conftest.py:38)
- Default conftest behavior skips all `live_agent_e2e` tests
- Tests themselves check `OPENAI_API_KEY` (test_live_agent_e2e.py:38) as backup

**Gotcha**: Developer running `pytest --run-live-agent-e2e` locally without an API key will see test skips, not errors (because env check is inside the test function). Consider adding a warning or pre-flight check.

### 2. Flaky Async Tests

**Risk**: Tests using `@pytest.mark.asyncio` may be sensitive to timing in concurrent claim operations.

**Affected**: `test_tailor_concurrent_claims.py`, `test_queue_claim_concurrency_and_fairness.py`

**Mitigation**:
- Tests use deterministic in-memory SQLite for DB state
- Lock-based claim logic has explicit retry loops with short backoff
- Most flakiness is caught during local development; CI runs are stable

**Gotcha**: If you add async tests, import `pytest-asyncio` and mark functions with `@pytest.mark.asyncio`, or pytest-asyncio won't find them.

### 3. Dashboard Test Coverage Gaps

**Risk**: Frontend has untested components (resume download button, settings upload flow, form validations).

**Affected**: Per test-plan.md, high-priority gaps:
- `JobsPage.tsx:320` — Outbound job link sanitization (no integration test for real URLs)
- `SettingsPage.tsx:176` — Draft durability during global sync (no test for concurrent invalidation)
- `dashboard/src/lib/api/client.ts:72` — Error parse handling (no test for empty 200 responses)

**Mitigation**: test-plan.md recommends 6 new test suites (31 tests) to close gaps. P0 suites (resume download, link sanitization) should be implemented first.

**Gotcha**: Vitest is configured in `vite.config.ts` implicitly (no explicit `vitest.config.ts`), so IDE autocomplete may not work for Vitest globals. Workaround: add `/// <reference types="vitest" />` to test files.

### 4. Mutation Test Scope

**Risk**: Only LinkedIn fetcher is mutated; other modules may have silent logic errors.

**Mitigation**: LinkedIn is the highest-risk module (top job source, complex parsing). Other fetchers (Adzuna, Indeed) are tested concretely but not mutated.

**Gotcha**: If you add complex filter logic elsewhere (e.g., new job source), consider adding it to `[tool.mutmut]` `paths_to_mutate`.

### 5. Property Test Health Checks

**Risk**: Hypothesis health checks can timeout on slow test setup (DB creation, manifest parsing).

**Mitigation**: Suppress `HealthCheck.too_slow` in settings (e.g., test_apply_finisher_answer_cache_properties.py:41).

**Gotcha**: Suppressing health checks can hide real performance issues. Only suppress when the slowness is test infrastructure (DB setup), not the function being tested. If suppress count grows, refactor to use fixtures or lazy initialization.

### 6. Conftest Marker Registration Is Global

**Risk**: If a test adds a custom marker but doesn't register it in `conftest.py`, pytest will warn "unknown marker."

**Mitigation**: All custom markers are registered in `conftest.py:47–50` (currently just `live_agent_e2e`).

**Gotcha**: If you add a new test type (e.g., `@pytest.mark.manual_approval`), add it to `config.addinivalue_line()` in `pytest_configure()`.

### 7. Fixture Path Resolution

**Risk**: Fixture paths are hardcoded relative to `tests/` directory. If tests are run from a different cwd, fixtures won't be found.

**Example**: `helpers/pipeline_factories.py:78–83` resolves `Path(__file__).resolve().parent.parent / "fixtures" / "resumes" / "synthetic_minimal.tex"`.

**Mitigation**: All paths use `__file__` and `Path.resolve()` for absolute resolution.

**Gotcha**: If tests are symlinked or run from a non-repo directory, `__file__` may be unexpected. Workaround: pytest always adds `tests/` to `sys.path`, so imports of fixtures work.

### 8. API Contract Tests Are Shape-Only

**Risk**: Tests assert response schemas but don't validate business logic (e.g., cost calculations, filtering accuracy).

**Example**: `test_apply_runs_router.py` checks that `ApplyRunDump` has the right fields, but doesn't verify that cost events are summed correctly.

**Mitigation**: Business logic is tested separately in `test_budget_enforcement.py`, `test_queue_claim_concurrency_and_fairness.py`, etc.

**Gotcha**: A refactor that changes field semantics (e.g., cost is now USD instead of cents) can pass API contract tests but break consumers. Recommend adding inline docs on units and business rules.

---

## Summary

The testing architecture balances **coverage breadth** (100 pytest tests, 20 dashboard tests) with **quality depth** (property-based tests, mutation testing, strict typing). The opt-in `live_agent_e2e` gate keeps CI deterministic and secret-free while still allowing validation of real LLM behavior on-demand. Fixture and factory patterns reduce test boilerplate and catch schema drift early. Dashboard testing lags backend coverage; the test plan prescribes 6 priority suites to close critical gaps (resume access, link sanitization, draft durability).

Key success metrics:
- **CI runs in <3 min** (pytest + mypy for backend, vitest + lint + typecheck for frontend)
- **All tests deterministic by default** (no API keys, no flakiness from timing)
- **Type checking blocks merges** (`mypy --strict` on all Python code)
- **Mutation testing catches logic drift** (LinkedIn fetcher)
- **Property tests stress invariants** (normalize, patching, substitution)
