# analysis-016 — Direct ATS Platforms: Greenhouse, Lever, Ashby, SmartRecruiters

**Date:** 2026-05-24
**Mode:** Design (research)
**Built on:** 16 fetch artifacts in `source-research/source-{greenhouse,lever,ashby,smartrecruiters}-*.md`

---

## 1. Greenhouse

**Landing behavior.** `source_url` = `https://job-boards.greenhouse.io/[company]/jobs/[id]` — a job detail page. The application form is **inline on the same page**, revealed after clicking "Apply for this job". One click; no page navigation; same DOM.

**Required field set.** First Name, Last Name, Email, Phone, Location. Resume upload (PDF/DOCX, ≤500 MB). "How did you hear about us?" dropdown (usually required). Cover letter (varies). LinkedIn URL (often employer-required). Work history + education auto-parsed from resume.

**Custom questions.** 0–12 per job (modal 3–6). Types: short text, long-form essay, yes/no, dropdown, file attachment, checkbox, number, date. Near-universal knockout pair: "Are you legally authorized to work in the US?" + "Will you require sponsorship?" — auto-reject if answered No. Essays ("Why $COMPANY?", "Describe a challenge") are the largest time sinks.

**What Simplify fills.** First/last name, email, phone, location, LinkedIn, work history, education, skills, work authorization (stored), disability/EEO toggles. Standard fields are reliably filled — accuracy is high.

**What Simplify misses.** (1) All employer-configured custom questions. (2) "How did you hear about us?" dropdown — frequently unmatched. (3) Cover letter (Simplify+ AI only). (4) Salary, start date, referral specifics.

**Submit button + EEO.** Submit text: **"Submit Application"**. EEO section: bottom of main form, before Submit (same page, non-blocking, "Decline to self-identify" allowed on all fields).

**Failure modes.** (1) Greenhouse's **invisible reCAPTCHA** — the highest automation risk of the four. Analyzes mouse/typing; if triggered, sends an email verification code that blocks submission. Headed Chrome + Simplify's prior human-like interactions reduce but don't eliminate risk. (2) Auto-reject knockout questions. (3) Duplicate application detection (same email + same job). (4) Required cover letter blocking submission if missing.

**Estimated agent burden.** 5–15 fields remaining after Simplify (custom questions dominate; standard fields reliably covered).

---

## 2. Lever

**Landing behavior.** `source_url` = `https://jobs.lever.co/[company]/[uuid]` — job detail page. The apply form lives at a **separate `/apply` subpath**. One click on "Apply for this job" triggers a full page navigation to `jobs.lever.co/[company]/[uuid]/apply`. If `source_url` is already the `/apply` URL (some fetchers may resolve to this directly), zero extra clicks.

**Required field set.** Full Name + Email are system-enforced. Employer typically requires: Phone, Current Company, Current Location, Resume (multipart, ≤100 MB), LinkedIn URL, GitHub URL. "Additional Information" / Comments textarea is the de facto cover letter field.

**Custom questions.** 0–8 (modal 2–5). Split into (a) global questions site-wide and (b) per-job questions. Types: single line text, long text, dropdown, multiple choice, yes/no, file upload, link/URL. Lever supports auto-screening rules on dropdown/checkbox/yes-no answers.

**What Simplify fills.** Full name, email, phone, current company, current location, LinkedIn, GitHub, personal website, work authorization, resume. Multi-step progression handled via Simplify's auto-advance setting.

**What Simplify misses.** (1) All custom questions. (2) "Additional Information" textarea. (3) Cover letter file upload (if present as a custom question). (4) Known **wrong-field carryover bug** (text from a previous application bleeds into a different field on Lever).

