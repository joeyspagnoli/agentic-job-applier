# source-aggregator-001-indeed.md
## Indeed Apply: Two Paths, One Source

### What `source_url` resolves to
JobSpy's `job_url` for Indeed takes one of two forms:
- `https://www.indeed.com/rc/clk?jk=<hash>` — a redirect through Indeed's click-tracker that lands at either the Indeed Apply overlay or a company site redirect page
- `https://www.indeed.com/viewjob?jk=<hash>` — the canonical listing page that shows both apply options side-by-side

### The Two Apply Modes
1. **Indeed Apply** ("Apply with your Indeed resume") — Indeed hosts the entire form in a modal/overlay. Fields are Indeed's own (name, email, resume upload, screener questions). No ATS behind it; Indeed forwards the application. Simplify **does** fire on these overlays because they render standard HTML inputs.
2. **Apply on company site** — clicking the button opens a new tab/popup to the employer's ATS URL (Greenhouse, Workday, Taleo, etc.). Indeed's listing page stays open. The new tab IS where the actual application lives.

### Tab-Spawn Behavior
"Apply on company site" uses `window.open` or `<a target="_blank">`. This spawns a second tab (or popup context) in the attached Chrome instance. The worker's `page` reference is still pointing at the Indeed listing, not the new ATS tab. This is the same problem as LinkedIn's "Apply on company site" — the worker needs to intercept the new page event (`context.on('page', ...)`) or switch the active tab after click.

### Indeed Apply (modal) — Simplify Coverage
Simplify fires its autofill overlay on Indeed's in-page application form. Community reports confirm it covers name, email, phone, work experience, education on Indeed Apply modals. However, Indeed screener questions (employer-defined custom questions like "Do you have a security clearance?") are NOT filled by Simplify — these are dynamic and unstructured.

### Known Indeed-Specific Issues
- **Session required**: Indeed Apply requires the user to be logged into Indeed. Without session cookies, the apply modal shows a login gate. The worker attaches to the user's real Chrome with their cookies, so this is generally handled — but if the session is stale, the modal shows a login screen instead of the form.
- **CAPTCHA on navigation**: Direct navigation to `indeed.com/viewjob?jk=...` from a non-logged-in state or bot-pattern session frequently triggers a "Just a moment..." Cloudflare check or an Indeed CAPTCHA wall. The user's real Chrome with cookies avoids most of these.
- **Indeed Apply toggle**: Some employers enable both Indeed Apply AND company-site apply simultaneously. The UI shows two buttons. Others use only one mode. The `job_url` field does not indicate which mode is active.
- **Ghost applications**: Community reports note Indeed Apply submissions sometimes do not reach the employer's ATS if the employer integration is broken. For high-signal roles, "Apply on company site" is more reliable delivery.

### Sources
- YouTube: "Indeed Apply VS Apply On Company Site" (employer hiring perspective)
- Reddit/careers: consensus is company-site apply reaches ATS more reliably
- job-sentinel GitHub `src/platforms/indeed/apply.py` — uses selectors `.jobsearch-IndeedApplyButton` and `#indeedApplyButton` to detect Indeed Apply vs company-site
