# source-workday-001-wizard-structure.md

**Topic:** Workday multi-step application wizard structure  
**Date fetched:** 2026-05-24  
**Sources consulted:**
- https://www.wlu.edu/employment-opportunities/staff-and-administrative-positions/application-instructions-for-new-external-applicants/
- https://hirepilot.co/how-to-complete-a-workday-application-faster/
- https://teex.org/wp-content/uploads/Step-by-step-Workday-External-Applicant-Instructions.pdf (PDF — binary, not parseable)
- WebSearch: "Workday application wizard steps 2024 My Information My Experience Application Questions Self Identify Review complete guide"

---

## Confirmed Wizard Step Sequence (5–7 steps depending on company config)

### Pre-Application Gate: Account Creation / Sign In
- External candidates hit a **Workday Candidate portal** (company-specific tenant)
- Prompt: "Sign In" or "Create Account" 
- If new: enter email + password; verification email sent
- Must verify email before proceeding
- **Each company = separate Workday tenant = separate account required**
- No cross-tenant SSO for candidates (enterprise SSO only for employees)

### Application Start Method (modal before Step 1)
Three choices presented after signing in / before My Information:
1. **Autofill with Resume** — upload PDF/DOCX; Workday parser fills work history + education
2. **Apply Manually** — no pre-fill
3. **Use My Last Application** — reuse data from previous application at this same tenant

---

## Step 1: My Information

**Fields confirmed:**
- First Name, Last Name
- Address (Street Address, City, State/Province, Postal Code, Country — separate fields)
- Phone Number + Phone Type dropdown (Mobile / Home / Work)
- Email Address
- LinkedIn URL (optional)
- "How did you hear about us?" / Referral Source dropdown (optional; sometimes auto-populated from tracking param)
- Work Authorization question — varies by company:
  - Often a dropdown or Yes/No: "Are you legally authorized to work in [country]?"
  - Separate: "Do you now or in the future require visa sponsorship?"

**Typical field count: ~10–15 depending on company config**

---

## Step 2: My Experience

**Fields confirmed:**
- Work Experience entries (each entry: Job Title, Company Name, Start Date [month/year], End Date [month/year], currently employed toggle, Description)
- Education entries (each entry: School Name, Degree/Level dropdown, Field of Study, Start Date, End Date / Graduation Date)
- Skills (free-text tags or dropdown, optional)
- **Document uploads — CRITICAL: this is the ONLY place to upload documents in the wizard**
  - Resume (PDF preferred)
  - Cover Letter (optional unless required)
  - Up to 5 files maximum

**Typical field count: ~20–40 depending on experience history depth**

---

## Step 3: Application Questions

**Fields confirmed:**
- Employer-specific, highly variable
- Range: simple Yes/No knockout questions to multi-paragraph essay questions
- Common types:
  - "Minimum salary expectation?" (text or dropdown)
  - "Are you willing to relocate?" (Yes/No/Maybe)
  - "Years of experience in [technology]?" (dropdown: 0-1, 1-3, 3-5, 5+)
  - "Describe your experience with [X]" (free text, 500-2000 chars)
  - Open-ended essay: "Why do you want to work here?" / "Describe a challenge you overcame"
- Required fields marked with asterisk (*)
- **Cannot proceed to next step until required fields filled**

**Typical field count: 2–15, varies wildly**

---

## Step 4: Voluntary Disclosures / Self Identify

**Fields confirmed (demographically sensitive — TIER 3, never auto-fill):**
- Gender (dropdown: Male / Female / Non-Binary / I prefer not to answer / Other)
- Race/Ethnicity (dropdown: American Indian/Alaska Native / Asian / Black or African American / Hispanic or Latino / Native Hawaiian/Other Pacific Islander / White / Two or more races / I prefer not to answer)
- Veteran Status (dropdown options vary; typically: Protected Veteran / Not a Protected Veteran / I prefer not to answer / Other)
- Disability Status (per OFCCP Form CC-305: Yes / No / I prefer not to answer)

**Notes:**
- All fields are legally voluntary
- Section exists for OFCCP / EEOC federal contractor compliance
- "I prefer not to answer" / "I don't wish to answer" option always available
- Some portals: leaving incomplete prevents advancing to Review (must at least select "prefer not to answer")
- Some portals split into two sub-steps: "Voluntary Disclosures" + "Self Identify" (disability/veteran separate from race/gender)

**Typical field count: 3–5**

---

## Step 5: Review

- Full summary of all previous steps
- Editable via "Back" button to any prior step
- No new data entry — display only
- Verify: resume uploaded, contact info correct, experience complete

---

## Step 6: Submit

- Single button at bottom of Review step
- **Button label: "Submit"** (confirmed by multiple institutional guides)
- Note: Some employers show "Submit Application" but "Submit" is standard
- After click: confirmation message + confirmation email sent
- **Application is locked; no edits possible after submission**

---

## Session Timeout Risk

- Workday employee sessions: 10–15 minutes inactivity
- Candidate application portal: anecdotally similar; GitHub extension `prevent-workday-timeout` exists confirming this is a known problem
- Each step interaction resets timer
- Risk: if agent pauses between steps > 10 min, session expires and must re-authenticate

---

## Key Structural Notes

- Some companies add additional custom steps (e.g., "Additional Questions" between Application Questions and Voluntary Disclosures)
- Step count ranges from 5 (minimal) to 8 (maximum with split Voluntary Disclosures)
- Sidebar/progress indicator shows current step number and step names on left panel
- "Next" button advances; "Back" button returns without losing data
- Workday auto-saves progress within a session but not across sessions

---

## Sources

- [WLU Application Instructions](https://www.wlu.edu/employment-opportunities/staff-and-administrative-positions/application-instructions-for-new-external-applicants/)
- [HirePilot: How to Complete a Workday Application Faster](https://hirepilot.co/how-to-complete-a-workday-application-faster/)
- WebSearch synthesis from multiple institutional guides
