# search-003 — Simplify extension internals (publicly known)

## Sources
- `gh search code "pbanhockgagggenencehbnadejlgchfc"` — run 2026-05-22 (Simplify's CWS extension ID; the search surfaced ~20 repos that interact with or document the extension)
- `gh search code "simplify-jobs-shadow-root"` — run 2026-05-22 (returned the most useful single result: a complete saved HTML page showing the unpacked shadow DOM)
- https://raw.githubusercontent.com/ksrawr/auto_apply/main/chrome_extension/scripts/job.js — fetched raw 2026-05-22 (working open-source code that triggers Simplify autofill via shadow-DOM click)
- https://raw.githubusercontent.com/soumilbaldota/auto_filler/main/scripts/download-simplify.sh — fetched raw 2026-05-22 (script that downloads the Simplify CRX directly from CWS — the extension is publicly extractable)
- https://raw.githubusercontent.com/akshatvasisht/notiapply/main/.env.example — fetched raw 2026-05-22 (confirms extension version 2.4.1 was the pinned version mid-2025)
- https://github.com/SimplifyJobs — fetched 2026-05-22 (Simplify's org page — only 10 repos public, NONE are the Copilot extension source)
- https://github.com/SimplifyJobs/extension-take-home — fetched 2026-05-22 (their hiring assignment reveals the architecture style: TypeScript + React + XPath element detection + JSON config)
- https://github.com/SimplifyJobs/webpack-ext-reloader — fetched 2026-05-22 (MIT-licensed webpack hot-reload tooling for extensions — confirms they use webpack)
- Search results for "contentScript.bundle.js simplify" — confirmed the bundle filenames

## Thesis
The Copilot extension is **not** open source, but it is **trivially extractable** (the CRX is a public artifact downloadable from `clients2.google.com/service/update2`), and its **DOM contract is fully observable**. We have:
- The exact CRX-download URL pattern (reproducible from the extension ID)
- The internal file structure (assets URLs visible in third-party saved HTML)
- The element ID that triggers autofill (`fill-button` inside the open shadow root of `.simplify-jobs-shadow-root` / `#simplify-jobs-container`)
- The injected page script path (`chrome-extension://<extId>/js/pageScript.bundle.js`)
- The content-script bundle name (`contentScript.bundle.js`)
- The CSS path (`chrome-extension://<extId>/css/styles.css`)
- The framework choice (TypeScript + React, per the take-home; webpack-bundled)
- Their detection strategy (XPath-first, per the take-home)

**There is no documented postMessage API, no publicly-known custom DOM event bus, and no public Simplify HTTP API for autofill.** The shadow-root button click IS the API. That's a fragile contract (no version stability promise) but it has survived at least the v2.4.1 → v2.5.0 jump.

---

## 1. Extension distribution — public CRX

Verbatim from `soumilbaldota/auto_filler/scripts/download-simplify.sh`:
```bash
EXTENSION_ID="pbanhockgagggenencehbnadejlgchfc"
EXTENSION_DIR="/app/extensions/simplify"
TEMP_FILE="/tmp/simplify.crx"

curl -L -o "$TEMP_FILE" \
  "https://clients2.google.com/service/update2/crx?response=redirect&prodversion=120.0.0.0&acceptformat=crx2,crx3&x=id%3D${EXTENSION_ID}%26uc"
```

The script also handles CRX3 stripping (12-byte magic + variable header) and unpacks to a directory. **Implication:** we can pin a known-good Simplify version into our pipeline's extension load path, get version stability, and only upgrade after our own smoke test. We do not depend on whatever auto-update Chrome pulled.

## 2. File structure (from third-party saved HTML pages on GitHub)

Multiple captured pages on GitHub show what the extension injects into a host page:

From `udishkumar/udishkumar.github.io/u1d2i4s0h8.html` and `NotRichieNguyen/business-website/src/images/localhost.htm` and `cgandotr/MoCode/src/extra/profile.html`:

```html
<div id="simplifyJobsContainer" style="position: fixed; ...">
  <span>
    <template shadowrootmode="open">
      <link rel="stylesheet" href="chrome-extension://pbanhockgagggenencehbnadejlgchfc/css/styles.css">
      <!-- panel UI here -->
      <div id="simplifyJobsPortals"></div>
    </template>
  </span>
</div>
<script id="simplify-jobs-page-script"
        src="chrome-extension://pbanhockgagggenencehbnadejlgchfc/js/pageScript.bundle.js"></script>
```

And a slightly older variant (from `SCharank/charan/index.html`):
```html
<script id="simplify-jobs-page-script"
        src="chrome-extension://pbanhockgagggenencehbnadejlgchfc/js/pageScript.bundle.js"></script>
```

Two observations:
- The host element ID has changed over versions (`simplifyJobsContainer` in older saves, `simplify-jobs-container` in newer; the shadow-root class `.simplify-jobs-shadow-root` is the stable selector both old and new code uses).
- The page-script ID is also stable: `simplify-jobs-page-script` (`id` attribute).
- The shadow root is **opened with `shadowrootmode="open"`** — meaning content scripts and page scripts can both pierce it without the closed-shadow-root API. This is what our pipeline relies on.

A fragment from `botswin/FakeVision-Privacy-Research/1.8.8/detections/chromeExtension.js` is interesting too: it lists the Simplify extension ID in a privacy-fingerprinting detector. Means privacy researchers can fingerprint the extension on a page by checking for `#simplify-jobs-container` and the page-script `<script>` tag — also means anti-bot defenses on careers pages could potentially detect Simplify the same way.

There's also a reference to a missing asset: `chrome-extension://pbanhockgagggenencehbnadejlgchfc/assets/userReportLinkedCandidate.json` (from `noopta/personal_ai_assistant_fe`'s pasted log: `GET ... net::ERR_FILE_NOT_FOUND`) — implies the extension at some point referenced a JSON file that was removed in a later version. Not load-bearing for us; just a signal that file paths churn.

