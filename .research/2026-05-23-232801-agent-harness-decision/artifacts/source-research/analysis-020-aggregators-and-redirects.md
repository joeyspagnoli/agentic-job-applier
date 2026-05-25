# analysis-020-aggregators-and-redirects.md
## Aggregator Sources: Redirects, Anti-Bot, and Apply Routing

**Scope**: JobSpy (Indeed, Glassdoor), Adzuna, TheMuse, Remotive, Working Nomads, Himalayas, Startup Jobs.

---

## 1. Per-Aggregator Landing-URL Semantics and Redirect Chain

### Indeed (via JobSpy)
`source_url` = `indeed.com/viewjob?jk=<hash>` or `indeed.com/rc/clk?jk=<hash>`.

The listing page presents **two apply paths in the same view**:
- **Indeed Apply**: a modal form hosted by Indeed. The current page stays loaded; a modal/overlay renders the application form. No new tab.
- **Apply on company site**: `<a target="_blank">` or `window.open()` spawns a new browser tab pointing to the company's ATS (Greenhouse, Workday, Lever, iCIMS, Taleo, SmartRecruiters, or a bespoke careers page).

There is no redirect between the listing page and these two modes — both resolve from the same `viewjob` URL. One hop from `source_url` to the apply interface.

### Glassdoor (via JobSpy)
`source_url` = `glassdoor.com/job-listing/<slug>?jl=<id>`.

Same two-path structure as Indeed:
- **Glassdoor Easy Apply** (listings with "Easy Apply" badge): Glassdoor-hosted modal form. No new tab.
- **Apply on employer site**: new tab to company ATS.

Glassdoor does NOT redirect through LinkedIn. Glassdoor applies go to company ATS or Glassdoor's own form. The listing page is the single hop before apply.

### Adzuna
`source_url` = `adzuna.com/land/ad/<id>` — a **tracked redirect URL**.

On navigation, Adzuna issues an HTTP 302 to the actual destination, which can be:
- Company ATS directly (Greenhouse, Lever, Workday) — 1 hop total, ideal
- Another aggregator listing (Indeed, LinkedIn, SimplyHired) — worker lands on aggregator listing page and must click Apply there — 2 hops
- Company's generic careers page — requires finding the specific role — variable hops

The `httpx` liveness_checker with `follow_redirects=True` follows the Adzuna redirect and checks the final URL. However a liveness ACTIVE result on an Indeed listing page is a **false-active** — the listing exists, but the worker will still need to click Apply on that page.

### TheMuse
`source_url` = `themuse.com/jobs/<company>/<role-slug>` — TheMuse's own landing/branding page.

This is always a 1-hop situation but the landing page has no form. The worker must click "Apply Now" to reach the ATS.

TheMuse documentation explicitly states: "When a candidate clicks Apply Now, they'll be redirected from your profile to your external ATS." There is no TheMuse-native apply form.

TheMuse's "Apply Now" behavior is inconsistent: some listings use same-tab navigation; others use `target="_blank"` new-tab spawn.

### Remotive
`source_url` = `remotive.com/remote-jobs/<category>/<role-slug>` — Remotive's own listing page.

Remotive listing page links to the company's application URL. The apply button opens the company's ATS (new tab or same-tab). Remotive manually curates listings, so dead URL rate is lower than most aggregators (~2–5%).

### Working Nomads
`source_url` = the `url` field from the API — typically a **direct link** to the company's application page or ATS. One of the cleanest URL types: often lands directly at the ATS with no intermediate aggregator step.

### Himalayas
`source_url` = either `himalayas.app/companies/<companySlug>/jobs/<slug>` (Himalayas listing page) or `applicationUrl` (direct ATS link), depending on which fields are present in the API response. The fetcher prefers the constructed Himalayas URL; falls back to `applicationUrl`.

When `source_url` is a Himalayas page, the worker must click "Apply" to reach the external ATS. When it is `applicationUrl`, it goes directly to the ATS.

### Startup Jobs
`source_url` = `url` or `apply_url` field — typically direct links to the company's apply page or ATS. Similar to Working Nomads: direct ATS URLs, no intermediate aggregator step.

---

## 2. The "Apply on Company Site" Tab-Spawn Problem

**This is the single most critical structural issue for aggregator sources.**

Indeed, Glassdoor, TheMuse, and sometimes Adzuna all have an intermediate aggregator page before the ATS. When the worker clicks "Apply on company site" or "Apply Now," the browser spawns a **new tab** via `window.open()` or `<a target="_blank">`.

The current `browser.py` does **not register a `context.on('page', ...)` listener**. After the click, the worker's `page` object still references the aggregator listing page, not the new ATS tab. The worker will find no form fields, time out, and fail.

This is the same problem previously identified for LinkedIn. The fix is identical: register `context.on('page', handler)` BEFORE clicking Apply, then switch to the new tab if it appears within ~5 seconds, or detect same-tab navigation otherwise.

