# Apply Worker Subsystem Specification

## 1. Purpose

The **Apply Worker** is the browser-driven orchestrator that transforms reviewed job postings into submitted (or human-reviewed) applications. It operates exclusively in **dry-run mode** (forms filled, not auto-submitted) per SECURITY.md, except when the binary submit gate authorizes and `SAFE_MODE=false` permits firing the click.

### What Apply Worker Does
- Claims reviewed jobs from the database (read-only lease-based claiming with token ownership)
- Launches a persistent Chrome browser session via CDP and navigates to job postings
- Triggers Simplify Copilot v2.4.x extension to autofill form fields
- Uploads the tailored resume PDF (re-uploads after Simplify to override its cached version)
- Optionally invokes the apply-finisher Pydantic AI agent to handle long-tail questions (Greenhouse, Ashby only)
- Computes confidence scores and field-resolution metadata for human review
- Persists outcomes to `apply_runs` (SUCCESS/FAILED) and `apply_handoffs` (NEEDS_REVIEW handoff)
- Evaluates the binary submit gate; auto-submits only when all conditions pass AND `SAFE_MODE` is not set

### What Apply Worker Does NOT Do
- Create or destroy the host Chrome process; assumes it's running before startup
- Modify the apply-finisher agent's decision logic; delegates to `run_finisher` as-is
- Handle user-facing form validation errors post-submit (retries at the `apply_runs` level)
- Resolve multi-step workflows (e.g., Lever's "finish application later" links)
- Update `job_postings.status` directly; transitions occur via `transition_handoff_status` in the human-review workflow

## 2. Worker Entry Flow

Entry point: `scripts/process_apply_jobs.py` → `main()` → `run_apply_loop()` or `_apply_once()`.

### Polling Loop Architecture (process_apply_jobs.py:826-907)

```
run_apply_loop() [persistent or single-shot]
├─ Read APPLY_MODE_KEY from system_settings (autonomous/both vs opt_in)
│  └─ If opt_in: sleep poll_interval, never claim (prevents Chrome offline → FAILED rows)
├─ Probe Chrome reachability: check_chrome_reachable(cdp_url)
│  └─ If unreachable: sleep poll_interval, never claim
├─ _apply_once(): claim_next_apply_job(max_retries, lease_seconds)
│  ├─ BEGIN IMMEDIATE transaction in SQLite
│  ├─ SELECT one eligible review_run with PASS/TAILORED/BASE verdict
│  │  └─ Filters: no existing SUCCESS apply_runs, no PENDING with active lease, 
│  │     failure_count < max_retries, retry_at <= now
│  ├─ INSERT PENDING apply_runs with claim_token
│  ├─ COMMIT
│  └─ Return merged job_postings + review_runs + apply metadata
├─ _process_apply_row(): apply_to_job(cdp_url, source_url, resume_pdf_path, ...)
│  └─ See section 3 (CDP architecture) and section 6 (browser session lifecycle)
├─ Persist outcome: record_apply_success() or record_apply_failure()
│  └─ See section 7 (outcome states)
└─ On failure + retries_remaining: schedule next_retry_at via _calculate_next_retry_at()
   └─ Backoff: retry_count * backoff_multiplier ^ (count-1)
```

**Mode gating (process_apply_jobs.py:803-824):**
- `autonomous` / `both`: worker claims immediately
- `opt_in`: worker skips claiming (prevents FAILED rows when Chrome is closed)

**Chrome-ready preflight (process_apply_jobs.py:269-316):**
- Synchronous: playwright importable, DISPLAY set on Linux
- Asynchronous: `check_chrome_reachable(cdp_url)` returns 200 from `/json/version`

**Claim semantics (src/database/_mixins/apply.py:178-307):**
- Each PENDING row carries a `claim_token = os.urandom(32).hex()` (32-byte opaque token)
- Claim is leased: `started_at > datetime('now', '-lease_seconds seconds')` filters stale PENDING
- Only one PENDING per review_run allowed (prevents double-claiming)
- Bug 4 guard: never re-claim a PENDING row that already has `claim_token IS NOT NULL` (rejects stale user-triggered enqueues)

## 3. CDP Architecture

### Default Configuration

- `DEFAULT_CDP_URL = "http://localhost:9222"` (src/agents/apply_worker/schemas.py:38)
- Override via `CHROME_CDP_URL` env var or `--cdp-url` flag
- Docker container → host Chrome: `host.docker.internal:9222` (Docker Desktop) or host-gateway IP (Linux)

### Host-Header Override (Bug 3 Fix)

**Problem:** Chrome 148+ rejects HTTP/WS requests whose Host header differs from localhost or an IP literal. Container-default `host.docker.internal:9222` fails this check.

**Solution:** Force `Host: localhost:<port>` header for both the HTTP `/json/version` probe and the Playwright WS handshake.

**Implementation:**
```python
def _cdp_localhost_host_header(cdp_url: str) -> dict[str, str]:
    """Force Host: localhost:PORT for the CDP handshake (browser.py:158-199)."""
    parsed = urlparse(cdp_url)
    port = parsed.port
    if port is None:
        return {}  # No port → no override (Chrome's port-less form is non-standard)
    hostname = parsed.hostname or ""
    # Skip override if URL already uses localhost or IP literal
    if hostname in {"localhost", "::1"}:
        return {}
    try:
        ip_address(hostname)
        return {}  # IP literal → no override
    except ValueError:
        pass
    return {"Host": f"localhost:{port}"}
```

**Applied at two points:**
1. `check_chrome_reachable()` (line 329): `httpx.AsyncClient.get(..., headers=_cdp_localhost_host_header(cdp_url))`
2. `apply_to_job()` (line 387): `pw.chromium.connect_over_cdp(cdp_url, headers=cdp_headers)`

**Evidence:** test_cdp_host_header_override.py:127-150 verifies the probe succeeds when URL uses IP literal but Host header is forced to localhost.

### Chrome Reachability Probe

```python
async def check_chrome_reachable(cdp_url: str = DEFAULT_CDP_URL) -> bool:
    """Verify Chrome responds to /json/version (browser.py:314-333)."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{cdp_url}/json/version",
                timeout=5.0,
                headers=_cdp_localhost_host_header(cdp_url),
            )
            return response.status_code == 200
    except (httpx.HTTPError, OSError):
        return False
```

**No reconnection retry:** If probe returns False, the loop sleeps without claiming. This design prevents FAILED rows when Chrome is temporarily offline or shut down.

## 4. Simplify Autofill Trigger

### Detection (browser.py:567-573)

Before uploading resume, the worker polls for Simplify's shadow root to appear:

```python
simplify_detected: bool = await playwright_page.evaluate(
    _JS_DETECT_SIMPLIFY,  # Polls DOM every 500ms for up to 45s
    {
        "intervalMs": SIMPLIFY_POLL_INTERVAL_MS,  # 500ms (schemas.py:22)
        "timeoutMs": SIMPLIFY_POLL_TIMEOUT_MS,    # 45s (schemas.py:25)
    },
)
```

The JavaScript (browser.py:80-105) walks every `<div class="simplify-jobs-shadow-root">` element, checks its shadowRoot, and returns `true` if any of the autofill labels ("Autofill", "Autofill all fields with AI", "Fill", "Continue filling") is found.

**Verified behavior (2026-05-07):** Simplify v2.4.6 takes ~15s on Greenhouse to render its full UI; 45s provides headroom for slower pages.

### Triggering & Settlement (browser.py:598-625)

1. **Resume upload BEFORE Simplify click** (line 582): Simplify's autofill click navigates to a preview URL (storage.googleapis.com), clobbering the form's file input. Our upload must happen first.

2. **Click the button** (line 600): JavaScript pierces shadow root and clicks first non-forbidden aria-label button. Returns status like `"CLICKED:Autofill"` or `"NO_AUTOFILL_BUTTON"`.

3. **Settle polling** (lines 612-625): Instead of fixed sleeps, poll the form's filled-field count every 500ms until it stabilizes for 2s or 30s elapses:
   ```python
   simplify_filled_count = await _wait_for_simplify_to_settle(
       playwright_page,
       max_wait_seconds=30.0,
       stability_window_seconds=2.0,
       poll_interval_seconds=0.5,
   )
   ```
   The JavaScript counts inputs with non-blank values, React-Select shells with picked values, and checked checkboxes.

4. **Resume re-upload** (lines 633-656): Simplify uploaded its cached resume; re-upload ours to ensure tailoring wins.

### Page State Assertions

- Before navigation: skip goto if already on correct path (to avoid Simplify re-render failure)
- After navigation: wait for `domcontentloaded`, then best-effort `networkidle` (10s timeout, non-fatal if it times out)
- Before Simplify click: ensure form page is settled

## 5. Browser Session Lifecycle

### Connection & Context (browser.py:385-410)

```python
async with async_playwright() as pw:
    try:
        cdp_headers = _cdp_localhost_host_header(cdp_url) or None
        browser = await pw.chromium.connect_over_cdp(cdp_url, headers=cdp_headers)
    except Exception as exc:
        return ApplyRunResult(success=False, ...)
    
    context = browser.contexts[0] if browser.contexts else None
    if context is None:
        return ApplyRunResult(success=False, ...)
    
    page = await context.new_page()
    try:
        result = await _run_application_flow(page, ...)
    finally:
        await page.close()
```

**Key points:**
- Uses the persistent default browser context (context[0]), not a private one
- Opens a new page per apply run; closes it in finally block
- Persistent cookies allow Simplify to recognize the logged-in profile

### Tab Management for Finisher (browser.py:202-311)

Before running the finisher, ensure the agent-browser daemon is connected and on the correct tab:

```python
session_ok, session_msg = await _ensure_agent_browser_session(cdp_url, apply_url)
```

This helper:
1. Calls `agent-browser connect <cdp_url>` to attach daemon to host Chrome
2. Calls `agent-browser tab list` to enumerate tabs
3. If apply_url matches an existing tab, switches to it via `agent-browser tab <tabId>`
4. If no match, opens apply_url in agent-browser (finisher snapshot will then see the form)

## 6. Handoff to Apply-Finisher

### Boundary & Preconditions (browser.py:716-772)

The finisher runs **only** when:
1. `finisher_context is not None` (caller provided company/role/JD/paths)
2. `supported_finisher_ats(ats_platform)` returns a dialect (Greenhouse or Ashby)

For unsupported ATS (Lever, Workday, iCIMS, etc.): finisher is **skipped**, outcome remains NEEDS_REVIEW, diagnostics show `finisher_outcome="SKIPPED"`.

### What the Finisher Receives

```python
finisher_result = await run_finisher(
    apply_url=playwright_page.url,
    ats="greenhouse" | "ashby",
    target_company=context.target_company,
    target_role=context.target_role,
    profile_yaml=deps.profile_yaml,
    job_description_excerpt=excerpt_job_description(context.job_description),
    defer_rules=deps.defer_rules,
    cache=deps.answer_cache,
    apply_run_id=apply_run_id,  # For cost attribution
)
```

**Inputs sourced from:**
- `FinisherContext`: job posting metadata (company, role, description, resource paths)
- `FinisherDependencies`: loaded YAML files (defer_rules, answer_cache, candidate_profile)
- Job description is trimmed to 6000 chars to fit agent token budget

### What the Finisher Returns (FinisherResult)

- `outcome: str` — "COMPLETE", "AGENT_GAVE_UP", "USAGE_LIMIT_HIT", "RUNTIME_ERROR"
- `fields_filled: int` — Tier-1 fills reported by agent
- `fields_deferred: int` — Tier-3 questions skipped
- `all_required_filled: bool` — Every required field is either filled or drafted
- `has_tier3_deferred: bool` — Convenience: `len(deferred_questions) > 0`
- `has_tier2_pending: bool` — Tier-2 drafts awaiting human review
- `drafted_fields_flagged_for_verify: list[Draft]` — Drafts with per-field confidence scores
- `turns_used: int` — Agent iterations consumed
- `cost_usd: float` — Token cost via litellm
- `deferred_questions: list[...] ` — Tier-3 questions deferred

## 7. Outcome States & Persistence

### Browser-Level Outcomes (ApplyOutcome enum, schemas.py:47-62)

| Outcome | Meaning | When It Occurs |
|---------|---------|----------------|
| `NEEDS_REVIEW` | Form filled, not submitted | Default; gate withheld submit or form had no submit selector |
| `SUBMITTED` | URL changed after submit click | Submit succeeded and gate authorized |
| `FAILED_PREFILL` | Form fields couldn't be filled | Simplify didn't activate or upload failed |
| `FAILED_UPLOAD` | Resume PDF upload failed | File not found or upload step crashed |
| `FAILED_NAVIGATION` | Couldn't reach the posting URL | Navigation timed out or CDP connection lost |
| `FAILED_OTHER` | Generic browser error | CDP protocol error, exception in JS eval, etc. |

### Run-Level States (apply_runs table, apply.py:71-94)

| Status | Meaning | Transition |
|--------|---------|-----------|
| `PENDING` | Claimed, in-flight | START → SUCCESS or FAILED |
| `SUCCESS` | Browser automation completed (outcome persisted regardless of form success) | PENDING → SUCCESS |
| `FAILED` | Browser crashed or timed out before finishing | PENDING → FAILED + next_retry_at scheduled |

**Critical distinction:** `status=SUCCESS, outcome=NEEDS_REVIEW` is a valid end state (form filled, no submit). `status=FAILED, outcome=FAILED_OTHER` means the browser work didn't complete.

### Handoff-Level States (apply_handoffs table, apply.py:105-127)

| Handoff Status | Meaning |
|---|---|
| `PENDING_REVIEW` | Worker wrote handoff, awaiting human action |
| `APPROVED` | Reviewer approved; apply_runs row's outcome is enacted |
| `REJECTED` | Reviewer rejected; job status → REJECTED |

Only `outcome=NEEDS_REVIEW` apply_runs rows create apply_handoffs. SUBMITTED/FAILED rows do not.

### Persistence Flow (process_apply_jobs.py:685-800)

```
_process_apply_row():
├─ result = apply_to_job(...)
└─ if result.success:
   ├─ record_apply_success(run_id, claim_token, outcome, ...)
   │  └─ UPDATE apply_runs SET status=SUCCESS, outcome=?, ... WHERE id=? AND claim_token=?
   │
   └─ if outcome == "NEEDS_REVIEW":
      └─ record_apply_handoff(apply_run_id, job_hash, ..., deferred_questions_json, finisher_diagnostics_json)
         └─ INSERT INTO apply_handoffs (...) VALUES (...) ON CONFLICT(apply_run_id) DO UPDATE ...
   
   else (result.success=False):
   └─ _handle_apply_failure(run_id, claim_token, error, outcome, next_retry_at, ...)
      └─ UPDATE apply_runs SET status=FAILED, error=?, next_retry_at=?, ... WHERE id=? AND claim_token=?
         └─ If attempt >= max_retries: notify terminal failure
```

**Claim ownership check:** Every update requires `claim_token` match. Raises `ClaimOwnershipError` if stale or reassigned. Caller logs warning and returns 1 (processed).

## 8. apply_handoffs Row Contract

When `outcome=NEEDS_REVIEW`, `record_apply_handoff()` (apply.py:467-572) writes:

```sql
INSERT INTO apply_handoffs (
    apply_run_id,           -- apply_runs.id
    job_hash,               -- stable job identifier
    review_run_id,          -- source review_run.id
    handoff_status,         -- 'PENDING_REVIEW' (fixed)
    apply_outcome,          -- 'NEEDS_REVIEW' (always for handoff rows)
    resume_source,          -- 'TAILORED' or 'BASE'
    resume_pdf_path,        -- /path/to/resume.pdf
    confidence_score,       -- float [0.0, 1.0]
    confidence_report_json, -- ConfidenceReport.model_dump_json()
    unresolved_fields_json, -- JSON list of UnresolvedField
    screenshot_path,        -- /path/to/screenshot_pre_submit.png
    dom_snapshot_path,      -- /path/to/dom_snapshot.html
    ats_platform,           -- 'greenhouse', 'lever', 'unknown', etc.
    page_url,               -- final in-browser URL
    deferred_questions_json,   -- (Issue #59) list of Tier-3 questions
    finisher_diagnostics_json  -- (Issue #59) FinisherDiagnostics.model_dump_json()
)
```

**What human-review queue expects:**
- `screenshot_path` + `dom_snapshot_path`: visual audit trail
- `confidence_score` + `confidence_report_json`: ranked checks (resume uploaded, form settled, required fields filled, etc.)
- `unresolved_fields_json`: rich metadata for each unfilled field (label, type, options, selector, current_value)
- `deferred_questions_json`: Tier-3 questions finisher logged (human must answer to proceed)
- `finisher_diagnostics_json`: finisher outcome, turns, cost, drafted field confidences, submit gate decision, any validation toasts scraped post-submit

## 9. Chrome Reachability Chip (Process-Level)

The top-bar "Chrome ready / offline" status is computed by the apply loop's live probe:

```python
while True:
    if not await _is_apply_mode_active(db):
        sleep()
        continue
    
    chrome_reachable = await check_chrome_reachable(cdp_url)
    if not chrome_reachable:
        logger.debug("Chrome unreachable; sleeping without claim")
        sleep()
        continue
    
    processed = await _apply_once(...)  # Claims and processes
```

**Behavior:**
- Probe fires every poll cycle (default 60s)
- No automatic reconnection; relies on external Chrome-restart supervisor
- If Chrome is offline, the loop sleeps and never claims jobs, preventing FAILED rows
- When Chrome restarts, the next probe succeeds and claiming resumes

## 10. Concurrency & Claim-Lease Semantics

### Claim-Lease Design

- **Lease duration:** `DEFAULT_APPLY_CLAIM_LEASE_SECONDS = 1800` (30 min, apply.py:21)
- Browser operations are slower than agent runs; generous budget prevents false stale detection
- At startup: `mark_stale_apply_runs_failed(lease_seconds)` converts PENDING rows older than lease to FAILED

### Multi-Job Race Safety

**Atomic claiming:**
```sql
BEGIN IMMEDIATE  -- Serialize all readers
SELECT ... LIMIT 1  -- Pick one eligible candidate
INSERT INTO apply_runs (..., claim_token)  -- Atomically insert PENDING
COMMIT
```

**Concurrency guards:**
1. No existing SUCCESS apply_runs for this review_run
2. No PENDING with `claim_token IS NOT NULL` (Bug 4: rejects stale user-triggered enqueues)
3. No PENDING within lease window (active claim)
4. Failure count < max_retries
5. Next retry_at <= now

Only one apply worker can claim each review_run in each cycle due to LIMIT 1 + IMMEDIATE transaction.

## 11. SAFE_MODE (Kill Switch)

### Environment Variable Gating

```python
def _is_safe_mode() -> bool:
    raw = os.environ.get("SAFE_MODE", "").strip().lower()
    return raw in {"true", "1", "yes", "on"}
```

**Documentation:** `.env.example`, `SECURITY.md`

### Disabling Layers

1. **Process-level:** `safe_mode_from_env()` in `process_apply_jobs.main()` (line 976) sets `dry_run` parameter
   - If `SAFE_MODE=true`, the loop never fires submit clicks
   - Logged: "Apply worker: auto-submit gate ENABLED / DISABLED"

2. **Per-run:** `finisher_context.safe_mode` field (FinisherContext dataclass, finisher_integration.py:104)
   - Built from `safe_mode_from_env()` at claim time

3. **Gate evaluation:** `evaluate_submit_gate()` (finisher_integration.py:204-253) returns `(False, "safe_mode")` if safe_mode=true, regardless of finisher result

**Effect:** With `SAFE_MODE=true`, all applies land as `status=SUCCESS, outcome=NEEDS_REVIEW`. No submit attempt is made.

## 12. Risks & Gotchas

### Host-Header Quirk (Bug 3)

- **Symptom:** CDP probe returns 500 on Chrome 148+; connection fails with "Host header rejected"
- **Root cause:** Chrome 148 validates Host header against localhost or IP literal
- **Mitigation:** Force `Host: localhost:PORT` regardless of URL hostname
- **Fallout:** If you override to localhost on a URL that already uses localhost, Chrome's `/json/version` echoes `ws://localhost:PORT` which resolves inside the container (breaking Playwright's connect)
  - **Guard:** Skip override if URL already uses localhost or IP literal
  - **Tested:** test_cdp_host_header_override.py

