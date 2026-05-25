# source-aggregator-004-ziprecruiter.md
## ZipRecruiter Apply: Form Fields and Automation

### What `source_url` Resolves To
ZipRecruiter is not scraped by JobSpy directly (JobSpy covers Indeed, Glassdoor, LinkedIn). ZipRecruiter may appear in Adzuna results (`redirect_url`) if Adzuna aggregates ZipRecruiter-sourced listings.

When a ZipRecruiter URL is encountered:
- `https://www.ziprecruiter.com/jobs/<company>-<title>-<id>` — ZipRecruiter listing page

### ZipRecruiter's Own Apply Form
ZipRecruiter hosts its own "1-Click Apply" form. It is a ZipRecruiter-native form (not a redirect to ATS). Fields include:
- Name, email, phone
- Resume upload (or use ZipRecruiter profile)
- Optional cover letter
- Screener questions (employer-defined)

ZipRecruiter's form IS an HTML form — Simplify can autofill standard fields. Screener questions vary.

### "Apply on company site" Variant
Some ZipRecruiter listings have an "Apply on company site" button alongside ZipRecruiter's own form. The behavior is the same: new tab spawns to the employer's ATS.

### Anti-Bot Risk
ZipRecruiter does not use Cloudflare's "Just a moment" challenge on its own listing pages. Navigation with a real logged-in Chrome session is generally clean. However ZipRecruiter does rate-limit automated clicks if patterns look too fast.

### Simplify Coverage on ZipRecruiter
Community reports do not call out ZipRecruiter specifically as a Simplify-covered site. ZipRecruiter's form uses standard HTML inputs, so Simplify likely triggers — but ZipRecruiter's 1-Click Apply can bypass most form-fill by using the stored ZipRecruiter profile. For our worker, ZipRecruiter is low-priority since it appears less frequently via our fetcher chain.

### Sources
- ZipRecruiter job listing searches confirm "1-click apply" and "apply on company site" both exist
- Playwright ZipRecruiter searches only surfaced ZipRecruiter AS a job listing site, not automation-specific docs