Real-world projects (`cucia/job-sentinel`, `KhaoulaMaleh/MobileCVMind`) universally implement this pattern. It is not optional for aggregator sources.

---

## 3. Cloudflare / Anti-Bot Detection

### Verdict: LOW RISK for Our Specific Architecture

Standard headless Playwright fails Cloudflare because of headless flag detection, fingerprint mismatch (canvas, WebGL, fonts), and cold session (no cookies). Our worker inverts all three risk factors:

- **Headed Chrome** — `navigator.webdriver` behavior, canvas fingerprint, font enumeration match the user's real daily browser
- **User's real Chrome binary** — not Playwright's bundled Chromium, which has a distinct build fingerprint known to Cloudflare
- **Pre-authenticated sessions** — Indeed, Glassdoor, LinkedIn cookies are already present; Cloudflare's JS challenge evaluates the user's established trust score

| Site | Bot Protection | Risk with Headed Chrome + Cookies |
|------|---------------|-----------------------------------|
| Indeed | Cloudflare medium | LOW — logged-in session passes CF trust |
| Glassdoor | Cloudflare + PerimeterX | LOW-MEDIUM — PX analyzes mouse movement |
| ZipRecruiter | Rate limiting only | VERY LOW |
| TheMuse | None significant | VERY LOW |
| Adzuna | None on redirect | VERY LOW |
| ATS destinations | Minimal | VERY LOW |

**Remaining risks:**
1. Navigation speed: visiting >3 Indeed/Glassdoor pages in <30 seconds triggers behavioral analysis. Enforce 3–5 second minimum gaps.
2. Glassdoor PerimeterX: use randomized `page.mouse.move()` before clicking Apply.
3. Docker/VPN IP issue: Mac host→container shows as 172.66.0.243. If Glassdoor/Indeed have IP-based session correlation, Docker-hosted workers may trigger soft blocks. Running browser automation on the host (not in Docker) is recommended.
4. CAPTCHA fallthrough: ~1–3% of sessions will hit CAPTCHA regardless → NEEDS_REVIEW.

---

## 4. Indeed Apply vs. Company-Site Apply Preference

**Prefer "Apply on company site" when available.**

Indeed Apply has documented delivery failures when the employer's Indeed integration is misconfigured — applications submitted but never reach the ATS. "Apply on company site" goes directly to the ATS with guaranteed delivery. The ATS surface is also the same surface our direct-ATS fetchers already handle.

Use Indeed Apply only when "Apply on company site" is not available (employer has configured only Indeed Apply mode).

Detection: check for `.jobsearch-IndeedApplyButton`, `#indeedApplyButton`, or `[data-testid*="indeedApplyButton"]` (indicates Indeed Apply mode) vs. text "Apply on company site" or `[data-testid*="desktop-apply-button"]` with an external href.

---

## 5. Dead Source URL Failure Mode

### Estimated Dead URL Rates

| Source | Estimated Dead URL Rate | Primary Signal |
|--------|------------------------|----------------|
| Indeed (72h window via JobSpy) | ~3–5% | "this job is no longer available" |
| Glassdoor (72h window via JobSpy) | ~5–8% | "Job Not Found" |
| Adzuna (no age filter) | ~8–15% at destination | 404 or "position filled" |
| TheMuse | ~5–10% at ATS (landing page stays live) | ATS 404 post-click |
| Remotive (curated) | ~2–5% | Listing removed |
| Working Nomads | ~5–10% | Direct link goes stale |
| Himalayas | ~5–8% | ATS link stale |
| Startup Jobs | ~5–10% | Direct ATS link stale |

JobSpy's `hours_old=72` (hardcoded in `jobspy_fetcher.py`) significantly reduces stale URLs for Indeed and Glassdoor. API-based fetchers without age filters (Adzuna, Remotive, Himalayas) accumulate more stale listings.

**The TheMuse false-active problem** is structurally unique: the landing page at `source_url` is ACTIVE (returns 200, has an Apply button), but the ATS URL behind "Apply Now" may be 404. The liveness_checker cannot see through the intermediate page to the ATS URL. This costs one navigation before the 404 is discovered.

---

## 6. Recommended First Action Per Aggregator

| Aggregator | `source_url` Type | First Action |
|------------|------------------|-------------|
| **Indeed** | Indeed listing page | Detect apply mode → prefer "Apply on company site" → intercept new tab → ride ATS flow |
| **Glassdoor** | Glassdoor listing page | Detect "Easy Apply" badge → prefer employer site → intercept new tab |
| **Adzuna** | Tracked redirect (302) | Navigate → httpx liveness check follows redirect → if final URL is another aggregator listing, click Apply there → if ATS, fill directly |
| **TheMuse** | TheMuse landing page | Navigate → click "Apply Now" → intercept new tab OR same-tab → verify ATS URL loads (check for 404 before proceeding) |
| **Remotive** | Remotive listing page | Navigate → find "Apply for this job" link → click → intercept ATS |
| **Working Nomads** | Direct external URL | Navigate directly to ATS → fill form |
| **Himalayas** | Himalayas page OR direct ATS URL | If Himalayas page: click Apply → intercept. If `applicationUrl`: navigate directly |
| **Startup Jobs** | Direct ATS URL | Navigate directly → fill form |

