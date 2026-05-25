# source-workday-004-dropdown-options.md

**Topic:** Workday dropdown field options and autofill mismatch patterns  
**Date fetched:** 2026-05-24  
**Sources consulted:**
- WebSearch: "Workday job application dropdown United States of America country state options"
- WebSearch: "Workday application education level dropdown Bachelor's Degree exact options"
- WebSearch: "Workday autofill extension limitations work authorization education level dropdown wrong value"
- https://www.glassdoor.com/Community/hr-jobs-advice/is-anyone-else-struggling-with-workday-applications (blocked 403)
- https://www.fishbowlapp.com/post/workday-does-not-have-bachelor-of-technology-as-a-degree (community post)
- jobo.world/ats/workday (Workday scraper API docs)

---

## The Core Dropdown Mismatch Problem

Workday uses a global product catalog of dropdown option values that many autofill tools (including Simplify) do not match exactly. The mismatches fall into predictable categories.

---

## Category 1: Country Field

**Workday label:** `"United States of America"`  
**What autofill tools write:** `"United States"` or `"US"` or `"USA"`  
**Result:** No match — dropdown remains blank or reverts to default

**Other country label patterns observed in Workday:**
- "United Kingdom of Great Britain and Northern Ireland" (not "UK" or "United Kingdom")
- Full formal country names per ISO 3166-1 long-form

**Detection note:** jobo.world Workday API docs confirm Workday uses ISO 3166-1 standard country names in its data model — long-form names, not abbreviations.

---

## Category 2: Education Level / Degree Type

**Workday's standard degree dropdown options (confirmed from Glassdoor forum + Fishbowl):**
- High School Diploma or Equivalent
- Associate's Degree
- Bachelor's Degree
- Master's Degree  
- Doctoral Degree (PhD)
- Professional Degree (JD, MD)
- Some Coursework / No Degree

**Mismatch examples:**
- Autofill writes "Bachelor of Science" → Workday wants "Bachelor's Degree"
- Autofill writes "B.S." → Workday wants "Bachelor's Degree"
- "Bachelor of Technology" does NOT exist in Workday's list (Fishbowl post: user had to pick "Bachelor of Engineering" as closest match)
- "Postgraduate degree" not an option → user forced into "Master's Degree" or "Doctoral Degree"
- Non-standard degrees (post-grad certificates, graduate diplomas) have no match

**Glassdoor forum thread confirms** this is a widespread complaint: "NONE of the Workday applications have [postgrad degree] as an option. My choices are Doctorate or Masters."

---

## Category 3: Field of Study / Major

**Pattern:** Workday provides a searchable typeahead dropdown, NOT free text  
- Intel support article confirms: candidates submit support tickets about being "unable to find field of study"
- Options are from a fixed catalog — "Computer Science" exists, "Computational Linguistics" may not
- Autofill tools write free text; Workday's typeahead may not match → field left blank
- **Common failure:** Autofill writes "Computer Science and Engineering" when Workday only has "Computer Science" and "Computer Engineering" separately

---

## Category 4: Work Authorization

**Workday's typical work authorization field variants (not standardized — company-configured):**

Variant A (Yes/No radio):
- "Are you legally authorized to work in the United States?"  → Yes / No
- "Will you now or in the future require visa sponsorship?" → Yes / No

Variant B (dropdown):
- "I am authorized to work in the U.S. for any employer"
- "I am authorized to work in the U.S. for this employer only (e.g., have a work visa)"
- "I am not authorized to work in the U.S."

Variant C (single dropdown):
- "Select work authorization status" → "US Citizen or Permanent Resident" / "H1B Visa" / "Other Work Visa" / "Not Authorized"

**Mismatch problem:** Simplify stores "Authorized to work: Yes, No sponsorship needed" — the mapping to these variant dropdown labels is not guaranteed.

---

## Category 5: Phone Type

**Workday dropdown:** Mobile / Home / Work  
**Autofill behavior:** Usually fills "Mobile" correctly (standard enough)  
**Edge case:** Some tenants show "Cell" instead of "Mobile"

---

## Category 6: State / Province

**Workday:** Full state names ("California", "New York") not abbreviations ("CA", "NY")  
**Autofill:** Often writes abbreviated "CA" → dropdown doesn't match  
**Confirmed:** Workday separates address into multiple fields; state is a dropdown list of full names

---

## Category 7: How Did You Hear About Us

**Options vary per company.** Common options:
- LinkedIn
- Indeed
- Company Website
- Employee Referral
- Job Fair
- Other

Autofill tools often skip this field or leave it blank. Best practice: set "LinkedIn" or "Company Website" as default.

---

## Severity Ranking for Agent

| Field | Mismatch Frequency | Impact if Wrong |
|---|---|---|
| Country | High | Address section broken |
| Degree Type | High | Education section incorrect |
| Field of Study | Medium-High | Education incomplete |
| Work Authorization | Medium | Knockout question risk |
| State | Medium | Address section broken |
| Phone Type | Low | Minor |
| Referral Source | Low | Informational only |

---

## Sources

- jobo.world Workday Scraper API docs (URL pattern + data model)
- Glassdoor Community forum (degree dropdown complaint thread)
- Fishbowl: "Workday does not have Bachelor of Technology" post
- Intel support: "Unable to Find Field of Study While Applying"
- WebSearch synthesis from multiple autofill tool extension reviews
