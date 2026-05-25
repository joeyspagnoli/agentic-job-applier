# local-gap-audit-003 — Simplify invocation timing + verify-after-fill detection

**Source:** `src/agents/apply_worker/browser.py:_run_application_flow` lines 361-411, `_trigger_simplify_autofill` lines 494-520.
**Trigger:** Epic Phase D bullet 4 — "verify-after-fill in `_run_application_flow`: after Simplify settles, read 2-3 known input values…" Locked decision 4 from gap-synthesis: Simplify is racy on Lever (filled 009, empty 010/011).

## Current Simplify invocation

```python
# Step 3: Wait for Simplify extension to activate
simplify_detected: bool = await playwright_page.evaluate(
    _JS_DETECT_SIMPLIFY,
    {
        "intervalMs": SIMPLIFY_POLL_INTERVAL_MS,
        "timeoutMs": SIMPLIFY_POLL_TIMEOUT_MS,
    },
)
# Step 4: upload resume first (lines 376-389)
# Step 5: click Autofill (lines 394-411)
if simplify_detected:
    autofill_click_status = await _trigger_simplify_autofill(playwright_page)
    import asyncio
    await asyncio.sleep(8)
```

The 8-second fixed sleep at line 407 is the entire "Simplify is filling" wait. The flow then goes straight into `scan_unresolved_fields` (line 415).

## Gap vs the epic's verify-after-fill spec

The epic says "If still empty after the click, log `simplify_no_op=true` so the finisher knows to start from scratch." Today **the only signal we have is the click status from `_JS_CLICK_SIMPLIFY_AUTOFILL`** — one of `CLICKED:Autofill`, `NO_SHADOW_HOST`, `SHADOW_HOST_BUT_NO_ROOT`, `NO_AUTOFILL_BUTTON`, or `EXCEPTION:*`. The status confirms the click happened; it doesn't confirm fills landed.

**No code today reads known-field values post-Simplify.** The verify step described in gap-synthesis §3d and Phase D bullet 4 needs to be net-new logic. Suggested implementation:

```python
# After the 8s settle, verify-after-fill
VERIFY_SELECTORS_BY_ATS = {
    ATSPlatform.GREENHOUSE: ["#first_name", "#last_name", "#email"],
    ATSPlatform.LEVER: ["input[name=name]", "input[name=email]"],
    ATSPlatform.ASHBY: ["#_systemfield_name", "#_systemfield_email"],
}
selectors = VERIFY_SELECTORS_BY_ATS.get(ats_platform, [])
verify_results = await _read_known_values(playwright_page, selectors)
simplify_no_op = all(v.strip() == "" for v in verify_results.values()) if verify_results else False
```

Then pass `simplify_no_op` into the finisher's run_state.

## Is the 8-second sleep enough?

The Lever races in iters 009/010/011 (gap-synthesis §0) are all "Simplify clicked, fields empty 8s later." That means **the sleep is fine but the click sometimes no-ops** — verify-after-fill is the only reliable signal. 300ms idle (epic Phase C) is not what we want here; that's for *between agent clicks during the finisher loop*, not for *after the Simplify autofill bulk-fill*.

## Open issue: how does the finisher "start from scratch" on a Lever no-op?

The epic says "the finisher knows to start from scratch" but Lever is out of scope for v1. **For Greenhouse and Ashby specifically, even when Simplify no-ops, the finisher still gets a clean AX-tree snapshot and can fill from profile.** There's no special "start from scratch" mode needed — the finisher's loop is field-by-field, profile-direct OR draft, regardless of how many fields Simplify pre-filled. The `simplify_no_op` signal is purely diagnostic (drives telemetry / logging), not control flow.

**Recommendation:** keep `simplify_no_op` as a boolean field on `FinisherResult` for telemetry. Don't branch on it for any logic in v1.