---

## 7. Does `liveness_checker.py` Catch Dead URLs Upstream?

**Partially — with three important gaps.**

### What It Catches (correctly)
- HTTP 404/410 → EXPIRED
- Text patterns: "this job is no longer available", "no longer accepting applications", "position has been filled", "job not found" → EXPIRED
- Redirect to `?error=true` URL → EXPIRED
- Apply button present → ACTIVE

### What It Misses
1. **TheMuse false-actives**: Landing page returns 200 with Apply button → liveness checker says ACTIVE, but the ATS URL behind the button is 404. ~30–40% of TheMuse "dead" listings would show as ACTIVE.
2. **Adzuna second-hop**: Adzuna redirects to an Indeed/LinkedIn listing page. liveness checker sees that listing (200, has apply buttons) → ACTIVE. But the subsequent company-site apply from that listing may be to a dead ATS URL.
3. **JavaScript-rendered "position closed"**: Taleo, iCIMS, BrassRing can show the job page with all standard HTML but render "this position is closed" in a dynamic div. httpx doesn't execute JavaScript, so the body pattern match misses this. These show as UNCERTAIN (no apply button found in raw HTML).

### Coverage Summary
The liveness_checker is highly effective for direct ATS sources (Greenhouse, Lever, Workday). For aggregator sources with intermediate pages (TheMuse, Adzuna), it provides a first-line filter that eliminates the ~50% of definitively dead URLs (hard 404s, explicit expiry text) but misses the structural false-active cases. The worker should do a secondary liveness check AFTER clicking through to the ATS URL, especially for TheMuse.

---

## Per-Aggregator Routing Recommendation

| Aggregator | Preferred Apply Button | Fallback |
|------------|----------------------|---------|
| Indeed | "Apply on company site" → new-tab ATS | Indeed Apply modal if company-site unavailable |
| Glassdoor | "Apply on employer site" → new-tab ATS | Glassdoor Easy Apply if no employer-site option |
| Adzuna | Follow redirect → handle ATS or second-hop listing | NEEDS_REVIEW if destination ambiguous |
| TheMuse | "Apply Now" → intercept new tab or same-tab ATS | NEEDS_REVIEW if ATS returns 404 |
| Remotive | "Apply for this job" → company ATS | NEEDS_REVIEW |
| Working Nomads | Direct to ATS | NEEDS_REVIEW |
| Himalayas | Himalayas page: click Apply. Direct URL: navigate. | NEEDS_REVIEW |
| Startup Jobs | Direct apply_url to ATS | NEEDS_REVIEW |

---

## Failure-Handling Table

| Failure Mode | Aggregators Affected | Detection Method | Response |
|-------------|---------------------|-----------------|---------|
| 404 / HTTP error at source_url | All | liveness_checker HTTP status | Skip (FILTERED_OUT before apply) |
| "No longer available" text | Indeed, Glassdoor | liveness_checker EXPIRED_PATTERNS | Skip |
| TheMuse landing page live, ATS 404 | TheMuse | Worker detects 404 after "Apply Now" click | NEEDS_REVIEW |
| Adzuna → second-hop aggregator | Adzuna (~15–25%) | URL pattern detection after redirect | Worker clicks Apply on second-hop listing |
| CAPTCHA / bot detection | Indeed, Glassdoor | Worker detects CAPTCHA selector | NEEDS_REVIEW |
| Login gate (no session) | Indeed Apply, Glassdoor Easy Apply | Worker detects login form instead of apply form | NEEDS_REVIEW |
| New tab not intercepted | Indeed, Glassdoor, TheMuse, Remotive | No form fields found on current page | Add context.on('page') listener — CRITICAL GAP |
| Company ATS requires account creation | iCIMS, Taleo, BrassRing | "Create profile" wall detected | NEEDS_REVIEW |
| JS-rendered "position closed" | iCIMS, Taleo | No Apply button after JS load | NEEDS_REVIEW (no Apply button found) |
| Screener questions not filled by Simplify | Indeed Apply, ZipRecruiter | Unfilled required fields detected | AI completion + NEEDS_REVIEW for review |

---

## Critical Implementation Gap

`browser.py` has no `context.on('page', ...)` listener (confirmed: only `new_page()` call is on line 199 for the initial tab). Every "Apply on company site" click from Indeed, Glassdoor, and TheMuse listings will silently fail — the worker points at the aggregator listing page while the ATS tab opens unattended in the background.

This is the first structural fix required before aggregator sources can be processed reliably.