### Docker Desktop Proxy IP Quirk

- **Observed:** Mac host → container source IP shows as `172.66.0.243` (vpnkit NAT), not `127.0.0.1`
- **Effect on tests:** Localhost-binding tests may fail if they assume source=127.0.0.1
- **Mitigation:** Tests use `127.0.0.1` bindings; Docker Desktop's `host.docker.internal` resolves properly

### Chrome Version Drift

- **Simplify timing:** v2.4.6 observed ~15s UI render; older versions may differ
- **Host-check strictness:** Chrome 148+ enforces Host header; older versions may not
- **Mitigation:** timeouts are generous (45s for Simplify); host-header override is defensive (doesn't break older Chrome)

### Simplify Extension Dependency

- **User must be logged in:** Simplify only auto-fills if the profile is authenticated
- **Version lock:** Tested on v2.4.6; future versions may change aria-labels or shadow-root structure
- **Fallback:** If Simplify doesn't activate (`simplify_detected=false`), form is hand-filled by finisher or left blank
- **Resume clobber:** Simplify's autofill clicks upload its cached resume; re-upload ours afterward

### Race on Simplify Post-Navigate

- **Symptom:** Simplify autofill click navigates tab to a preview URL (storage.googleapis.com); form is no longer visible
- **Mitigation:** Resume upload happens BEFORE Simplify click; re-upload after settle
- **Observation:** Storage URL is temporary; page eventually settles back to the form (observed on Greenhouse)

### Finisher Out-of-Scope ATS

- **Unsupported:** Lever, Workday, iCIMS, SmartRecruiters
- **Behavior:** Finisher is skipped; outcome remains NEEDS_REVIEW; diagnostics show `finisher_outcome="SKIPPED"`
- **Design:** Allows graceful degradation; human reviews the form without finisher's long-tail answers

---

## Diagrams

### Apply Lifecycle (Sequence Diagram)

```
Worker              Database          Chrome            Finisher
  |                   |                 |                  |
  +--claim_next_apply_job()---->|       |                  |
  |                   |<--PENDING apply_runs row           |
  |<--merged job row--|         |                          |
  |                   |         |                          |
  |-----apply_to_job()--------->|                          |
  |                             |     navigate            |
  |                             |<--goto(apply_url)       |
  |                             |                         |
  |                             |  detect Simplify        |
  |                             |  poll shadow-root       |
  |                             |                         |
  |                             | upload_resume           |
  |                             |<--file input            |
  |                             |                         |
  |                             | click Simplify btn      |
  |                             |<--autofill              |
  |                             |                         |
  |                             | wait_for_settle         |
  |                             |<--poll filled count     |
  |                             |                         |
  |                             | reupload_resume         |
  |                             |<--file input (override) |
  |                             |                         |
  |                             | scan_unresolved_fields  |
  |                             |<--DOM query             |
  |                             |                         |
  |                             | compute_confidence      |
  |                             |<--count checks          |
  |                             |                         |
  +-----run_finisher()----->        (if supported ATS)     |
  |                   |              |<--agent-browser-------->|
  |                   |              |<--snapshots & fills------|
  |                   |<--FinisherResult--                  |
  |                   |              |                      |
  | evaluate_submit_gate()           |                      |
  | (check: all_required_filled      |                      |
  |  no_tier3_deferred, gate passes) |                      |
  |                   |              |                      |
  +----try_submit_and_classify()---->|                      |
  |                   |              |  click submit        |
  |                   |              |<--wait for URL change|
  |                   |              |  (or scrape toasts)  |
  |                   |              |                      |
  | outcome determined (SUBMITTED/   |                      |
  | NEEDS_REVIEW/FAILED_OTHER)       |                      |
  |                   |              |                      |
  +--record_apply_success()-->|       |                      |
  |   (update apply_runs             |                      |
  |    set status=SUCCESS)           |                      |
  |                   |              |                      |
  +--record_apply_handoff()--->|     |                      |
  |   (if NEEDS_REVIEW outcome)      |                      |
  |   insert apply_handoffs          |                      |
  |   with deferred_questions_json   |                      |
  |   and finisher_diagnostics_json  |                      |
  |                   |              |                      |
```

### Apply Loop Control Flow (Flowchart)

```
START
  |
  v
[Apply mode = autonomous/both?]--NO--> [Sleep poll_interval] --> (loop)
  |
  YES
  |
  v
[Chrome reachable?]--NO--> [Sleep poll_interval] --> (loop)
  |
  YES
  |
  v
[BEGIN IMMEDIATE transaction]
  |
  v
[SELECT one eligible review_run]--NULL--> [ROLLBACK] --> [Return 0] --> (loop)
  |
  FOUND
  |
  v
[INSERT PENDING apply_runs + claim_token]
  |
  v
[COMMIT] --> [Release transaction lock]
  |
  v
[Validate job_hash]--FAIL--> [record_apply_failure(max_retries=0)]
  |                           |
  OK                          v
  |                      [return 1]
  v
[Resolve resume path]--FAIL--> [record_apply_failure(max_retries=0)]
  |                            |
  OK                           v
  |                       [return 1]
  v
[apply_to_job()] -----EXCEPTION----> [record_apply_failure(max_retries=max_retries)]
  |                                   |
  SUCCESS                             v
  |                              [return 1]
  v
[result.success?]--NO--> [_handle_apply_failure(...)]
  |                      |
  YES                    v
  |                 [if attempt >= max_retries: notify]
  v                 [return 1]
[record_apply_success(...)]
  |
  v
[Persist confidence, unresolved fields, diagnostics]
  |
  v
[outcome == NEEDS_REVIEW?]--NO--> [return 1] --> (loop)
  |
  YES
  |
  v
[record_apply_handoff(...)]
  |
  v
[Log & record cost telemetry]
  |
  v
[return 1] --> (loop)
```

### Submit Gate Decision Tree (finisher_integration.py:204-253)

```
evaluate_submit_gate():
  |
  +-- safe_mode=true? --> FALSE, "safe_mode"
  |
  +-- dry_run=true? --> FALSE, "dry_run"
  |
  +-- finisher_result.outcome != COMPLETE? --> FALSE, "finisher_incomplete"
  |
  +-- finisher_result.all_required_filled? 
      |
      NO --> FALSE, "finisher_incomplete"
      |
      YES
      |
      +-- finisher_result.has_tier3_deferred?
          |
          YES --> FALSE, "tier3_deferred"
          |
          NO
          |
          +-- finisher_result.has_tier2_pending?
              |
              NO --> TRUE, "auto_submit"
              |
              YES
              |
              +-- all drafted_fields >= tier2_confidence_threshold?
                  |
                  YES --> TRUE, "auto_submit"
                  |
                  NO --> FALSE, "tier2_pending"
```

---

## Summary

The Apply Worker is a stateless, claim-leased browser orchestrator that bridges reviewed job postings and Simplify-powered form autofill, with optional Pydantic AI finisher handoff for long-tail questions. It operates in dry-run mode by default, queuing all outcomes for human review via `apply_handoffs`, and only auto-submits when the binary gate passes and `SAFE_MODE` permits. Key hardening: claim tokens enforce ownership, Chrome reachability probes prevent offline FAILED rows, host-header overrides defend against Chrome 148+ host checks, and Simplify settle polling replaces fixed sleeps for adaptive wait times. The subsystem is self-contained in `src/agents/apply_worker/`, uses persistent browser contexts to preserve login state, and gracefully degrades on unsupported ATS platforms.

