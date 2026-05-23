# fetch-001 — Simplify Copilot Chrome Web Store listing

## Sources
- https://chromewebstore.google.com/detail/simplify-copilot-autofill/pbanhockgagggenencehbnadejlgchfc — fetched 2026-05-22
- https://chromewebstore.google.com/detail/simplify-copilot-autofill/pbanhockgagggenencehbnadejlgchfc/reviews — referenced 2026-05-22
- https://addons.mozilla.org/en-US/firefox/addon/simplify-jobs/reviews/ — fetched 2026-05-22 (Firefox listing — Anthropic crawler can't reach Chrome reviews directly, so Firefox is the proxy for first-party negative reviews)
- https://www.linkedin.com/posts/myan_simplifys-copilot-extension-just-hit-200000-activity-7113618832488857600-9aID — fetched 2026-05-22 (founder announcement)

## Thesis
The CWS listing is a marketing surface — heavy on impact claims (3-5x more apps, 100M+ submissions) but quiet about field-level limits. The only structural detail we extract is the **8.6 MiB unpacked size**, current **v2.5.0 on 2026-05-22**, and **500,000+ users** with a **4.9/5 (3.6K ratings)**. The version cadence is fast: we know v2.4.1 shipped earlier (a downstream repo's `.env.example` pins `2.4.1_0`), and our own pipeline notes report v2.4.6 on 2026-05-07, so the extension ships roughly every couple of weeks. The CWS reviews are aggregated 5-star and useless for failure-mode research; the Firefox listing is where the angry users go.

---

## Verbatim extract — listing metadata (2026-05-22)
- **Title:** "Simplify Copilot - Autofill job applications, job tracker & AI resumes"
- **Tagline:** "The better way to job search. Quick apply and autofill job applications in one click. Track jobs, companies, resumes & more!"
- **Users:** 500,000+
- **Rating:** 4.9 (3.6K ratings)
- **Version:** 2.5.0
- **Updated:** May 22, 2026 (so an update shipped the same day this research pass ran)
- **Size:** 8.6 MiB
- **Language:** English only
- **Developer:** Simplify Jobs, Inc. (10-person team, San Francisco)
- **Contact:** support@simplify.jobs, +1 304-919-0100
- **D-U-N-S:** 118347701

## Verbatim extract — capability claims (CWS body)
- "Autofill Applications on All Major ATSs" across Workday, Lever, Greenhouse, and thousands of job boards
- "Generate tailored, ATS-friendly resumes and personalized cover letters using our recruiter-approved AI"
- AI resume builder credited with creating over 1,000,000 resumes
- All-in-one job tracker for bookmarking and tracking applications
- "Identify Missing Keywords in Your Resume" by analyzing job descriptions
- Personalized job recommendations based on user preferences

## Verbatim extract — impact claims
- Users report "applying to 3-5x more positions with the same effort"
- Helped applicants "submit over 100 million applications and land thousands of job offers"
- Application time "from 10+ minutes to seconds"
- Privacy posture: "We do NOT sell your data to advertisers"

## Pricing tier surface
- "Free to use with premium features available" (no tier breakdown on the CWS page itself; pricing is unpacked in fetch-002 / fetch-003)

---

## Version cadence (assembled from cross-references)
| Version | Approx. date | Source |
| --- | --- | --- |
| 2.4.1 | mid-2025 (date inferred from .env.example pin) | `akshatvasisht/notiapply/.env.example` pins `2.4.1_0` |
| 2.4.6 | 2026-05-07 | our own pipeline notes (CLAUDE-adjacent context provided in mission brief) |
| 2.5.0 | 2026-05-22 | CWS listing today |

**Implication:** the extension ships fast, so any DOM selector or shadow-root contract we depend on is mutable. Our pipeline already pierces `.simplify-jobs-shadow-root` and reads `aria-label` text — both have survived at least three releases between v2.4.1 and v2.5.0, but neither is a documented contract.

## User-count growth signal
- LinkedIn post by Michael Yan (Simplify founder), dated ~2 years ago (early-to-mid 2024): "Simplify's Copilot Extension just hit 200,000+ users"
- 2026-05-22 CWS: 500,000+
- Roughly 2.5x in ~2 years. Healthy but not viral — they are not a winner-takes-all platform.

## Negative-review signal (Firefox proxy — these are the same product, same engine)
The Chrome reviews are sanitized by the 4.9-star aggregate. Firefox carries the same code with much louder complaints — see fetch-003 / search-001 for the substantive quotes. Top buckets:
- **Performance:** "lags my computer to a complete stop", "brings my entire Mac to a halt when opening any new tab" — repeated complaints over 12+ months
- **Auth/connection:** "extension can't connect to my profile" — repeated login-loop failures
- **Field-level:** "In some applications it doesn't fill the drop down if a degree doesn't exist" — this is the only ATS-specific field-failure quote in the Firefox reviews; the others are dominated by perf and login issues

## What the CWS page does NOT say (load-bearing absences)
- No ATS-by-ATS field-coverage matrix
- No mention of EEO / demographic / veteran / self-id field handling
- No mention of work authorization or visa fields
- No mention of multi-page Workday navigation behavior
- No mention of file-upload behavior (does it upload Simplify's stored resume or whatever the user puts in the form?)
- No mention of postMessage / programmatic-trigger API
- No privacy-policy detail on what gets sent to Simplify servers when "Autofill all fields with AI" is enabled
