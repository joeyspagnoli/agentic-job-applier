# SmartRecruiters Real Board — Field & Structure Research

Source: https://careers.smartrecruiters.com/Pfizer (live fetch — "No job postings currently available")
Supplemented from: developers.smartrecruiters.com, SF.gov SmartRecruiters guide, SAP learning docs

## Board Page Structure
- URL pattern: `https://careers.smartrecruiters.com/[Company]` (old: `jobs.smartrecruiters.com/[Company]`, now 301-redirects)
- Board page shows job listings searchable by keyword and filterable by location
- **Candidate clicks a job → lands on a job detail page** within the careers.smartrecruiters.com domain
- Job detail page: full description + requirements + prominent **"I'm Interested"** button
  - This is the primary CTA button text on SmartRecruiters standard hosted pages
  - Some employers customize this to "Apply Now" or "Apply for this job"
- Clicking "I'm Interested" → reveals the application form inline on the same page (or navigates to `/apply`)

## Application Flow (Standard)

SmartRecruiters has two application modes:

### Standard Application (full form)
Multi-step or single-page form depending on employer configuration:

**Step 1 — Basic Info:**
| Field | Notes |
|-------|-------|
| First Name | Required |
| Last Name | Required |
| Email | Required |
| Phone | Configurable required |
| Place of Residence | City/region dropdown or postal code — configurable required |

**Step 2 — Experience:**
| Field | Notes |
|-------|-------|
| Work Experience | At least 1 entry if enabled as required |
| Education | At least 1 entry if enabled as required |
| Resume | Upload always available; required if Easy Apply disabled |

**Step 3 — Additional:**
| Field | Notes |
|-------|-------|
| Message to Hiring Manager | Configurable required |
| Custom Screening Questions | Per-job, varies 0–10 |

**Step 4 — Review & Submit:**
- Review summary
- **"Submit" or "Submit Application"** button (varies by employer config)

### Easy Apply (simplified)
- Stays on the job search platform; uses pre-filled profile data
- Resume upload always available and cannot be deactivated in Easy Apply mode
- Fewer fields; submits existing profile data directly

## Submit Button Text
- Standard hosted form: **"Submit"** or **"Submit Application"** at final review step
- Job detail page primary CTA: **"I'm Interested"** (this triggers the form, not submits it)
- Easy Apply: may show "Apply" directly
- IMPORTANT: "I'm Interested" is NOT the submit button — it's the trigger to open/start the form

## Key Navigation Note
- source_url for SmartRecruiters jobs typically points to the job detail page (with "I'm Interested" button)
- Agent must click "I'm Interested" first, THEN fill the form, THEN click Submit
- This is one extra click vs. being directly on a form

## Sources
- https://careers.smartrecruiters.com/Pfizer (fetched — no active listings)
- https://www.smartrecruiters.com/resources/glossary/easy-apply-job-applications/
- https://learning.sap.com/courses/smartrecruiters-for-sap-successfactors-academy/configuring-application-fields
- https://developers.smartrecruiters.com/docs/post-an-application
- https://www.sf.gov/sites/default/files/2022-04/SmartRecruiters%20Guide%20final%20V2.pdf
