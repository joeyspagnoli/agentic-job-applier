# Ashby — Simplify Copilot Coverage Research

Sources: Simplify docs, hirepilot.co review, jobwizard.ai (competitor perspective)

## Simplify Support for Ashby
- Simplify claims support for "over 100 job boards and application portals" and 20,000+ career pages
- Ashby is a supported platform but community documentation is sparse compared to Greenhouse/Lever

## What Simplify Likely Fills on Ashby

Based on Ashby's standard field structure and Simplify's known capabilities:
- First Name, Last Name (from profile)
- Email
- Phone
- Location
- LinkedIn URL (important for Ashby — auto-populates candidate profile)
- Resume (file upload)
- Work Authorization (if stored)

## What Simplify Misses on Ashby

1. **Custom screening questions** — The primary miss, same as all ATS:
   - Ashby's custom questions are notably more thoughtful/essay-oriented than enterprise ATS
   - "Why are you interested in this role?" (very common)
   - "Tell us about a time you worked cross-functionally"
   - Ashby companies are growth-stage tech (Ramp, OpenAI, etc.) which tend to have more elaborate screening

2. **Resume upload re-requirement** — Ashby forms require resume upload even if profile has one; autofill tools may not trigger the file picker correctly on Ashby's React-based form

3. **Portfolio / website URL** — Sometimes missed if not in Simplify profile

4. **Multi-select / checkbox custom questions** — Inconsistent handling of Ashby's MultiValueSelect field type

## Ashby-Specific Complication for Autofill
Ashby forms are heavily JavaScript-rendered (React) with controlled form components. Autofill tools (including Simplify and browser-native autofill) have higher miss rates on React-controlled inputs because the DOM events must be dispatched correctly to trigger React's state update. This is a more significant problem on Ashby than on Greenhouse or Lever.

## Sources
- https://help.simplify.jobs/articles/8686025-manage-autofill-settings-in-the-simplify-extension
- https://www.jobwizard.ai/post/how-to-autofill-ashby-job-applications-with-ai
- https://hirepilot.co/simplify-extension-review-does-it-actually-work/
- https://developers.ashbyhq.com/reference/applicationformsubmit
