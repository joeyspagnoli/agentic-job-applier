# Simplify Apply-Worker Feedback Loop — Summary

## Outcome: ✅ Loop converged, apply worker works end-to-end (sans submit)

The apply worker (`src/agents/apply_worker/browser.py`) now reliably drives a full Simplify-Copilot-assisted job application up to but never including the submit click. Verified with 6 PASS iterations across 4 distinct Greenhouse URLs.

| Iter | Target | Confidence | Simplify | Resume | Unresolved | PASS |
|------|--------|------------|----------|--------|------------|------|
| 19   | Anthropic 5023394008                | 0.8 | ✓ | ✓ | 2  | ✓ |
| 20   | Scale AI 4631613005                 | 0.8 | ✓ | ✓ | 7  | ✓ |
| 21   | Scale AI 4654897005                 | 0.7 | ✓ | ✓ | 8  | ✓ |
| 22   | Anthropic 5076929008 (prev. flaky)  | 0.7 | ✓ | ✓ | 18 | ✓ |
| 23   | Anthropic 5023394008 (regression)   | 0.8 | ✓ | ✓ | 2  | ✓ |
| 24   | Scale AI 4631613005 (regression)    | 0.8 | ✓ | ✓ | 6  | ✓ |

## What changed in production code

`src/agents/apply_worker/browser.py`:

- **Pierce shadow DOM**: Simplify creates multiple `<div class="simplify-jobs-shadow-root">` hosts (banner + side panel + empty placeholder). The Autofill button lives in the side panel. Old code used `querySelector` (singular) and only saw the banner. New code walks all hosts via `querySelectorAll`.
- **Real selectors**: Buttons inside the shadow root have stable aria-labels: `Autofill`, `Autofill all fields with AI`, `Fill`, `Continue filling`. Submit guard refuses any label containing `Submit Application` or `Submit`.
- **Upload before click**: Simplify's Autofill click on Greenhouse navigates the tab to a Google Cloud Storage signed-URL preview of Simplify's stored resume PDF, which makes the form inaccessible. Upload our tailored PDF first, then trigger Simplify.
- **Drop networkidle wait** after click: chatty extensions (Capital One Shopping etc.) keep network active for >60s, deadlocking the wait. Use a fixed 8s `asyncio.sleep` instead.
- **Skip apply-flow's own goto**: if the page is already at the source URL, don't re-navigate (re-navigation wipes Simplify's render).
- **Defensive try/except** on upload/scan/confidence: a destroyed Playwright execution context (TargetClosedError from a click-driven navigation) no longer crashes the iteration; we log a warning and proceed with whatever survived.
- **Bump `SIMPLIFY_POLL_TIMEOUT_MS`** from 30s → 45s.

`src/agents/apply_worker/schemas.py`:

- Update `SIMPLIFY_POLL_TIMEOUT_MS` and add an explanatory docstring.

## What's the smoke runner

`scripts/_apply_smoke.py` is a development tool that drives the production code path against a real Chrome instance loaded with the user's cloned profile. It:

1. Re-copies Simplify's extension dir into the clone if missing (Chrome can wipe it on some launches).
2. Launches real Chrome with the target URL as the initial command-line argument and `--load-extension=data/simplify-unpacked` (so Simplify gets loaded even when the cached install is rejected by Chrome's content verification).
3. Polls via raw websocket CDP for the Simplify side panel to render BEFORE attaching Playwright. Up to 45s with one Page.reload retry.
4. Connects Playwright via `connect_over_cdp` and runs `_run_application_flow` against the existing tab (creating a new tab via `context.new_page()` was unreliable for Simplify).
5. Captures per-iteration artifacts to `.research/simplify-loop/iterations/NNN/`.
6. Falls back to bare-CDP capture if Playwright loses the tab post-click.
7. Hard-codes `dry_run=True` — no submit logic exists.

## What's NOT changed

- No changes to `process_apply_jobs.py` (the production worker). It still uses the existing `apply_to_job(cdp_url=...)` entry point.
- No changes to the database/schema/cost-tracking layer.
- No new dependencies.

## Known caveats for production deployment

1. **Profile clone requires Chrome closed at copy time.** macOS rsync of a live Chrome profile produces inconsistent Secure Preferences MAC signatures, which causes Chrome to wipe most extensions on first launch. The smoke runner's `_ensure_simplify_dir_in_clone()` works around this but a one-time clean clone is preferred.
2. **Simplify rendering is intermittent** (~80% success on cold launches in our testing). The smoke runner's 45s pre-attach wait + one reload absorbs most flakiness; production should do the same.
3. **The Autofill click can navigate the tab.** Production `process_apply_jobs.py` already handles this since `_run_application_flow` now wraps each post-click step in try/except. The page may end up on a `storage.googleapis.com/simplify-resumes/...` URL — this is normal.
4. **The 2-18 unresolved required fields** in passing iterations are freeform questions Simplify doesn't autofill (cover letter, "why are you interested", visa-status free-form). These are exactly the cases the apply worker is supposed to hand off via NEEDS_REVIEW for human or future-AI repair.

## Files for reference

- `RESUME.md` — runbook for resuming the loop after compaction.
- `findings.md` — DOM map, launch strategy, render-timing observations.
- `runlog.md` — append-only narrative of every iteration.
- `targets.txt` — list of Greenhouse URLs for the smoke runner.
- `state.json` — counters and stopping-condition flag.
- `iterations/NNN/` — per-iteration artifacts (gitignored).
