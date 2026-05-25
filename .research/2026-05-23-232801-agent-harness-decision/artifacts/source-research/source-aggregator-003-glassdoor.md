# source-aggregator-003-glassdoor.md
## Glassdoor Apply: Redirect Behavior

### What `source_url` Resolves To (JobSpy/Glassdoor)
JobSpy scrapes Glassdoor. The `job_url` from Glassdoor is of the form:
- `https://www.glassdoor.com/job-listing/<slug>?jl=<id>` — Glassdoor's canonical listing page

### Apply Button Behavior on Glassdoor
Glassdoor's "Easy Apply" vs "Apply on employer site" mirrors the Indeed pattern:

1. **Glassdoor Easy Apply**: Glassdoor hosts a minimal form (name, email, resume upload, optional cover letter). Some listings use this path. Simplify can autofill these standard fields.
2. **Apply on employer site**: Most Glassdoor listings redirect to the company's ATS (the same Greenhouse/Lever/Workday destinations as from Indeed). This redirect is a `window.open` or link that opens a new tab.

### Glassdoor Redirect Chain
`glassdoor.com/job-listing?jl=...` → user clicks "Apply" → 
- Path A: Glassdoor Easy Apply modal (no new tab)
- Path B: New tab opens to `jobs.lever.co/company/role` or `company.greenhouse.io/jobs/...` etc.

Glassdoor does NOT typically redirect through LinkedIn. Glassdoor IS a separate entity now (acquired by Recruit Holdings), though older references suggested LinkedIn partnership discussions. In practice, Glassdoor apply buttons go to the company ATS directly.

### Does Glassdoor Serve Its Own Apply Form?
Yes, Glassdoor Easy Apply is a real form hosted by Glassdoor. However it is less common than "Apply on employer site." The distinguishing feature in the UI is:
- "Easy Apply" badge on the listing card = Glassdoor-hosted form
- No badge = employer site redirect

Glassdoor does not have its own ATS infrastructure — Easy Apply submissions are forwarded to the employer via email or ATS integration (similar to Indeed Apply).

### Anti-Bot / Cloudflare on Glassdoor
Glassdoor has active bot protection. Direct Playwright navigation to Glassdoor listing pages triggers Cloudflare/PerimeterX challenges in headless mode. However:
- The worker uses the **user's real Chrome with their existing Glassdoor session cookies** — this bypasses Cloudflare's fingerprinting for most cases
- JobSpy scrapes Glassdoor at fetch time (not at apply time), so the worker only navigates to the listing once, with real browser + session

### Dead URL Rate
Glassdoor listings expire but the listing page typically shows "This job is no longer available" rather than 404. The liveness_checker EXPIRED_PATTERNS cover "no longer available" — so Glassdoor expired listings are caught upstream.

### Sources
- Glassdoor Help Center: resume upload docs confirm Easy Apply modal exists
- Web search: "How to use LinkedIn, Glassdoor, Wellfound to find tech jobs" — confirms Glassdoor redirects to external sites
- job-search-tools GitHub aggregator overview
