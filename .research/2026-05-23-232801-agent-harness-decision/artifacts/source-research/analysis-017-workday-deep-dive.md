# analysis-017 — Workday Deep Dive

**Date:** 2026-05-24
**Built on:** 6 source artifacts (`source-workday-001..006`)

Workday is the dominant ATS at large enterprises (Microsoft, Salesforce, Oracle, Walmart, Citi, Goldman, JPM, Accenture, Deloitte, …). The apply-worker will hit it constantly. It's also the most hostile to autofill of all the major ATS platforms.

## The 6–8 step wizard (confirmed sequence)

1. **[Pre-gate] Account Creation / Sign In** — per-company-tenant, email + password + email verification link; **no cross-tenant identity**; no social login.
2. **[Modal] Application Start Method** — "Autofill with Resume" / "Apply Manually" / "Use My Last Application".
3. **Step 1: My Information** — name, address (street/city/state/ZIP/country all separate), phone + phone-type dropdown, email, LinkedIn URL, work-authorization Yes/No, referral-source dropdown. ~10–15 fields.
4. **Step 2: My Experience** — work-history entries (title/company/dates/description), education entries (school/degree-dropdown/field-of-study-typeahead/graduation), skills, **document uploads (the only upload point in the entire wizard)**. ~20–40 fields.
5. **Step 3: Application Questions** — employer-specific; Yes/No knockouts to multi-paragraph essays. ~2–15 fields, high variance.
6. **Step 4: Voluntary Disclosures / Self Identify** — Gender, Race/Ethnicity, Veteran Status, Disability Status. ~3–5 fields. Legally voluntary; sometimes split into two sub-steps at large enterprises.
7. **Step 5: Review** — full summary, no data entry, "Back" button to prior steps.
8. **Step 6: Submit** — single button labeled **"Submit"** or "Submit Application".

## Three biggest Simplify gaps on Workday

### Gap 1 — Essay / open-text application questions (Step 3)

Simplify does not fill open-text essays. Worse: there are documented cases of Simplify pasting **cached content from a previous employer's application** into the new one — a "Why $COMPANY?" answer for company X bleeding into company Y. The finisher must (a) generate fresh answers with the current JD in context, (b) verify company-specificity before writing, (c) re-author any textarea >200 chars whose pre-fill references the wrong company.

### Gap 2 — Account-creation wall (pre-Step 1)

Simplify cannot create accounts or complete email verification. The agent inherits this. If the user is not already signed in on this Workday tenant, the agent must detect the login wall and route to `NEEDS_REVIEW(reason="ACCOUNT_REQUIRED")`. **This is the single most common reason an agent run will fail before filling a single field on Workday.**

### Gap 3 — Dropdown mismatches (Steps 1–2)

Simplify injects candidate profile strings directly into dropdowns. Workday uses **exact catalog values**:

| Field | Simplify likely writes | Workday's catalog value |
|---|---|---|
| Country | "United States" / "US" / "USA" | **"United States of America"** |
| State | "CA" / "FL" | **"California"** / **"Florida"** (full names) |
| Degree | "B.S." / "BS" / "Bachelor of Science" | **"Bachelor's Degree"** |
| Field of Study | (typeahead — direct text injection fails) | type 4 chars → wait for suggestions → pick |

Failure is **silent** — the dropdown reverts to blank without an error message.

**Agent rule:** Never inject into dropdowns directly. Snapshot options first → fuzzy-match the candidate value to the closest option string → select. For Field-of-Study-style typeaheads: type 4 chars, wait 300 ms for the suggestion list, pick the highest-rank match.

## ATS detection gap to fix

`ats_detection.py:14-24` currently matches `myworkdayjobs.com` and `workday.com`. Some tenants use `myworkdaysite.com` (e.g., `jobs.myworkdaysite.com/recruiting/{tenant}/{board}`). The DOM-fallback catches it via the `"workday"` substring, but adding `("myworkdaysite.com", ATSPlatform.WORKDAY)` to `_URL_PATTERNS` makes detection explicit (and faster, since URL match precedes the DOM scan).

## Session timeout (10–15 minutes)

