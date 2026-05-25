# source-aggregator-002-simplify-indeed.md
## Simplify Copilot + Indeed: Autofill Coverage

### What Simplify Does on Indeed
Simplify Copilot activates on any page where it detects job application form fields. On Indeed:
- **Indeed Apply modal**: Simplify triggers its overlay. It fills standard profile fields (name, contact info, work history, education, resume upload). Coverage is rated "fairly decent" per community reports on sites like Workday and Greenhouse.
- **Company-site tab**: If clicking "Apply on company site" opens a new tab to Greenhouse/Lever/Workday, Simplify is active in that new tab independently (it's a browser extension, so it activates on any tab). The worker needs to switch focus to that tab.

### Limitations on Indeed Specifically
1. **Screener questions**: Indeed employer-custom screener questions (yes/no, dropdowns, free-text) are frequently missed by Simplify. These require AI-driven completion.
2. **Multi-page Indeed Apply**: Some Indeed Apply flows span 3–5 pages. Simplify handles the first page well; follow-up pages with more nuanced questions (salary expectations, sponsorship, assessments) are partial fills at best.
3. **Resume replacement**: Simplify can upload the stored resume to Indeed Apply, but Indeed also caches a previous resume. If the cached version is stale, the worker needs to explicitly remove it and re-upload.
4. **Ref tag interference**: Reddit thread notes Simplify changes the application ref tag when autofilling through LinkedIn, which may affect tracking attribution. Similar behavior observed on Indeed.

### Community Verdict (2024–2026)
- Simplify gets 4.9/5 on Chrome Web Store with 1M+ installs
- Reddit r/recruitinghell and r/simplify: "helps a lot on Workday, Taleo, Lever, Greenhouse" — Indeed is not the top mention, suggesting more variable behavior
- Review sites note: "calling it auto-apply is misleading, because you are still clicking Submit on every single application yourself"

### Implication for Worker
Simplify handles the bulk of field-filling even on Indeed. The worker's job is:
1. Navigate to the listing page
2. Detect Indeed Apply vs. company-site apply
3. For Indeed Apply: click apply button, wait for modal, let Simplify fill, check for unfilled screener questions, use AI for those, route to NEEDS_REVIEW
4. For company-site apply: click button, intercept new tab, ride ATS flow in that tab

### Sources
- Simplify Jobs Review (2026 review article): autofill coverage summary
- Reddit r/simplify, r/csMajors: ref tag and coverage reports
- Reddit r/recruitinghell: "helps a lot on Workday, Taleo, Lever, Greenhouse"
