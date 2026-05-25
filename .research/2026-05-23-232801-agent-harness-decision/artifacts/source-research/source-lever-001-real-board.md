# Lever Real Board — Field & Structure Research

Source: https://jobs.lever.co/figma (403 on direct fetch — Lever blocks scrapers), https://jobs.lever.co/notion (403)
Supplemented from: Lever help docs, postings API docs, JobWizard blog

## Board Page Structure
- URL pattern: `https://jobs.lever.co/[company]`
- Board page lists all open roles (title, team, location, type)
- **Candidate clicks a job title → lands on a Lever-hosted job detail page**
  - URL format: `https://jobs.lever.co/[company]/[job-uuid]`
  - Page shows: job description + responsibilities + requirements
  - **"Apply for this job" button appears prominently at the top AND bottom of the job description**
  - Clicking button either (a) expands an inline form below the description, or (b) navigates to a separate `/apply` subpath: `https://jobs.lever.co/[company]/[job-uuid]/apply`
- The apply URL path is distinct — the apply form is on its own route, not embedded inline

## Typical Application Form Fields

### Required by Default (system-enforced, cannot be removed)
| Field | Notes |
|-------|-------|
| Full Name | Required, cannot be deleted |
| Email | Required, cannot be deleted |

### Standard Optional Fields (employer can make required)
| Field | Notes |
|-------|-------|
| Phone | Toggle required on/off |
| Current Company | Text field |
| Current Location | Text field / geocomplete |
| LinkedIn URL | Link-type field |
| GitHub URL | Link-type field |
| Twitter/X URL | Link-type field |
| Personal Website | Link-type field |
| Resume | File upload (multipart only, up to 100MB per file) |
| Additional Information / Cover Letter | Long text or file upload |
| Comments / "Anything else?" | Free text textarea |

### Custom Questions (employer-configured, per job)
- Range: 0–8 custom questions typical for tech roles
- Scoped per job posting (not universal like personal info)
- See source-lever-003-custom-questions.md for types

## Submit Button
- Default text: **"Submit application"** (lowercase 'a' — confirmed from Lever API and postings)
- Some implementations show "Apply for this job" on the detail page button that leads to form

## Page Navigation Path
1. `jobs.lever.co/[company]` → list view
2. Click job → `jobs.lever.co/[company]/[uuid]` → job detail with "Apply for this job" button
3. Click apply button → `jobs.lever.co/[company]/[uuid]/apply` → application form
- **Two clicks from board listing to form** (not direct-to-form from source_url if source_url = job detail page)
- If source_url points directly to `/apply` route → **one click** (just fill and submit)

## Sources
- https://github.com/lever/postings-api/blob/master/README.md (API field spec)
- https://help.lever.co/hc/en-us/articles/20087243347741-Configuring-your-Lever-application-form
- https://jobwizard.ai/blog/how-to-autofill-lever-job-applications-with-jobwizard
