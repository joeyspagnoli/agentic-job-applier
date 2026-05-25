# Ashby — Custom Application Questions Research

Sources: docs.ashbyhq.com, developers.ashbyhq.com, jobwizard.ai

## Custom Question Field Types in Ashby

From the official Ashby documentation on application forms:

| Type | Description |
|------|-------------|
| Short answer | Single line of unformatted text |
| Long answer | Multiple lines, unformatted |
| Phone | Domestic or international phone |
| Email | Valid email address |
| Multiple choice | Select single option (ValueSelect) |
| Checkboxes | Select multiple options (MultiValueSelect) |
| Date | Date picker |
| Yes/No | Boolean toggle |
| Number | Whole number or decimal |
| Resume | Single file upload |
| Location (candidate's) | Auto-geolocate or manual entry |
| Other location | Secondary location field |
| Referral URL | For referral tracking |
| File upload | Generic file, up to 50MB |
| Education history | Structured education entry array |
| LinkedIn URL | Auto-populates candidate profile |

## Custom Question Volume
- Ashby-powered companies (typically growth-stage tech: Ramp, OpenAI, Brex, etc.) tend to have 3–8 custom questions
- Notable characteristic: Ashby companies ask more open-ended qualitative questions vs. the yes/no knockout style common on legacy enterprise ATS

## Typical Custom Question Examples

### Very Common (nearly universal)
- "Why are you interested in this role?" (long-form, required)
- "How did you hear about this role?" (dropdown or short text)
- Work authorization / sponsorship questions (yes/no)

### Common at Growth-Stage Companies
- "Tell us about a time you worked cross-functionally" (essay)
- "What is a project you're most proud of?" (essay)
- "Describe your experience with [specific stack/domain]" (long-form)
- "What is your expected compensation?" (short text or number)
- "Are you open to working in-office [location] X days/week?" (yes/no or dropdown)

### Less Common but Present
- Portfolio / work samples (file upload)
- GitHub / personal site (URL field)
- Referral source (who referred you)
- "What does [company mission] mean to you?" (essay)

## Form Field Connectors (Ashby Feature)
Ashby has a "Form Field Connectors" feature that maps application question answers directly to structured candidate profile fields. This means employer-side filtering on answers is more powerful than traditional ATS, but it also means applicants must match expected value formats (e.g., correct format for location, correct option text for dropdowns).

## Sources
- https://docs.ashbyhq.com/application-forms
- https://www.ashbyhq.com/product-updates/form-field-connectors
- https://www.jobwizard.ai/post/how-to-autofill-ashby-job-applications-with-ai
- https://developers.ashbyhq.com/reference/applicationformsubmit
