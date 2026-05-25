# Lever — EEO / Demographic Questions Pattern

Sources: Lever help docs

## EEO Position in Lever Application Flow

- **Location**: Lever renders EEO questions **at the END of the application form**, after all custom questions
- For multi-location postings: EEO survey is **dynamically rendered at the end of the application** based on the preferred/selected location
- The EEO survey is presented as a **continuation of the same form**, not as a post-submit separate step
- Evidence: Lever help doc language — "the survey will be dynamically rendered at the end of the application for the applicant to complete"

## EEO Fields Collected (typical)
- Gender
- Race / ethnicity
- Veteran status
- Disability status

## Key Behavioral Properties

- EEO questions are **voluntary** — all have an option to decline
- Data used only for EEOC compliance reporting — not shared with hiring team for evaluation
- Non-blocking: skipping all EEO questions does not prevent form submission
- The EEO section appears with a header clearly labeling it as voluntary demographic data

## Submit Button Relationship
- "Submit application" button appears AFTER the EEO section on the form
- The EEO section must be scrolled past to reach the submit button
- Agent/automation should recognize EEO section by looking for "voluntary", "demographic", "EEOC", "race", "gender" headers and skip them (select "prefer not to say" / "decline") rather than treating them as blocking fields

## Sources
- https://help.lever.co/hc/en-us/articles/20087340764701-Configuring-and-using-equal-employment-opportunity-EEO-questions
- https://lever-old.zendesk.com/hc/en-us/articles/115000312143-Using-equal-employment-opportunity-EEO-questions
