# Lever — Simplify Copilot Coverage Research

Sources: Simplify docs, JobWizard Lever blog, review sites

## What Simplify Fills on Lever

From the Lever API field spec + community reports, Simplify populates:
- Full Name
- Email
- Phone
- Current Company
- Current Location
- LinkedIn URL
- GitHub / personal website URLs (if stored in profile)
- Resume (uploads stored file)
- Work Authorization status (stored answer, toggleable)

Lever applications have been described as handling "multi-step applications smoothly" — standard field accuracy is high.

## What Simplify Misses on Lever

1. **Custom application questions** — All employer-configured questions are missed:
   - Open-text essays: "Describe a challenge you overcame"
   - Role-specific short answers: "Preferred start date", "What interests you about Notion?"
   - Custom dropdowns the tool doesn't have mappings for

2. **"Additional Information" / Comments field** — Often not filled (Simplify doesn't generate cover-letter-style text on free tier)

3. **Cover letter** — Lever doesn't have a separate cover letter field by default; it's added as a custom file upload question. Simplify may not upload a cover letter unless specifically configured.

4. **Wrong-field carryover** — Reported issue: custom open-text fields from a previous application getting copied into unrelated fields

5. **Current Company** — Occasionally missed or pulled from stale profile data

## AI Fill for Custom Questions
- Simplify+ paid tier offers AI-generated suggestions for open-ended questions
- Free tier: manual entry required for all custom questions

## Sources
- https://help.simplify.jobs/articles/8686025-manage-autofill-settings-in-the-simplify-extension
- https://jobwizard.ai/blog/how-to-autofill-lever-job-applications-with-jobwizard
- https://hirepilot.co/simplify-extension-review-does-it-actually-work/
