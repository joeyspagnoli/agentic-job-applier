# SmartRecruiters — EEO / Demographic Questions Pattern

Sources: developers.smartrecruiters.com, SAP learning docs

## EEO Position in SmartRecruiters Application Flow

- SmartRecruiters recommends placing diversity/demographic questions in a section labeled "Confidential Diversity Questions"
- Instructional text above the section: "Any information you choose to provide will not be considered for employment purposes and will be treated as confidential."
- **Position**: End of the application form, after all required screening questions, before the final submit button
- Best practices note that demographic information should be "kept separate from an application as a candidate proceeds through the hiring process"
- Some SmartRecruiters deployments place the EEO survey as a completely separate post-submit page (especially for government/OFCCP-compliant employers)

## EEO Fields (when enabled)
- Gender
- Race / ethnicity
- Veteran status
- Disability status
- All responses are voluntary ("Your voluntary cooperation will be appreciated")

## Key Behavioral Properties

- Completely voluntary — explicitly labeled as not affecting hiring decisions
- Not universally enabled — depends on employer configuration
- Large enterprises (healthcare, pharma, government contractors) more likely to have EEO section
- Data kept separate from resume review pipeline
- May appear as part of main form OR as a separate post-submit step depending on employer config

## Submit Button Text Clarification

SmartRecruiters uses a two-step CTA:
1. **"I'm Interested"** — On the job detail page (NOT a submit; this opens the application form)
2. **"Submit"** or **"Submit Application"** — At the end of the filled application form (the actual submit)

The agent/deny-list must differentiate between these two buttons. "I'm Interested" should be clicked to OPEN the form; "Submit" should be clicked to COMPLETE the application.

## Sources
- https://developers.smartrecruiters.com/docs/post-an-application
- https://learning.sap.com/courses/smartrecruiters-for-sap-successfactors-academy/configuring-application-experience
