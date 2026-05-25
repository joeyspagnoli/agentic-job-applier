# source-workday-006-voluntary-disclosure.md

**Topic:** Workday Voluntary Disclosures / Self Identify step fields — Tier-3 deny list confirmation  
**Date fetched:** 2026-05-24  
**Sources consulted:**
- WebSearch: "Workday Voluntary Disclosures Self Identify fields race ethnicity disability veteran"
- https://civilrights.osu.edu/about/focus-areas/voluntary-self-identification-disability
- https://news.vt.edu/notices/2025/04/crcpe-selfid-veterans.html
- https://www.pwc.com/us/en/careers/voluntarydisclosures.html (blocked 403)
- WebSearch: "Workday Voluntary Disclosures step application gender race ethnicity disability veteran exact field labels"
- Institutional HR docs synthesis

---

## The Voluntary Disclosures / Self Identify Step

### Why It Exists

Federal law (OFCCP) requires federal contractors and subcontractors to invite candidates to voluntarily self-identify demographic information. This includes:
- OFCCP Form CC-305 (disability)
- VEVRAA (veteran status)
- EEO-1 data (race/ethnicity)

Workday implements this as one or two steps near the end of the application wizard.

### Step Variants

**Single Step:** "Voluntary Disclosures" — all demographic fields in one page  
**Split Steps:**
1. "Voluntary Disclosures" — gender, race/ethnicity
2. "Self Identify" — disability, veteran status

Both variants occur; split is more common at larger enterprises (government contractors, Fortune 500).

---

## Field-by-Field Breakdown

### Gender

**Field label:** "Gender" or "Sex"  
**Type:** Dropdown or radio  
**Options (standard):**
- Male
- Female
- Non-Binary (not always present — newer addition)
- I prefer not to answer
- Decline to self-identify

### Race / Ethnicity

**Field label:** "Race/Ethnicity" or "Ethnic Background"  
**Type:** Dropdown (single select)  
**Options (EEO-1 standard):**
- American Indian or Alaska Native
- Asian
- Black or African American
- Hispanic or Latino
- Native Hawaiian or Other Pacific Islander
- White
- Two or More Races
- I choose not to self-identify

### Veteran Status

**Field label:** "Veteran Status" or "Protected Veteran Status"  
**Type:** Dropdown  
**Options (per VEVRAA):**
- I am a protected veteran
- I am not a protected veteran
- I do not wish to answer
- (Some variants): Active Duty Wartime or Campaign Badge Veteran / Armed Forces Service Medal Veteran / Disabled Veteran / Recently Separated Veteran (listed individually)

### Disability Status

**Field label:** "Disability Status" (per OFCCP CC-305 form language)  
**Type:** Radio or dropdown  
**Options:**
- Yes, I have a disability (or previously had a disability)
- No, I don't have a disability
- I don't wish to answer

**Additional disability context text (CC-305 language):** Workday often shows the full CC-305 legal form text including definitions of "disability" — this is a long block of legalese before the question.

---

## Behavioral Properties

1. **Legally voluntary** — candidates cannot be required to answer
2. **"I prefer not to answer" / "Decline to self-identify"** option always present for each field
3. **Does not affect application scoring or recruiter view** (legally mandated separation)
4. **Blocking behavior on some tenants:** Some Workday configurations prevent advancing to Review unless the candidate makes a selection in each field (even "prefer not to answer")
5. **Not Simplify's territory:** No autofill tool should touch these fields — doing so could constitute improper data submission

---

## Tier-3 Classification: Always Defer

These fields are classified as **Tier-3** (always skip / defer to human) because:
- Contain personally sensitive demographic data
- Legal compliance implications if filled incorrectly
- User must make an intentional choice
- No "correct" answer from candidate profile

**Agent behavior:**
1. Detect step name contains "Voluntary" or "Self Identify" or "Disclosures"
2. Check if any fields are marked required (*)
3. If blocking required field: select "I prefer not to answer" / "Decline" option
4. Route to NEEDS_REVIEW with note: "Voluntary disclosures step requires human review"
5. Never select substantive demographic answers (Male/Female/Race/etc.)

---

## Common Workday Field Selectors (for Playwright targeting)

The Voluntary Disclosures section typically renders as:
- Label text: "Gender", "Race/Ethnicity", "Veteran Status", "Disability"
- Each field is a `<select>` or radio group
- Step progress indicator shows "Voluntary Disclosures" or "Self Identify" in sidebar
- Can detect step by reading the `h1` or sidebar step label

---

## Sources

- [OSU Civil Rights: Voluntary Self-Identification of Disability](https://civilrights.osu.edu/about/focus-areas/voluntary-self-identification-disability)
- [Virginia Tech: Voluntary self-identification of veteran status](https://news.vt.edu/notices/2025/04/crcpe-selfid-veterans.html)
- [Lipstickalley forum: Voluntary disclosure questions](https://www.lipstickalley.com/threads/do-you-answer-any-of-the-voluntary-disclosure-questions-race-gender-disability-etc-when-applying.5728237/)
- WebSearch synthesis from OFCCP + Workday institutional HR documentation