**Submit button + EEO.** Submit text: **"Submit application"** (note lowercase 'a' — Lever's exact default). EEO: end of the apply form, after all custom questions, before Submit. Dynamically rendered based on location; voluntary.

**Failure modes.** (1) Lever job board pages return 403 to headless scrapers — not a problem with headed Chrome. (2) Required "Additional Information" left empty. (3) **No reCAPTCHA on standard forms** — Lever is the lowest automation risk of the four. (4) File upload type restrictions on custom file questions.

**Estimated agent burden.** 5–15 fields.

---

## 3. Ashby

**Landing behavior.** `source_url` = `https://jobs.ashbyhq.com/[company]/[uuid]` — heavily React/JS-rendered detail page. Worker must wait for JS execution before Simplify detects the form. "Apply" button navigates to `jobs.ashbyhq.com/[company]/[uuid]/application`. One click plus a full-page JS render wait.

**Required field set.** First Name, Last Name, Email, Phone, Location/City, LinkedIn Profile URL (auto-populates candidate profile — particularly important to fill correctly), Resume (required, ≤16 MB for parsing / ≤50 MB raw), Portfolio URL (optional). Work history + education auto-parsed.

**Custom questions.** 3–8, notably **essay-heavy** (Ashby is predominantly used by growth-stage tech: Ramp, OpenAI, Brex). Types: short answer, long answer, multiple choice (ValueSelect), checkboxes (MultiValueSelect), date, yes/no, number, file upload, education history, referral URL. **"Why are you interested in this role?" is nearly universal on Ashby.**

**What Simplify fills.** Name, email, phone, location, LinkedIn, resume, work authorization. However, Ashby's React-controlled form components cause a **higher base miss rate** even on standard fields — React's controlled inputs require correctly dispatched DOM events; browser-native autofill and extensions like Simplify have documented issues with React forms.

**What Simplify misses.** (1) All custom questions. (2) Standard fields may also be blank post-Simplify due to React issues — **agent must verify name/email/phone were actually populated.** (3) MultiValueSelect checkboxes (inconsistent). (4) Resume file picker may not trigger correctly on Ashby's React form.

**Submit button + EEO.** Submit text: **"Submit Application"** (confirmed via Ashby's developer embed examples and `applicationForm.submit` API endpoint). EEO: optional, often absent entirely on Ashby (most growth-stage companies don't enable it); when present, appears at form bottom, non-blocking.

**Failure modes.** (1) JS rendering — agent must wait for full React mount. (2) React controlled inputs — standard fields need explicit verification post-Simplify. (3) Form Field Connectors — Ashby maps answers to structured candidate profile fields; wrong format (e.g., wrong city format) can cause silent validation failures. (4) Resume >16 MB uploads but won't be text-parsed. (5) No reCAPTCHA — low automation risk at submit.

**Estimated agent burden.** 5–15 fields, **skewing toward 15** (React issues may require re-entering standard fields + more essay-type questions). Ashby carries the highest per-apply verification burden.

---

## 4. SmartRecruiters

**Landing behavior.** `source_url` = `https://careers.smartrecruiters.com/[Company]/[job-id]` — job detail page with a prominent **"I'm Interested"** button. Clicking it reveals the application form inline.

**CRITICAL:** "I'm Interested" is a **form-trigger, NOT a submit action**. The actual submit button ("Submit"/"Submit Application") is at the end of the filled form. Worker sequence: click "I'm Interested" → form reveals → trigger Simplify → fill → human Submit.

**Required field set.** System minimum: `firstName`, `lastName`, `email`. Employer typically adds: Phone, Place of Residence (city/region or postal code), Work Experience (1+ entries), Education (1+ entries), Resume (always available), Message to Hiring Manager (if enabled as required). Often multi-step: Step 1 basic info → Step 2 experience/education → Step 3 custom questions → Step 4 review/submit.

**Custom questions.** 2–6 (compliance-oriented — SmartRecruiters predominantly serves enterprise: pharma, manufacturing, government). Tend to be yes/no knockouts (work auth, background check consent, relocation) more than essays. Types: yes/no, single select, multi-select, free text, number, date.

**What Simplify fills.** First/last name, email, phone, location/residence, work history, education, resume, work authorization. After the "I'm Interested" form-reveal, Simplify should detect the form and autofill normally.

**What Simplify misses.** (1) All custom screening questions. (2) "Message to Hiring Manager" (free-text; Simplify+ AI only). (3) Multi-step "Next" button navigation — Simplify's auto-advance may stall between steps. (4) **The "I'm Interested" click itself must happen before Simplify can run.**

**Submit button + EEO.** Form-trigger button: **"I'm Interested"** (NOT submit). Actual submit: **"Submit"** or **"Submit Application"**. EEO: end of form ("Confidential Diversity Questions"); for OFCCP-compliant employers (government contractors), may be a separate post-submit page. Non-blocking in either case.

**Failure modes.** (1) "I'm Interested" misidentified as submit — **must be EXCLUDED from the no-Submit deny list**. (2) Multi-step form stalling on "Next" clicks. (3) Account creation interstitial before/after form (dismissible). (4) Easy Apply conflict if third-party Easy Apply enabled. (5) Resume parsing quirks with some PDF structures.

**Estimated agent burden.** 5–15 fields (lighter on essays than Ashby; multi-step navigation adds friction; compliance yes/no routing needs care).

---

## Comparison Table

| ATS | Direct-to-form? | Custom-Q count | EEO position | Submit button text | Simplify miss rate |
|-----|-----------------|----------------|--------------|--------------------|--------------------|
| **Greenhouse** | No — 1 click, form inline same page | 3–6 | Bottom of main form, before Submit | **"Submit Application"** | Low standard / High custom |
| **Lever** | No — 1 click, navigates to `/apply` | 2–6 (global + per-job) | End of apply form, before Submit | **"Submit application"** (lowercase a) | Low standard / High custom |
| **Ashby** | No — 1 click, navigates to `/application` | 3–8 (essay-heavy) | End of form if present (often absent) | **"Submit Application"** | Medium standard (React) / High custom |
| **SmartRecruiters** | No — 1 click ("I'm Interested" ≠ submit), form reveals inline | 2–6 (compliance-heavy) | End of form or separate post-submit page | **"Submit"** / **"Submit Application"** | Low-Medium standard / High custom |

## The single universal miss

**"Why are you interested in this role?"** (or "Why $COMPANY?") — long-form essay field — appears on nearly every Ashby job, very common on Lever, common on Greenhouse, present on many SmartRecruiters postings. **Cannot be filled by free Simplify tier**; requires AI generation drawing from candidate profile + job description.

This single question is the most important thing the Layer-3 finisher must handle reliably — it justifies the entire LLM-in-the-loop architecture even if everything else were Simplify-coverable.

## Implications for the no-Submit deny list

The deny-list must include exact-text and prefix matching. Concrete entries:

```python
SUBMIT_LIKE_LABELS = {
    # exact
    "Submit Application",            # Greenhouse, Ashby
    "Submit application",            # Lever — lowercase a!
    "Submit",                        # SmartRecruiters (and others) — careful: too broad
    # prefix-safe matches for SmartRecruiters / Workday variants
    "Send Application",
    "Apply Now",                     # NOT to be confused with "I'm Interested"
    "Finalize",
    "Confirm Submission",
}

SUBMIT_LIKE_PREFIXES = (
    "submit",                        # case-insensitive prefix on accessible-name
    "send",
    "apply now",
    "finalize",
    "confirm submission",
)

# Form-trigger buttons that LOOK like Submit but ARE NOT — explicitly allowed
FORM_TRIGGER_ALLOWLIST = {
    "I'm Interested",                # SmartRecruiters — reveals the form
    "Apply for this job",            # Greenhouse — opens the form inline
    "Apply",                         # Ashby/Lever — navigates to /apply or /application
    "Easy Apply",                    # LinkedIn — opens the modal
}
```

The allowlist takes precedence over the deny-list during snapshot filtering. Without it, the agent would refuse to click "I'm Interested" on SmartRecruiters because "Apply Now" matches a prefix and "Apply" appears in the label.
