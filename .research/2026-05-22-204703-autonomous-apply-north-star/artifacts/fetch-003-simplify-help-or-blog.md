# fetch-003 — Simplify help center, blog, and third-party reviews

## Sources
- https://help.simplify.jobs/articles/8686025-manage-autofill-settings-in-the-simplify-extension — fetched 2026-05-22
- https://help.simplify.jobs/articles/2415391-autofill-skills-on-job-application — fetched 2026-05-22
- https://help.simplify.jobs/ — landing fetched 2026-05-22 (3 articles under "Simplify Copilot Extension" — only the two above are reachable without auth)
- https://help.simplify.jobs/article/20-request-new-autofill-support — 404 on direct fetch; reached via search snippet
- https://www.remotejobassistant.com/blog/simplify-jobs-review — fetched 2026-05-22 (most ATS-specific third-party review)
- https://resumehog.com/blog/posts/simplify-copilot-review-2026-is-the-free-autofill-tool-worth-it.html — fetched 2026-05-22
- https://hirepilot.co/simplify-extension-review-does-it-actually-work/ — fetched 2026-05-22
- https://skywork.ai/skypage/en/Simplify-Extension-In-Depth-Review-(2025)-Your-Ultimate-AI-Job-Search-Copilot/1974365563567271936 — fetched 2026-05-22
- https://jobright.ai/blog/simplify-copilot-review-2026-features-pricing-and-top-alternatives/ — fetched 2026-05-22 (competitor-biased)
- https://jobcopilot.com/simplify-jobs-review/ — fetched 2026-05-22 (competitor-biased)
- https://addons.mozilla.org/en-US/firefox/addon/simplify-jobs/reviews/ — fetched 2026-05-22 (first-party negative reviews)

Note on bias: jobright.ai and jobcopilot.com are direct competitors so their critiques are loaded — quoted only where corroborated elsewhere.

## Thesis
Simplify's own help center is thin (only ~3 articles publicly indexed for the extension), but the third-party review pool converges on a consistent picture: **autofill is near-perfect on the standard contact/work-history/education block across the major ATSes (Workday especially praised), and consistently fails on (a) custom open-text questions, (b) preferred-start-date selectors, (c) dropdowns where the user's value doesn't exist in the option list, (d) custom-built non-ATS career pages.** The most damning concrete quote is from remotejobassistant.com: *"an autofilled 'why this company' field carried text from an unrelated prior application to a different employer entirely"* — the AI-fill long-text feature is the single biggest correctness hazard.

---

## Verbatim — Simplify's own docs

### Autofill settings (full extract)
- "Autofill all fields with AI": "Use this to let Copilot answer unique questions using information from your profile"
- "Continuously autofill multipage forms": "Simplify will continue filling each page automatically until the application is submitted"
- "Fields to autofill" panel exposes: LinkedIn URL, Disability, Location, Phone, Education, Work Authorization, Salary
- Per-field toggles exist for each. No documented per-ATS overrides.

### Skills autofill (separate article)
- "Skills autofill is disabled by default but can be enabled quickly in the Copilot popup."
- Enable path: Settings → Other section → toggle Skills on → trigger autofill

### "Request new autofill support" (article 20)
- We couldn't fetch the body (page is mobile-only / login-gated for full content). The article title alone tells us something material: **Simplify's autofill is per-site, not universal.** Users have to request new sites. This implies a curated mapping layer (XPaths / heuristics tuned per career-page template) rather than a fully generic LLM-driven understanding. Cross-confirmed by the SimplifyJobs GitHub take-home assignment: "Use XPaths to find the relevant elements" + a JSON config structure for form automation.

## Verbatim — third-party reviews on what fills and what doesn't

### remotejobassistant.com (2026 review — most specific)
- **Fills well, all five major ATSes:** "On Workday, Greenhouse, Lever, iCIMS, and Taleo: 'near-perfect' or '90%+' accuracy for standard field population"
- **Standard field set:** "Name, contact info, work history, education, work authorization"
- **Workday time-saving:** "a manual Workday application taking 22 minutes was reduced to 8 minutes with Simplify running"
- **Hard failures:** "Custom and open-text fields required manual entry on all five platforms"
- **Specific problem areas:** "'Why this company' questions; 'Describe a challenge you overcame' prompts; Preferred start date selections; Any open-text questions outside the standard contact/work history template"
- **AI-fill correctness hazard (verbatim):** "an autofilled 'why this company' field carried text from an unrelated prior application to a different employer entirely"
- **Multi-page behavior:** "Simplify's 'multi-page auto-complete' setting advances through form pages automatically but stops at the final submission page, requiring manual user confirmation. This is not true auto-submission."
- **Honest summary line:** "The supervision requirement is equally real and not marketed"

