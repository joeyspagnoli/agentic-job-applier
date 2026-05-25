# Greenhouse Real Board — Field & Structure Research

Source: https://job-boards.greenhouse.io/anthropic (live fetch, 392 jobs visible)

## Board Page Structure
- URL pattern: `https://job-boards.greenhouse.io/[company]` (old: `boards.greenhouse.io/[company]`, now 301-redirects)
- Board page lists jobs grouped by department with pagination
- **Candidate clicks a job title → lands on a job detail page** that contains:
  1. Full job description (scrollable)
  2. An "Apply for this job" or "Apply now" button (text can be customized up to 25 chars by employer)
  3. Clicking the apply button **scrolls to or reveals the inline application form on the same page**
- The apply form and job description are on the same hosted URL — no separate domain hop for the form itself

## Typical Application Form Fields (ordered as they appear)

### Page 1 — Personal Info
| Field | Required? |
|-------|-----------|
| First Name | Yes |
| Last Name | Yes |
| Email | Yes |
| Phone | Usually yes |
| Location | Yes |
| LinkedIn URL | Optional (some employers require) |
| "How did you hear about us?" | Usually required (dropdown) |

### Page 2 — Documents
| Field | Required? |
|-------|-----------|
| Resume upload (PDF/DOCX) | Yes |
| Cover letter | Optional (varies by job — sometimes required) |
| Portfolio / website URL | Optional |

### Page 3 — Work History & Education
Auto-parsed from resume; candidate reviews/confirms:
- Job title, Company, Dates, Location, Description
- Degree, School, Graduation year

### Page 4 — Custom Questions (employer-configured, 0–12 questions)
Common types:
- Yes/No knockout questions: "Are you legally authorized to work in the US?" / "Will you now or in the future require sponsorship?"
- Short text: salary expectations, preferred start date
- Long-form essay: "Why do you want to work here?", "Describe a challenge you overcame"
- Dropdown: "What is your highest level of education?", "Years of experience in X?"
- File upload: portfolio, writing sample

### Page 5 — Demographic / EEO Section
- Appears **at the bottom of the form on the same page**, BEFORE the final submit button
- Includes: gender, race/ethnicity, veteran status, disability
- Every question has "Decline to self-identify" option
- Data NOT visible to hiring team during review (aggregated for EEOC reporting only)
- Hiring team notes this is NOT a separate post-submit flow — it is part of the main form

## Submit Button
- Default text: **"Submit Application"**
- Appears at the bottom after all form sections including EEO
- reCAPTCHA note: Greenhouse uses **invisible reCAPTCHA** (analyzes mouse/typing patterns)
  - On detection of bot-like behavior: may email a verification code, blocking submission
  - Risk for Playwright automation — behavioral signals differ from human input

## Supported File Types (Resume)
- PDF, Word (.doc/.docx), RTF, TXT
- Max size: 500MB per upload
- Parser extracts: name, email, phone, LinkedIn, work history, education

## Source
- https://job-boards.greenhouse.io/anthropic (fetched)
- https://notchresume.com/resources/greenhouse-job-application.html
- https://support.greenhouse.io/hc/en-us/articles/115005448066-Invisible-reCAPTCHA
- https://support.greenhouse.io/hc/en-us/articles/360025222851-Add-a-custom-application-question-to-a-job-post
- https://www.jobpilotapp.com/blog/automate-greenhouse-applications
