# Ashby — EEO / Demographic Questions Pattern

Sources: docs.ashbyhq.com, developers.ashbyhq.com

## EEO Position in Ashby Application Flow

- Ashby supports optional survey forms that can be configured to collect EEOC/demographic questions
- **Location**: Demographic questions are configured as a separate optional survey, typically presented at the **end of the application form**, before the submit button
- Ashby can infer candidate demographics OR rely on self-reported data for DEI tracking
- Not all Ashby employers enable the EEO survey — many growth-stage companies omit it entirely
- When present, it appears as a labeled voluntary section at the form bottom

## EEO Fields (when enabled)
- Gender identity
- Race / ethnicity
- Veteran status
- Disability status
- All with "prefer not to answer" option

## Key Behavioral Properties

- Completely voluntary — skipping does not block submission
- Ashby's EEO survey is configurable per company and is not universally present
- For companies that DO include it (often companies with government contracts or larger headcount), it appears inline before the Submit button
- Data not used in hiring decisions

## Agent Guidance

- The EEO section in Ashby may be absent entirely (most common case for small/growth companies)
- When present, select "prefer not to answer" on all fields and proceed to Submit
- Ashby's submit button ("Submit Application") is visible after all form sections

## Sources
- https://docs.ashbyhq.com/application-forms
- https://developers.ashbyhq.com/docs/public-job-posting-api
