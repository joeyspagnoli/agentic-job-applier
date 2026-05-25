# SmartRecruiters — Custom Application Questions Research

Sources: SAP learning docs, developers.smartrecruiters.com

## Custom Question Types in SmartRecruiters

SmartRecruiters supports two levels of screening questions:

### Screening Questions (per job)
- Yes/No
- Single select (dropdown/radio)
- Multi-select (checkboxes)
- Free text (short answer)
- Number
- Date

### Custom Application Fields (account-level configuration)
Per the developer docs, field types include custom fields beyond the standard set.

## Required vs Optional
- Only fields that are strictly required: `firstName`, `lastName`, `email`, and `answers` (if there are required screening questions)
- All other fields (phone, location, experience, education) are configurable as required or optional per employer

## Typical Custom Question Examples

### Universal / Almost Always Present
- Work authorization and visa sponsorship (yes/no knockouts)
- "How did you hear about this role?" (dropdown)

### Common
- Salary / compensation expectations
- Availability / start date
- Location preference or willingness to relocate
- "Briefly describe why you're interested in this role" (short or long text)

### Less Common
- Role-specific technical questions
- "Message to Hiring Manager" (when enabled as a required field)
- Portfolio or work sample links

## Volume
- Typical SmartRecruiters enterprise jobs: 2–6 custom screening questions
- Large enterprise companies (Pfizer, etc.) may have more complex screening with multiple required questions plus compliance fields

## Key Difference from Greenhouse/Lever/Ashby
SmartRecruiters is predominantly used by large enterprises (Pfizer, Bosch, etc.) vs. tech startups. Custom questions tend to be more compliance-oriented (work auth, drug testing, background check consent) and less essay-oriented.

## Sources
- https://learning.sap.com/courses/smartrecruiters-for-sap-successfactors-academy/configuring-application-fields
- https://developers.smartrecruiters.com/docs/post-an-application
- https://developers.smartrecruiters.com/docs/customfield
