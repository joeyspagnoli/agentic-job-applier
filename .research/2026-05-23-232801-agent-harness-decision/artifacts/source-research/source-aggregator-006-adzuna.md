# source-aggregator-006-adzuna.md
## Adzuna: Redirect Chain and Source URL Semantics

### What `source_url` Resolves To
The Adzuna fetcher uses `redirect_url` from the API response. This is Adzuna's own redirect URL:
`https://www.adzuna.com/land/ad/<id>?...`

Adzuna's `redirect_url` is a **tracked redirect**. When navigated to, it:
1. Logs a click event on Adzuna's side
2. Issues an HTTP 302 to the actual source — which can be ANY of:
   - The company's ATS directly (Greenhouse, Workday, Lever, iCIMS)
   - Another aggregator (Indeed, LinkedIn, ZipRecruiter, SimplyHired)
   - A job board's listing page (not direct ATS)
   - The company's own careers page

### Redirect Chain Depth
Adzuna's redirect chain is typically 1–2 hops:
- Adzuna → company ATS: 1 hop (ideal)
- Adzuna → Indeed/LinkedIn listing → company ATS: 2 hops (requires second click)
- Adzuna → company careers page → specific role: 2 hops (requires navigation)

The `httpx` liveness_checker uses `follow_redirects=True`, so it follows the Adzuna redirect and checks the final destination. This is correct behavior.

### Anti-Bot on Adzuna
Adzuna itself does not place Cloudflare protection on its redirect URLs (they are intentionally public). The final destination after redirect may have Cloudflare — but at that point we're on the company's ATS (Greenhouse/Lever/Workday), which are the same ATS surfaces handled by the direct-ATS fetchers and known to work.

### Variable Source Quality
Adzuna aggregates from many sources including job board APIs, direct employer feeds, and scraped postings. As a result:
- ~15–25% of Adzuna URLs resolve to another aggregator listing (Indeed, SimplyHired, LinkedIn) rather than directly to the ATS. These require a second "Apply" click after navigation.
- ~5–10% of Adzuna URLs are 404 or expired by the time of application (Adzuna does not aggressively prune expired listings).

### Liveness Checker Coverage
The liveness_checker `follow_redirects=True` client will follow the Adzuna redirect. If the final destination is 404 or shows "no longer available," it is caught upstream. If the final destination is another aggregator listing (LinkedIn, Indeed), the liveness checker may return ACTIVE (the listing page exists) even though the apply path from there requires additional navigation. This is a **false-active** case.

### Sources
- Adzuna API documentation confirms `redirect_url` is a tracked redirect to source
- Adzuna marketing: "Easy application process" and "ApplyIQ automatically applies to jobs for you"
- Adzuna acquired Trovit/Mitula (2024), so some listings route through those former brands
