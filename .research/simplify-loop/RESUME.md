# Simplify Apply-Worker Feedback Loop — RESUME

If you're reading this after a context compaction, this file tells you exactly where the loop is and how to continue. Read it top to bottom before doing anything.

## Mission

Iterate on `src/agents/apply_worker/browser.py` (and helpers in the same package) until the apply worker reliably executes the full Simplify-driven application flow against real Greenhouse job pages — **stopping strictly before any submit click**. The user is asleep; keep iterating autonomously until end-to-end is solid.

## The hard rule

**NEVER click submit.** No code path in this loop should ever produce a SUBMITTED outcome or click any button whose text/aria-label matches "Submit Application", "Submit", "Apply Now", or similar. The flow ends at "form filled, resume uploaded, screenshot captured." If you find yourself adding submit logic, stop and ask the user.

## Where you are

- State of progress: read `runlog.md` in this directory (append-only narrative; latest entry at bottom).
- Per-iteration artifacts: `iterations/NNN/` — `screenshot.png`, `dom.html`, `shadow_dom.html`, `console.log`, `result.json`.
- Current best-known selectors and findings: `findings.md`.
- Target URLs: `targets.txt`.

## Reconnaissance that's already done

- Simplify Copilot extension version 2.4.6 is installed in the user's main Chrome profile at extension ID `pbanhockgagggenencehbnadejlgchfc`.
- Profile cloned to `data/chrome-profile-clone/` (~3.5 GB) **while user's Chrome was closed** (live-clone produces inconsistent Secure Preferences MACs).
- Simplify staged at `data/simplify-unpacked/` (separate path) and **removed from clone's `Default/Extensions/`** plus its entry stripped from `Default/Secure Preferences` (settings + protection.macs). This is needed because Chrome's content-verification cache fails the SW with `DidStartWorkerFail: 5` if loaded from the cloned Default/Extensions path.
- **VERIFIED working** (2026-05-07 02:34): with `--load-extension=data/simplify-unpacked`, Simplify's service worker starts and content script injects the shadow root within ~15s on a Greenhouse application page. Visible aria-labels included **Autofill**, Tailor Resume, Save Job Instead.
- Real DOM markers (extracted from the content script bundle, NOT speculative):
  - **Shadow host element**: `<div class="simplify-jobs-shadow-root">` attached to body via `attachShadow({mode:"open"})` — `.shadowRoot` IS accessible from page context.
  - **Buttons inside the shadow DOM** (find by aria-label):
    - `aria-label="Autofill"` — primary autofill button (CONFIRMED visible after 15s)
    - `aria-label="Autofill all fields with AI"` — AI variant
    - `aria-label="Continue filling"` — multi-page proceed
    - `aria-label="Fill"` — short label variant
    - `aria-label="Submit Application"` — **DO NOT CLICK**
- `[class*="simplify" i]` selectors in current `browser.py` will fail because they don't pierce shadow DOM. That's the first thing to fix in iteration 1.

## How to run one iteration

```bash
cd /Users/jspags/Projects/agentic-job-applier
uv run python -m scripts._apply_smoke --target-index 0
```

`--target-index N` picks the Nth URL from `targets.txt` (0-indexed; rotate through them).

The runner:
1. Launches real Chrome (channel="chrome") with the cloned profile via `playwright.chromium.launch_persistent_context`.
2. Opens the target URL in a new page.
3. Calls `src.agents.apply_worker.browser.apply_to_job(...)` with `dry_run=True` (the runner doesn't even expose `dry_run=False` — defense in depth).
4. Writes artifacts to `.research/simplify-loop/iterations/NNN/`.
5. Appends one line to `runlog.md`.
6. Closes Chrome.

## How to iterate

After each smoke run:
1. `cat .research/simplify-loop/iterations/NNN/result.json` — overall pass/fail and what stage broke.
2. Open `screenshot.png` — visually confirm whether autofill happened and resume is attached.
3. Look at `shadow_dom.html` — what's actually inside the Simplify shadow root.
4. Edit `src/agents/apply_worker/*.py` to fix whatever broke.
5. Run again with the next target index, or the same one.

## Stopping condition

End the loop when 3 consecutive runs against 3 different target URLs all produce:
- `simplify_activated: true`
- `autofill_triggered: true`
- `resume_uploaded: true`
- `unresolved_required_count: 0`
- `screenshot_path` set

Then tell the user. Do NOT keep grinding past 30 total iterations — if you're not converging, write a status report and stop.

## What to update as you go

- `runlog.md` — one entry per iteration, what changed and why.
- `findings.md` — keep it up-to-date with current best-known selectors/timing knobs/quirks.
- `state.json` — counters and current target index.

## Hard guardrails

- Never modify `data/chrome-profile-clone/` outside of letting Chrome run against it.
- Never run with `dry_run=False`.
- Never call `page.click(...)` against a Submit-Application button.
- If you encounter a CAPTCHA or login wall, screenshot it, log it, move to next target.
- If Chrome refuses to launch because the user has reopened their main Chrome with the same profile clone, just stop — don't fight it.