Workday sessions time out after ~10–15 min of inactivity (configurable per tenant; 10 min is the non-PCI default). A Chrome extension (`prevent-workday-timeout`) exists specifically for this. Agent mitigations:
- **Pre-generate LLM content** before starting a step (don't compute mid-step).
- **Detect `/login` redirect** mid-session as a session-expiry signal → abort to `NEEDS_REVIEW(reason="SESSION_EXPIRED")`.
- Per-step budget: target <5 min per step.

## Voluntary Disclosures (Tier-3, confirmed)

Fields: Gender (Male/Female/Non-Binary/Prefer not to answer), Race/Ethnicity (EEO-1 standard 7 categories), Veteran Status (per VEVRAA), Disability Status (OFCCP CC-305, full legal form text). All voluntary.

**But some tenants make a selection REQUIRED to advance** (even "prefer not to answer"). Agent rule:
- If the field is optional → leave blank, the human can decide at review.
- If the field is required-to-advance → select "I prefer not to answer" (or equivalent decline option) ONLY to unblock the wizard, then mark the field as deferred so the human can change it before Submit.

## Per-step agent-tool sequencing

Workday is the platform where the `[Next]` button is its own first-class action. The finisher must:
1. Fill fields in the current step.
2. Verify all required-marked fields in this step are non-empty (or deferred).
3. Click `[Next]` — wait for the next step's URL fragment or AX-tree mutation.
4. Re-snapshot.
5. Repeat until the Review step.
6. On Review, do NOT click `[Submit]` — bail to NEEDS_REVIEW.

**Critical:** `[Next]` is a Tier-1 click (allowlist), `[Submit]` is Tier-3 deny (blocklist). The agent's snapshot serializer must label these distinctly.

## Failure modes specific to Workday

| Mode | Trigger | Agent action |
|---|---|---|
| Account wall | `<login>` URL fragment OR "Sign In" heading before any form fields | `NEEDS_REVIEW(reason="ACCOUNT_REQUIRED")` |
| Session expired | Mid-wizard redirect to `/login` | `NEEDS_REVIEW(reason="SESSION_EXPIRED")` |
| Dropdown silent revert | Field has no value after `select()` | Re-read options, fuzzy-rematch, retry once via `ModelRetry` |
| Typeahead empty | Field-of-Study returns no suggestions for 4-char prefix | Try 2-char prefix, then 6-char; if still empty → defer |
| CAPTCHA | "Verify you're human" heading mid-wizard | `NEEDS_REVIEW(reason="CAPTCHA")` immediately |
| Duplicate application | "You have already applied" banner | `NEEDS_REVIEW(reason="DUPLICATE_APP")` |

## Workday-specific system-prompt guidance (bake into the finisher)

> You are working through a Workday application. Workday breaks the application into 5–8 numbered steps; each step ends with a `[Next]` button you must click before the next step's fields appear.
>
> Hard rules on Workday:
> 1. NEVER click `[Submit]` or `[Submit Application]`. `[Next]` is fine; `[Back]` is fine; `[Save & Continue]` is fine.
> 2. Country dropdowns: always select "United States of America" — NOT "United States" or "US" or "USA".
> 3. State/Province: full names ("California"), never abbreviations.
> 4. Degree dropdowns: select "Bachelor's Degree" / "Master's Degree" / etc., NOT "B.S." / "M.S." / etc.
> 5. Field of Study: type 4 chars, wait 300 ms, pick the closest suggestion. If no suggestions appear, type 2 chars; if still empty, call `defer()` for this field.
> 6. Voluntary Disclosures / Self Identify section: ALL fields are Tier-3 defer. Leave them blank. If a field is required-to-advance, select "I prefer not to answer" and call `defer(reason="workday_voluntary_required_to_advance")` so the human can change it before Submit.
> 7. If you see a Sign In / Create Account screen instead of a form, call `abort(reason="ACCOUNT_REQUIRED")` immediately.
> 8. If the page redirects to `/login` mid-wizard, call `abort(reason="SESSION_EXPIRED")` immediately.
> 9. Don't refill fields Simplify already filled correctly. But on textareas >200 chars, RE-READ the pre-fill — if it references a different company than the current one ($COMPANY), re-author from scratch.

## Estimated agent burden on Workday

- **Best case** (logged in + Simplify hit Step 1+2 well + few custom questions): 8–15 agent turns, $0.005–$0.010 per apply.
- **Typical** (Simplify hit Step 1, partial Step 2, custom essays in Step 3, dropdown corrections needed): 20–30 agent turns, $0.015–$0.025 per apply.
- **Worst inside-budget** (multiple dropdown re-asks + 5+ custom-Q essays + dropdown-mismatch ModelRetries): 35–45 agent turns, $0.030–$0.050 per apply.
- **Bails before LLM ceiling** (account wall / session expired / captcha): 0–2 turns, $<0.001.

All cases remain well under the $0.10 per-apply ceiling. Workday is more turns than Greenhouse but still in budget.