## 3. The autofill trigger (verbatim working code)

From `ksrawr/auto_apply/chrome_extension/scripts/job.js` (raw fetched 2026-05-22):

```javascript
const main = async() => {
    try {
        const simplifyNodes = await getNode('.simplify-jobs-shadow-root', 'query-all') || [];
        const shadowNode = simplifyNodes.length > 0
            ? simplifyNodes[simplifyNodes.length - 1].shadowRoot
            : undefined;
        if(!shadowNode) return { status: "Failed", message: "Shadow node undefined"};

        const autoFillBtn = await getNodeV2(shadowNode, 'fill-button', 'id');
        if(!autoFillBtn) return { status: "Failed", message: "Fill Button undefined"};

        autoFillBtn.click();

        await delay(8000);
        return { status: "AUTOFILLED", message: "Fields autofilled"};
    } catch(e) {
        return { status: "ERROR", message: "Something went wrong while applying", e };
    }
};
```

**This is the working pattern, identical to what our `src/agents/apply_worker/browser.py` does.** Key facts confirmed:

| Fact | Value |
| --- | --- |
| Outer host selector | `.simplify-jobs-shadow-root` (class) |
| Shadow mode | open (so `.shadowRoot` is reachable from content/page scripts) |
| Element ID inside shadow | `fill-button` |
| Trigger | `.click()` synthetic event |
| Wait time after click | 8 seconds in ksrawr's code (we use ~15s in our pipeline; matches) |
| Multi-host case | "use the last node" — there can be multiple `.simplify-jobs-shadow-root` instances on a page; the last one is the active panel |

This code is **2+ years old** (ksrawr/auto_apply hasn't been actively maintained) and still works on Simplify v2.5.0. That's a useful longevity signal — the shadow-root contract has been stable for years.

## 4. The submit trigger (in the same file)

```javascript
const submit = async() => {
    const submitBtn = await getNode('submit_app', 'id');
    submitBtn.click();
    ...
};
```

Note: `submit_app` is the application's own submit button ID on certain ATSes (probably Greenhouse — it ships with that ID). This is the application-form submit, NOT a Simplify submit. Simplify does not have a submit button (per fetch-002 — they don't auto-submit). Our pipeline correctly refuses to click this.

