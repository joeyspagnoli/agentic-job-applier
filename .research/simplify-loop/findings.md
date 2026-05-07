# Simplify DOM Findings

Source: static analysis of `~/Library/Application Support/Google/Chrome/Default/Extensions/pbanhockgagggenencehbnadejlgchfc/2.4.6_0/js/contentScript.bundle.js` (Simplify Copilot v2.4.6, 1.7 MB minified).

## Shadow root

- Host element: `<div class="simplify-jobs-shadow-root">` appended to `document.body`.
- Attached via `t.attachShadow({mode:"open"})` — **mode is "open" so `host.shadowRoot` is reachable from page JS**.
- All Simplify UI (banner, autofill button, fill progress, etc.) lives inside this shadow root.

```js
// from contentScript.bundle.js (decompiled fragment):
t = document.createElement(e || "div");
t.className = "simplify-jobs-shadow-root";
const o = t.attachShadow({mode:"open"});
```

## Page-context script

- Sometimes injects a script element with id `simplify-jobs-page-script` (used for postMessage bridge between content script and page).

## Buttons (all live INSIDE shadow root, find by aria-label)

| aria-label | Purpose | Action |
|---|---|---|
| `Autofill` | Primary autofill trigger | **CLICK** |
| `Autofill all fields with AI` | AI variant when extension recognizes the form | **CLICK** if Autofill not visible |
| `Continue filling` | Proceeds to next page of multi-step app | **CLICK** to handle multi-step forms |
| `Fill` | Shorter label variant | **CLICK** as fallback |
| `Submit Application` | The actual submit | **NEVER CLICK** |
| `Fill progress view` | UI element to inspect fill progress | informational |
| `Add Application to Your History` | Post-submit tracking | n/a |

## Detection strategy

```js
// activation = shadow host present AND has shadowRoot
const host = document.querySelector('div.simplify-jobs-shadow-root');
const activated = !!(host && host.shadowRoot);
```

## Click strategy

```js
// must reach into the open shadow root
const host = document.querySelector('div.simplify-jobs-shadow-root');
if (!host || !host.shadowRoot) throw 'simplify not activated';
const root = host.shadowRoot;
// Try in priority order: Autofill > Autofill all fields with AI > Fill
const candidates = ['Autofill', 'Autofill all fields with AI', 'Fill'];
for (const label of candidates) {
  const btn = root.querySelector(`[aria-label="${label}"]`);
  if (btn) { btn.click(); break; }
}
```

## Submit safety

When scanning for buttons, always exclude any element whose aria-label or text contains "Submit". The runner should guard at the playwright level too — use a wrapper that refuses to click if aria-label matches `/submit/i`.

## VERIFIED working launch strategy (2026-05-07 02:34)

```bash
# 1. Quit user's main Chrome (cmd-Q) before cloning. The Default/Secure Preferences
#    file gets re-MAC'd while Chrome is running, so a live rsync produces an
#    inconsistent snapshot.
# 2. Clone the profile when Chrome is closed.
# 3. Stage Simplify's unpacked extension dir to a path OUTSIDE the user-data-dir.
# 4. Remove the Simplify entry from clone's Default/Extensions/ AND from
#    Default/Secure Preferences (entry + protection.macs entry). This avoids
#    Chrome's content-verification cache failing with `DidStartWorkerFail ... 5`.
# 5. Launch with --load-extension pointing at the staged unpacked dir.
#    Simplify's manifest has the `key` field so the extension ID stays
#    `pbanhockgagggenencehbnadejlgchfc` and Local Extension Settings (auth)
#    is picked up from the user-data-dir.

"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=<port> \
  --user-data-dir="$(pwd)/data/chrome-profile-clone" \
  --load-extension="$(pwd)/data/simplify-unpacked" \
  --no-first-run --no-default-browser-check
```

## Activation timing (measured on Anthropic Greenhouse)

- 0s after navigate: nothing
- ~5s: shadow root appears with "Resume score banner" only (initial state)
- ~10s: still settling
- ~15s: full UI rendered with **Autofill**, Tailor Resume, Save Job Instead, Settings, Minimize, Report an issue, Collapse Resume Section

