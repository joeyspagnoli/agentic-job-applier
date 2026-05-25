# Ashby Real Board — Field & Structure Research

Source: https://jobs.ashbyhq.com/ashby (fetched — rendered as "Ashby Jobs" title only, JS-heavy)
Supplemented from: developers.ashbyhq.com, docs.ashbyhq.com, jobwizard.ai/ashby blog

## Board Page Structure
- URL pattern: `https://jobs.ashbyhq.com/[company]`
- Ashby job boards are **heavily JavaScript-rendered** — the raw HTML fetch shows minimal content
- Board page displays job listings by department/team
- **Candidate clicks a job → lands on a job detail page** at `https://jobs.ashbyhq.com/[company]/[job-uuid]`
- Job detail page contains: job description + requirements + an **"Apply" button**
- Clicking Apply navigates to the application form, either:
  - On the same page (embedded form scrolls into view), or
  - At `https://jobs.ashbyhq.com/[company]/[job-uuid]/application`
- Ashby supports both embedded (company website) and hosted (jobs.ashbyhq.com) versions

## Typical Application Form Fields

From Ashby API docs + jobwizard.ai analysis:

### Standard Fields (always present)
| Field | Required? |
|-------|-----------|
| First Name | Yes |
| Last Name | Yes |
| Email | Yes |
| Phone | Usually yes |
| Location / City | Yes |
| LinkedIn Profile URL | Often required (Ashby auto-populates candidate profile) |
| Portfolio / Personal Website | Optional |
| Resume upload | Yes (max 16MB for parsing; 50MB for upload) |

### Work Experience
- Company, Title, Dates, Description (auto-parsed from resume)

### Education
- Institution, Degree, Field of study, Graduation date (auto-parsed)

### Custom Screening Questions
- Ashby companies are noted for "thoughtful screening questions — more so than traditional enterprise ATS platforms"
- Typical count: 2–8 questions
- Types: short answer, long-form, multiple choice, yes/no, dropdown, file upload

## Submit Button
- Default text: **"Submit Application"** (confirmed via developers.ashbyhq.com embed examples)
- Ashby API endpoint for submission: `POST /applicationForm.submit`

## Field Types in Ashby API
- Boolean, Date (YYYY-MM-DD), Email, Number, RichText (plain text via API), Score (1-4), Phone/String, ValueSelect (single choice), MultiValueSelect (array), Location (country/city/region), EducationHistory

## Key Structural Note
Ashby's LinkedIn URL field auto-populates the candidate's profile and is stored for reuse across future applications — this makes it particularly important to fill correctly.

## Sources
- https://developers.ashbyhq.com/reference/applicationformsubmit
- https://www.jobwizard.ai/post/how-to-autofill-ashby-job-applications-with-ai
- https://www.ashbyhq.com/job-board-embed-examples/application-form-only
- https://docs.ashbyhq.com/application-forms