## 5. Architecture (inferred from take-home + bundle names + webpack repo)

- **Language:** TypeScript
- **UI framework:** React
- **Bundler:** webpack (confirmed by SimplifyJobs/webpack-ext-reloader being MIT'd by them, and by the `*.bundle.js` filenames)
- **Element detection:** XPath-first, with JSON config per site (per the extension-take-home: "Use XPaths to find the relevant elements" + bonus JSON config section)
- **Per-site mapping:** there is a per-site / per-template mapping layer; new sites require manual addition (per help.simplify.jobs article 20 — "Request New Autofill Support")
- **AI layer:** "Autofill all fields with AI" toggle (free tier) + premium AI for cover letters and custom questions (Simplify+); this layer almost certainly calls api.simplify.jobs as a backend AI proxy (Simplify's profile and resume parser already require server-side processing for the Simplify+ tier)

## 6. Backend endpoints (publicly observable)

The only documented domain is `api.simplify.jobs` (referenced in the marketing site as the backend). Specific endpoints not enumerated in any public source we found. The extension:
- Logs in via `simplify.jobs` cookies (per Firefox reviews mentioning "extension can't connect to my profile" — suggests session-cookie-based auth, not OAuth)
- Syncs profile data with the backend (per onboarding flow)
- AI-fill answers are almost certainly server-side (the extension is 8.6 MiB unpacked — too small to ship a model; the AI must round-trip)

**Implication:** there is no documented HTTP endpoint we can hit to get autofill values without using the extension. If we wanted to bypass Simplify entirely but reuse their AI-fill engine, we'd be reverse-engineering authenticated endpoints — fragile, fragile, fragile.

## 7. postMessage / DOM event surface

Searched for `"simplify-jobs"` + `postMessage` and found nothing concrete in public code. Simplify's content script likely uses `window.postMessage` internally between page-script and content-script (standard MV3 pattern, confirmed by the existence of `pageScript.bundle.js` as a separately injected page-context script), but **no public documentation or third-party code shows an external API**.

**Verdict:** there is no programmatic-trigger API. Clicking the shadow-root button is the only entry point. That's what we already do. There is no faster / more reliable replacement.

## 8. Web-accessible resources

The CRX manifest declares at least these as web-accessible (visible because they're referenced via `chrome-extension://<id>/...` URLs in the injected DOM):
- `css/styles.css`
- `js/pageScript.bundle.js`
- `assets/logos/icon.png`
- `assets/userReportLinkedCandidate.json` (was, may have been removed)

These are the only resources third-party pages can reach. The content script (`contentScript.bundle.js`) is NOT web-accessible — only the extension can load it.

## 9. Manifest version + permissions (inferred)

- Manifest V3 (any recent Chrome extension is forced to MV3 by Chrome Web Store)
- Host permissions: broad (matches "all major ATSs" claim — likely `<all_urls>` or a large `matches` list spanning every supported career-page domain)
- Permissions almost certainly: `storage` (chrome.storage for profile), `tabs`, `cookies` (for cross-origin auth to simplify.jobs)

Exact manifest content NOT extracted (we didn't run download-simplify.sh in this pass — could be done as follow-up by literally curling the CRX and unzipping; ~1 minute of work).

## 10. Reverse-engineering risk

The extension is fully obfuscated by webpack production bundling (minified, mangled symbols). Source maps are not shipped (we'd see `.map` files in the asset references if they were). The visible identifiers like `fill-button`, `simplify-jobs-container`, `simplifyJobsPortals` ARE preserved because they're DOM IDs (must be stable for the extension's own runtime to find them).

**Bottom line:** the only stable contract Simplify exposes externally is:
1. `.simplify-jobs-shadow-root` host (open mode)
2. `#fill-button` inside the shadow root
3. The injected `<script id="simplify-jobs-page-script">` element (for detection)
4. The CSS file at `chrome-extension://<id>/css/styles.css`

These have survived at least 2 years of releases (ksrawr's code from ~2 years ago still matches v2.5.0). That's good enough to depend on, with a per-version smoke test.