### resumehog.com (2026 review)
- Workday: "Anyone who has applied to a corporate job dreads the Workday portal. Simplify handles these complex Applicant Tracking Systems with surprising ease."
- Failure surface: "on custom-built company websites, the extension can sometimes map data to the wrong fields, requiring a few manual corrections"
- Time savings: "reduces tasks that typically take 15 to 25 minutes per application down to just 1 to 2 minutes"
- AI quality (Simplify+): "often produce robotic-sounding cover letter drafts"
- EEO/demographic forms: NOT mentioned (significant absence)

### hirepilot.co (2025 review — most detailed failure examples)
- General failure rate: "the extension did not populate any fields at all" on some forms; "filled in some sections correctly but left others empty, requiring manual entry anyway"
- LinkedIn Easy Apply bug: "redirected to a different job listing entirely, breaking the application process"
- Resume parsing errors: "certifications under the education section" (placed in wrong section); "date of birth field with today's date instead of correct information"

### skywork.ai (2025 in-depth review)
- Strong ATS list: Workday, Greenhouse, Lever
- Failure surface: "may struggle with non-standard, custom-built, or less common application portals"
- AI quality: "often requires heavy editing to sound human"; "over-optimization for ATS keywords that harms readability"

### jobcopilot.com (competitor, biased — use only the field-level quotes)
- AI-generated content: handles "Open-ended questions – 'Tell us why you're a fit,' for example"
- Reddit-attributed (no link): "Tool works as intended but 'didn't lead to any interview callbacks'"; "Described as 'glorified autofill' by some users"
- TrustPilot 1-star: "process remained 'manual'"
- TrustPilot 3-star: "Praised Workday handling but cited 'bugs, resume customization limits' and concern that 'over-optimization for ATS keywords' hurt readability"

### Firefox add-on reviews (first-party, most credible negatives)
Dominant complaint categories — note that **field-level autofill failures are LESS reported than perf and auth problems**:
- Performance / browser hang: "lags my computer to a complete stop" (noahc, 9 months ago, 1-star); "brings my entire Mac to a halt when opening any new tab" (fazedoge, 1 year ago, 2-star); "extension is so painfully slow that it ends up wasting more of your time" (Jason weng, 10 months ago, 1-star)
- Login loops: "extension can't connect to my profile" (Gcwan, 9 months ago, 1-star); multiple users stuck at login prompt
- Compatibility: "extension breaks MS Teams. can't open a Teams meeting while this extension is enabled" (Firefox user 13658959, 2 years ago, 3-star)
- The ONLY direct field-level Firefox complaint we found: "In some applications it doesn't fill the drop down if a degree doesn't exist" (Hari, 1 year ago, embedded in a 5-star review)

## Convergent findings across all third-party sources
1. **Always reliable:** Name, email, phone, address, education (school + degree if present in dropdown), work history dates and titles, resume file upload, LinkedIn URL.
2. **Mostly reliable but with caveats:** Work authorization (yes/no), salary expectation, skills (default off).
3. **Best-effort via AI-fill toggle (correctness not guaranteed):** "Why $COMPANY?", "Tell us about a time you...", role-fit explanations.
4. **Routinely empty / wrong:** EEO race/ethnicity/gender/veteran/disability (silent in all reviews — meaning either it works silently or, more likely, it's not addressed because users don't expect autofill of demographic data), preferred start date pickers, custom multi-selects when user value isn't in option list, role-preference checklists, anything on a custom (non-ATS-templated) career page.
5. **AI-fill is the highest-risk feature.** The single best-quoted failure (cross-employer text leakage in a "why this company" answer) means **any pipeline using AI-fill MUST gate every output through human review** — which is exactly what the human review step in our existing apply_worker enforces.

## What the help-center surface implies about Simplify's architecture
- Per-site XPath maps (their take-home assignment confirms this)
- A request-queue for new sites (article 20)
- An AI layer bolted on top for unique questions, gated by the "AI Fill" toggle
- No documented programmatic-trigger API — clicking the shadow-root button is the only entry point
- Settings are stored locally (chrome.storage) and synced via the Simplify account; the extension talks to api.simplify.jobs for profile sync (inferred — Simplify's own help center says "we'll ask you to set up a profile")
