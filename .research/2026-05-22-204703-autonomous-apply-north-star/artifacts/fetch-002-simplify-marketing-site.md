# fetch-002 — Simplify marketing site (simplify.jobs and /copilot)

## Sources
- https://simplify.jobs/ — fetched 2026-05-22
- https://simplify.jobs/copilot — fetched 2026-05-22
- https://help.simplify.jobs/articles/8686025-manage-autofill-settings-in-the-simplify-extension — fetched 2026-05-22 (settings doc is referenced here because it concretizes the marketing claims)

## Thesis
The marketing site is the **only authoritative source for "what Simplify thinks autofill does"** — and it's deliberately abstract. The most useful concrete claim is the autofill settings panel, which enumerates the **field categories the extension exposes as toggles** ("LinkedIn URL, Disability, Location, Phone, Education, Work Authorization, Salary"). That toggle list is the closest thing to a documented capability matrix Simplify publishes. Also confirmed: the extension does NOT auto-submit ("Simplify Jobs doesn't auto-apply. It auto-fills. You're still the one clicking Submit — every single time.") and "Continuously autofill multipage forms" is an opt-in setting, not a default.

---

## Verbatim — homepage (simplify.jobs)
- Hero: "Your entire job search. Powered by one profile."
- Sub-hero: "Get personalized job recommendations, craft tailored resumes, autofill and track your job applications"
- Product list: Job Matches, Copilot Extension, AI Resume Builder, Job Tracker
- Adjacent features: Resume ATS Score, Cover Letter & Email Generator, Career Journal, Networking Copilot, Expert-curated lists
- Trust stats: "Join 1,500,000+ job seekers who use Simplify" / "hear back 25% more" / "200,000,000+ applications submitted"
- Pricing: free base + optional **Simplify+** subscription; revenue from employer job-posting fees, not data sales
- Job-board reach: "Source jobs directly from company career pages (20,000+ companies)"

## Verbatim — Copilot page (simplify.jobs/copilot)
- "Autofill job application questions in 1-click"
- "Think of Simplify like Google's generic autofill but designed specifically to help you accurately fill out job applications" — explicit positioning as a smart autofill, NOT an agent
- "Optimize & improve your resume for every job" — scores resume vs. JD, identifies missing keywords (via LinkedIn and Indeed integration)
- "Craft personalized responses with AI" — generates answers to role-fit questions like "why are you a good fit for this role?" (this is the Simplify+ AI-fill claim)
- Tracker: automatically saves submitted apps to dashboard
- **ATS list:** "over 100 job boards and application portals including Workday, Greenhouse, iCIMS, Taleo, Avature, Lever, and SmartRecruiters" — note Ashby is NOT in the named list
- Pricing claim: "Our autofill, application tracker, job matches, and basic resume builder are features we commit to keeping free for everyone."
- 1.5M+ candidates, 200M+ apps, 30M+ this year, 500K+ hours saved
- Profile setup: "we'll ask you to set up a profile with the data we'll need to autofill your job applications"

## Verbatim — autofill settings doc (help.simplify.jobs)
This is the **most field-specific** Simplify document we found. The settings panel exposes three controls:

1. **"Autofill all fields with AI"** — toggle. Doc text: "Use this to let Copilot answer unique questions using information from your profile." Enabled → attempts to autofill non-standard questions. Disabled → skips them.
2. **"Continuously autofill multipage forms"** — toggle. Disabled: "you must click Autofill on each page." Enabled: "Simplify will continue filling each page automatically until the application is submitted."
3. **"Fields to autofill"** — per-field on/off toggles. Examples enumerated by the doc: **LinkedIn URL, Disability, Location, Phone, Education, Work Authorization, Salary**.

A separate help article (`articles/2415391-autofill-skills-on-job-application`) notes: **"Skills autofill is disabled by default but can be enabled quickly in the Copilot popup."** Default-off for skills is a meaningful signal — even Simplify thinks skill-list autofill is risky enough to keep behind a manual toggle.

## What the settings list tells us about the capability matrix
Reading the toggles as a hint of "what Simplify treats as a known field type":
- **Confirmed first-class fields:** LinkedIn URL, Location, Phone, Education, Work Authorization, Salary, Disability, Skills (default-off)
- **Implied first-class but not listed:** Name, Email, Address (assumed too universal to expose as a toggle), Resume upload, Work history
- **NOT in the toggle list (so probably handled by the AI-fill toggle, not deterministic):** EEO race/ethnicity, Gender, Veteran status, Visa status, Long-form essays ("Why $COMPANY?"), Custom multi-select role preferences, Start-date pickers

## Pricing tiers (assembled from this page + downstream reviews — see fetch-003)
| Tier | Cost | Adds |
| --- | --- | --- |
| Free | $0 | Autofill, tracker, keyword suggestions, basic resume builder |
| Simplify+ (1 week) | $19.99 | AI resume generation, AI cover letters, AI-powered custom-question answers, networking tools |
| Simplify+ (1 month) | $39.99 | Same features, "53% discount" claim |
| Simplify+ (3 months) | $89.99 | Same features, "Most Popular Plan" |

The **"Autofill all fields with AI"** toggle in the free tier produces baseline AI answers. **Simplify+** unlocks higher-quality custom-question generation, AI resume optimization, and cover letter generation. Notably the basic autofill itself is in the free tier — Simplify+ is not a gate on field coverage, it's a gate on AI quality.

## Strategic reading
- Simplify markets Copilot as **autofill, not agent**. They specifically deny any auto-submit story. That means the "click Submit" gap is by design, not a missing feature they'll close on us.
- The AI-fill setting is their answer to long-form text fields, but the doc itself flags it as best-effort ("answer unique questions using information from your profile" — no promise of correctness).
- They're not currently competing on agent-style fully-autonomous apply. The competitive set for that is Sonara / JobRight / LazyApply — see search-002.
