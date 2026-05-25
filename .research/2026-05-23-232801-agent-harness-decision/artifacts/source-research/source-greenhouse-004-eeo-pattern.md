# Greenhouse — EEO / Demographic Questions Pattern

Sources: Greenhouse support docs, notchresume.com

## EEO Position in Greenhouse Application Flow

- **Location**: Bottom of the main application form — same page, before the Submit button
- **Not a post-submit page**: EEO appears inline within the application form, after all custom questions, before the final "Submit Application" button
- **Flow**: Personal info → Documents → Work history → Education → Custom questions → EEO/Demographics → Submit Application

## EEO Fields Collected

Standard U.S. demographic questions configured in Greenhouse:
- Gender identity
- Race / Ethnicity
- Veteran status
- Disability status

## Key Behavioral Properties

- Every demographic question includes a **"Decline to self-identify"** option
- Responses are **not visible to hiring managers or interview panels** during candidate review
- Data aggregated only for EEOC reporting and company-internal DEI analytics
- Filling or skipping EEO does NOT affect application submission — it is non-blocking
- Companies can enable both "custom demographic questions" AND standard EEOC questions; if both enabled, custom demographic set appears first, then EEOC

## Agent Guidance

- The EEO section can be safely skipped by selecting "Decline to self-identify" on all questions
- If Simplify fills it (via disability/EEO toggles), the agent does not need to touch it
- The agent should NOT interpret the EEO section as "blocking" — it is always optional
- After EEO, the submit button is the next/only remaining action

## reCAPTCHA Note (Greenhouse-specific failure mode)

Greenhouse uses **invisible reCAPTCHA** at form submission:
- Analyzes behavioral signals: mouse movements, typing patterns, scroll behavior
- If flagged → sends email verification code to candidate → **blocks submission until code entered**
- Playwright automation has elevated risk of triggering this because behavioral signals differ from human input
- Mitigation: using a headed browser with real user session (as the worker does) helps; Simplify's prior interactions add human-like signal

## Sources
- https://support.greenhouse.io/hc/en-us/articles/7541739987355-U-S-Standard-demographic-questions
- https://support.greenhouse.io/hc/en-us/articles/8292714720667-Collect-candidate-demographic-data
- https://support.greenhouse.io/hc/en-us/articles/115005448066-Invisible-reCAPTCHA
- https://notchresume.com/resources/greenhouse-job-application.html
