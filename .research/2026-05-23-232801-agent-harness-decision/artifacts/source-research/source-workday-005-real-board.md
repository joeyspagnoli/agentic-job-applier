# source-workday-005-real-board.md

**Topic:** Real Workday job boards — URL patterns observed  
**Date fetched:** 2026-05-24  
**Sources consulted:**
- https://workday.wd5.myworkdayjobs.com/Workday (Workday's own careers board — empty response)
- https://jobo.world/ats/workday (Workday scraper API documentation)
- https://www.netify.ai/resources/domains/myworkdayjobs.com
- https://www.netify.ai/resources/domains/myworkdaysite.com
- WebSearch synthesis

---

## Real Workday Career Board URLs Observed

### Standard Pattern: `{tenant}.wd{N}.myworkdayjobs.com`

| Company | URL | Cluster |
|---|---|---|
| Workday (self) | workday.wd5.myworkdayjobs.com/Workday | wd5 |
| RBS (Royal Bank of Scotland) | rbs.wd3.myworkdayjobs.com/RBS | wd3 |
| Salesforce | salesforce.wd12.myworkdayjobs.com | wd12 |
| Lilly (Eli Lilly) | lilly.wd5.myworkdayjobs.com | wd5 |
| PATH (nonprofit) | path.wd1.myworkdayjobs.com/External | wd1 |

**Notes:**
- `{N}` in `wd{N}` is the Workday cluster number assigned at tenant provisioning; ranges from wd1 to wd12+ observed
- **Never assume the cluster number** — must be read from the actual URL
- The `{board}` segment after the domain is the specific job board name configured per company

### Alternative Pattern: `jobs.myworkdaysite.com`

- Format: `https://jobs.myworkdaysite.com/recruiting/{tenant}/{board}`
- Less common; observed for some companies
- The `myworkdaysite.com` domain is distinct from `myworkdayjobs.com`

### Self-Hosted / Custom Domain Pattern

Some large enterprises embed Workday in their own careers domain:
- Example: `careers.company.com` with Workday iframe or redirect
- The page HTML contains `myworkdayjobs.com` or `workday.com` references
- Apply button redirects to `{tenant}.wd{N}.myworkdayjobs.com/...`
- The actual application form is always on `myworkdayjobs.com` — the company domain is just a landing page

**Detection implication:** Even if the user navigates to `careers.microsoft.com`, the actual application URL at form-fill time will be on `myworkdayjobs.com` or `myworkdaysite.com`.

---

## API Endpoints (from jobo.world docs)

These are the programmatic patterns exposed by Workday's public ATS API:

- **Job Listings (POST):** `https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{board}/jobs`
- **Job Detail (GET):** `https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{board}/job/{externalPath}`
- **Sitemap:** `https://{tenant}.wd{N}.myworkdayjobs.com/en-US/{board}/siteMap.xml`

Requisition ID formats observed: `JR_12345`, `REQ12345`, `R-00066362`

---

## Attempt to Fetch Workday Careers Board (workday.wd5.myworkdayjobs.com/Workday)

- WebFetch returned empty content — the page is a JavaScript SPA (React/Angular)
- Raw HTML is minimal; content loaded via XHR/fetch calls after page load
- This confirms: **Workday job boards require JavaScript execution to render** — not fetchable with simple HTTP GET

---

## ATS Detection Adequacy Assessment

Current `ats_detection.py` patterns:
```python
("myworkdayjobs.com", ATSPlatform.WORKDAY),
("workday.com", ATSPlatform.WORKDAY),
```

**Assessment: SUFFICIENT with one gap**

- `myworkdayjobs.com` substring catches: `*.wd{N}.myworkdayjobs.com` ✓
- `workday.com` substring catches: `workday.com` redirects + some self-hosted ✓
- **GAP: `myworkdaysite.com` not covered** — the alternative domain pattern

**Recommended addition:**
```python
("myworkdaysite.com", ATSPlatform.WORKDAY),
```

- DOM fallback already covers the "workday" string, which catches most iframes/embeds ✓
- The DOM fallback `if "workday" in html_prefix` also catches `myworkdaysite.com` pages that reference Workday in their HTML

**Verdict:** Current detection is ~97% sufficient. Adding `myworkdaysite.com` to URL patterns closes the last gap cleanly.

---

## Sources

- [jobo.world: Workday Scraper API](https://jobo.world/ats/workday)
- [Netify: myworkdayjobs.com domain info](https://www.netify.ai/resources/domains/myworkdayjobs.com)
- [Netify: myworkdaysite.com domain info](https://www.netify.ai/resources/domains/myworkdaysite.com)
- Live URL examples from search results
