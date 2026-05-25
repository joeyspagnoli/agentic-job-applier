# source-niche-003: Custom Company Careers Pages

## The "Custom Front-End" Pattern

Many companies build a branded careers page that hides their ATS behind a custom UI. The apply button eventually redirects to a standard ATS. Detection strategies:

### Pattern 1: Custom URL → Greenhouse/Lever behind the scenes
- Company hosts `careers.company.com` or `company.com/careers` with custom design
- Clicking "Apply" opens a new tab or redirects to `job-boards.greenhouse.io/{slug}/jobs/{id}` or `jobs.lever.co/{slug}/{id}`
- Example: Anthropic uses `anthropic.com/jobs` UI but links go to `job-boards.greenhouse.io/anthropic/jobs/{id}`

### Pattern 2: White-labeled ATS embed (iFrame)
- Company serves their own domain but the form is an iFrame pointing to ATS
- Harder for Simplify Copilot to detect (cross-origin iFrame limitations)
- Less common for top-tier tech companies

### Pattern 3: Fully custom apply flow
- Company has built their own application form (rare for small/mid-size companies)
- Examples: Google (careers.google.com with entirely custom forms), larger enterprises
- These DO have forms but Simplify won't recognize them

## ATS Detection from URL Patterns

The existing `ats_detection.py` already handles the common case: once the apply flow navigates to the ATS domain, the URL-pattern matcher identifies the platform. The challenge is when `source_url` points to the CUSTOM FRONT-END page, not the ATS page.

## Routing Recommendation

When `source_url` host is a company's own domain (not a known ATS):
1. Load the page → detect if there's a form present (pre-flight check).
2. If no form but there's an "Apply" button: click it and follow the redirect.
3. Re-check after navigation: is this now an ATS URL? If yes, proceed normally.
4. If still a custom form on company domain: attempt but flag `ats_platform=UNKNOWN`.
