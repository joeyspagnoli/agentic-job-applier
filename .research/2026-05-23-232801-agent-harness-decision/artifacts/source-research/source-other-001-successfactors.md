# Source: SAP SuccessFactors Apply Form Steps

## Key Findings

### Overview
SAP SuccessFactors Recruiting (formerly SuccessFactors Recruiting Management) is used primarily by large enterprises (SAP customers, Fortune 500). It powers career portals at major corporations in manufacturing, healthcare, automotive, and finance.

### Landing Behavior
SuccessFactors job listings typically land on a branded career portal. The apply button requires account creation (standard candidate profile). Some SuccessFactors deployments use the company's SSO (e.g., SAP ID Service), others use local SuccessFactors credentials.

### Account Creation
- Required: **YES** — candidates need a SuccessFactors candidate profile
- Profile is company-scoped (each company's SF instance is separate)
- Options: email/password or often company SSO integration
- Email verification: typically required

### Multi-Step Application Structure
From SAP SuccessFactors Recruiting documentation:
1. **Candidate Profile** — personal info, contact, work authorization
2. **Résumé Upload** — with auto-parsing into profile fields (SF has built-in parsing)
3. **Application Form** — job-specific fields configured by the employer
4. **Questions** — screening questions, background questions
5. **Attachments** — cover letter, portfolio, certifications
6. **EEO / OFCCP** — at the end (if employer is US federal contractor)
7. **Review & Submit**

### Resume Parsing Quality
SuccessFactors has evolved its resume parsing. As of 2024–2025, it uses an AI-assisted parser that pre-fills work history and education with reasonable accuracy. However, field IDs in SF's XML configuration must match for sync to work correctly.

### Field Naming / Customization
SuccessFactors is **highly configurable**. Employers can add custom fields, rename standard fields, and require non-standard data points. This makes it harder for generic autofill tools to cover reliably.

### Simplify Coverage
SuccessFactors is NOT in Simplify's commonly cited ATS list. Community reports suggest Simplify has **minimal coverage** on SuccessFactors — the non-standard field names and iframe-heavy rendering make DOM-based autofill unreliable.

### v1 Recommendation: DEFER
SuccessFactors is encountered less frequently for the typical mid-market job seeker (it skews enterprise/F500). The high customization variability, SAP-specific rendering, and lack of Simplify support makes it a poor v1 candidate. Recommend deferring to v2+.

### Sources
- SAP SuccessFactors Recruiting and Onboarding documentation
- SAP SuccessFactors "Job Applications" help article
- SAP SuccessFactors "Configuring Application Fields" documentation
- Simplify Copilot 2026 reviews: SuccessFactors not in supported ATS list
