# fetch-gap-audit-006 — Playwright DOM stability + MutationObserver for React re-mounts

**Sources:**
- https://playwright.dev/docs/actionability (WebFetched 2026-05-25)
- WebSearch results 2026-05-25, query: `Playwright wait for stable DOM idle MutationObserver form filling React re-mount`

**Trigger:** Gap area #1 — `gap-analysis-ashby.md §4` documents Ashby's EEO fieldset UUIDs changing between dom_pre and dom_post (`5f05dbce-…` → `468d3724-…`). Epic Phase C: "wait for stable DOM (300ms idle) after each click before re-snapshotting." Is 300ms enough?

## Playwright's built-in stability check (verbatim)

> **Element is considered stable when it has maintained the same bounding box for at least two consecutive animation frames.**

Two animation frames at 60Hz ≈ 33ms. This check runs automatically before `click()`, `fill()`, `type()`, etc.

**This is insufficient for React re-mounts.** A re-mount can produce identical bounding boxes on the same coordinates while the underlying DOM node is a brand-new element with different React internal state and potentially different name attributes (Ashby's UUID swap is exactly this). The old element is unmounted; any value written to it is discarded.

## What 300ms idle actually buys us

300ms is **roughly 18 animation frames** — enough that any genuine re-render cycle (React reconciliation typically completes within 1-2 frames after a state change settles) has finished. It is NOT a guarantee:

- If the re-render is gated on an `await` (e.g., loading remote dropdown options), 300ms can be too short.
- If the React Suspense boundary is in play, it can be much longer.

## Recommended pattern (synthesized from search + Playwright docs)

A MutationObserver-based wait is more robust than a fixed timeout:

```js
// Injected via page.evaluate or addInitScript
async function waitForDomQuiet(targetSelector, quietMs = 300, timeoutMs = 5000) {
    const target = document.querySelector(targetSelector) || document.body;
    return new Promise((resolve, reject) => {
        let timer;
        const deadline = setTimeout(() => {
            obs.disconnect();
            reject(new Error('dom_quiet_timeout'));
        }, timeoutMs);
        const obs = new MutationObserver(() => {
            clearTimeout(timer);
            timer = setTimeout(() => {
                obs.disconnect();
                clearTimeout(deadline);
                resolve(true);
            }, quietMs);
        });
        obs.observe(target, { childList: true, subtree: true, attributes: true });
        // Start the quiet timer immediately in case no mutations happen.
        timer = setTimeout(() => {
            obs.disconnect();
            clearTimeout(deadline);
            resolve(true);
        }, quietMs);
    });
}
```

This waits until **no DOM mutations have happened for `quietMs`**, with a hard ceiling of `timeoutMs`. More accurate than `page.wait_for_timeout(300)` (which is unconditional) and more reliable than `page.wait_for_load_state("networkidle")` (which hangs on chatty extensions per the existing `browser.py` line 332-340 comment).

## Two concrete improvements to the epic

1. **Replace the fixed 300ms with a MutationObserver-based `wait_for_dom_quiet(quiet_ms=300, timeout_ms=2000)` tool.** This is one of the 8 BYO tools the finisher exposes. It is dramatically more robust on Ashby's re-mounting fieldsets.

2. **After each click on a React-Select option or radio inside a fieldset, the finisher should re-snapshot AND verify the value persisted.** Pattern:
   ```python
   await tools.click(ref)
   await tools.wait_for_dom_quiet()
   snap2 = await tools.get_snapshot()
   if not field_has_value(snap2, ref):
       raise ModelRetry("Value did not persist; element may have re-mounted")
   ```
   The `ModelRetry` exception (Pydantic AI primitive, per sub-agent A) auto-loops the agent. This makes the React re-mount tolerated by design instead of an undetected silent fail.

## Locked decisions to sanity-check

- **Locked decision #2 in the epic README ("BYO Playwright tools over CDP")** lists the tool set but doesn't include `wait_for_dom_quiet`. The epic phase C lists 6 tools (`get_snapshot, click, fill, select, defer, complete_apply`) — **`wait_for_dom_quiet` is missing**. Recommend adding it as a 7th tool. Without it, the agent has no way to robustly handle Ashby re-mounts, and the "300ms idle after each click" guidance is unenforceable from the agent's side.
- The existing flow in `browser.py:407` uses `await asyncio.sleep(8)` after Simplify autofill. **That 8s is hardcoded** and unrelated to the per-click idle wait. Both can coexist.