**Loop should wait at least 15 seconds after navigation before scanning for the Autofill button.**

## Resolved questions

1. ✅ Activation time: ~15s for full UI on Greenhouse (5s for partial). Use 20s timeout to be safe.
2. ⏳ Auto-inject vs user click: appears to auto-inject (we never clicked anything and it appeared)
3. ⏳ Fill complete signal: not yet measured — TBD in the loop
4. ⏳ Whether Simplify uploads the resume itself: TBD — observe what happens after Autofill click
5. ⏳ Submit button location: not yet observed

## Critical: Simplify rendering is INTERMITTENT

Empirical observation across iterations 5-13 (2026-05-07 02:35-03:10):

**Simplify creates THREE `simplify-jobs-shadow-root` divs when it fully renders:**
- shadow#0: 4036 bytes, only "Resume score banner" aria-label (the inline banner)
- shadow#1: 27199 bytes — **THIS is the side panel with Autofill, Tailor Resume, Save Job Instead, Settings, Minimize, Close, Hide this message, Report an issue, Collapse Resume Section**
- shadow#2: 156 bytes (empty placeholder)

**My earlier `querySelector('div.simplify-jobs-shadow-root')` was finding shadow#0 only** (the banner) and reporting "Simplify activated but no Autofill button". Fixed in commit: now use `querySelectorAll` and walk each.

**Random failure rate: roughly 33%** of fresh Chrome launches with the same URL never render Simplify's UI at all (`shadow_host_count: 0` indefinitely, even after 45s + reload + 45s). On those failed runs, the SW is alive (visible in CDP target list) and the user is authenticated (`linkedCandidate` in storage, simplify.jobs cookies present), but the content script's React app doesn't mount the side panel.

**Possible causes (untested):**
- Rate limit: 800+ keys in chrome.storage suggest Simplify hit a quota/throttle on the simplify.jobs API after many test cycles.
- Job-specific: 5076929008 (Senior Payroll) showed banner-only at one point and 0 shadow roots later. 5023394008 (Anthropic Fellows) sometimes renders full UI, sometimes nothing.
- A/B test variant: banner says "SimplifyV1V2" — may indicate variant assignment.

**Implication for the loop:** The smoke runner cannot rely on Simplify rendering on every iteration. Strategy options:
1. Retry with reload until rendered (current behavior — doesn't always work)
2. Detect failure and skip to a different URL
3. Throttle iterations (e.g., 5+ minutes between runs to avoid rate limit)
4. Investigate Simplify's content script for the gating condition

**Discovered: Playwright connect_over_cdp does NOT prevent Simplify rendering when Simplify already rendered.** Earlier hypothesis disproven. Once shadow_root is mounted, attaching Playwright preserves it (verified probe count: 3, sizes [4036, 27199, 156] visible from Playwright too).

## Smoke runner architecture (current as of iteration 13)

1. Self-heal: remove Simplify from clone's `Default/Extensions/` and Secure Preferences entry.
2. Pick free TCP port.
3. Launch real Chrome (`/Applications/Google Chrome.app/.../Google Chrome`) with:
   - `--remote-debugging-port=<free port>`
   - `--user-data-dir=data/chrome-profile-clone`
   - `--load-extension=data/simplify-unpacked`
   - Initial URL = the target (so Chrome loads it before any automation attaches)
4. Wait for CDP `/json/version` to respond.
5. **Pre-attach Simplify wait** (raw websocket CDP, no Playwright): poll every 2s for shadow root + Autofill aria-label, up to 45s. If missing, `Page.reload`, poll again.
6. Connect Playwright via `connect_over_cdp`.
7. Pick the existing greenhouse tab via `context.pages` (don't create a new tab — Simplify won't inject in Playwright-spawned tabs).
8. Run `_run_application_flow(page=existing_page, ...)` — the apply flow now skips its own goto if URL already matches.
9. Capture artifacts (screenshots, shadow_dom_pre.html, shadow_dom_post.html, console.log, result.json).
10. Tear down Chrome.
