# Test Evaluation

## Detected Test Framework(s)
- Pytest (`tests/test_integration.py`)

## Test Inventory
| Test File | Framework | Type | Approx. Test Count | Quality | Notes |
| --------- | --------- | ---- | ------------------ | ------- | ----- |
| tests/test_integration.py | Pytest | Integration/unit mix | ~5 | Adequate for covered paths | Exercises DatabaseManager lifecycle, Deduplicator filtering, crawl history logging, JobPosting hash/normalization using temp SQLite DB [tests/test_integration.py:1-111] |

## Test Quality Assessment
- **Assertion quality:** Reasonable assertions on DB insert/duplicate handling, counts, and hash equality; lacks checks for error paths (e.g., failed migrations, invalid inputs) [tests/test_integration.py:12-111].
- **Edge cases:** Missing coverage for fetcher error handling, network failures, and malformed job data; tests only cover happy-path database and dedup flows.
- **Isolation:** Uses `TemporaryDirectory` and ephemeral SQLite files; no shared mutable state across tests [tests/test_integration.py:14-82].
- **Mocking:** None used; acceptable for current scope but leaves external fetchers untested.
- **Naming clarity:** Descriptive test names documenting intent [tests/test_integration.py:12-111].

**Overall Test Quality Rating:** Minimal — only one test module covering core DB/dedup basics; fetchers, orchestrator, agent pipeline, and CLI tools remain untested.

## Coverage Gaps (Untested Components)
| Component / Module | File(s) | Risk Level | Justification |
| ------------------ | ------- | ---------- | ------------- |
| Orchestrator cycle & per-source fetch flows | main.py | Medium | No tests cover end-to-end cycle, error handling, or stats updates under failures. |
| Fetchers (Greenhouse, Apify Workday, JobSpy) | src/fetchers/*.py | Medium | No unit or integration tests for request failures, data normalization, or interval parsing. |
| ADK agent pipeline | src/agents/root_apply_decider.py; scripts/process_new_jobs.py | High | Agent model stub and processing loop lack any automated coverage, making regressions likely. |
| CLI tools (status/query, find_greenhouse_id, decide_job) | scripts/status.py; scripts/query_jobs.py; scripts/find_greenhouse_id.py; scripts/decide_job.py | Low | Behavior and error handling not exercised; current hardcoded DB paths went undetected. |

## Additional Notes
- No fixtures or parameterization present; expanding scenarios will improve coverage breadth.
