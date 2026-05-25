# Source: iCIMS Account Wall — Create Profile Before Apply

## Key Findings

### Hard Account-Creation Requirement
iCIMS officially documents that **all candidates must have a login and profile** before they can apply. This is not a soft gate — there is no "apply as guest" option in standard iCIMS deployments.

From iCIMS Community documentation (primary source):
> "If you use iCIMS Applicant Tracking as your ATS, candidates are required to have a login to access the candidate portal and a profile to apply to jobs."

### What the Account Wall Looks Like
When a candidate hits "Apply Now" on an iCIMS job listing:
1. Redirected to a login/create account modal or page
2. Options: "Sign In" (existing account) | "Create Account" (new) | "Sign in with LinkedIn/Google" (SSO)
3. For new accounts: email, password, confirm password — then immediate redirect to profile creation
4. Profile creation: resume upload (optional but strongly promoted), basic contact fields
5. Only after profile is created does the job-specific application form appear

### Email Verification Step
Email verification is **NOT always required immediately** in iCIMS — some deployments allow the candidate to complete the application first and verify email later. However, some employer configurations DO require email verification before the application form loads.

### Password Requirements
Standard web security requirements — minimum 8 characters, typically one uppercase, one number. Not configurable by employers in standard iCIMS.

### Time Cost of Account Creation
- Fast path (SSO login, existing account): ~30 seconds
- New account creation without resume upload: ~2–3 minutes
- New account with resume upload and parsing: ~4–6 minutes (parsing can take 30–60 seconds)

### Duplicate Profile / Orphan Account Problem
Known user-reported issue: applying with different email addresses creates duplicate iCIMS profiles. The system does NOT automatically merge them. Symptoms:
- "You've already applied to this position" error on second attempt
- Application status showing "Incomplete" when the user thinks they completed it (submitted under wrong profile)
- Support requires manual profile merge by company HR admin

### Known Failure Mode: "Application Incomplete" Despite Completion
Reddit r/recruiting thread (2023): Multiple reports of iCIMS showing "Incomplete" status after the candidate believed they completed the full application. Root cause is usually a required field in a section that was not visible until the candidate scrolled, or a file attachment that was removed during parsing.

### Sources
- iCIMS Community: "Getting Started with iCIMS Career Sites" (primary source, admin documentation)
- iCIMS Community: "Candidate Guide to iCIMS Career Portals" (candidate-facing docs)
- Reddit r/recruiting (2023): "i applied to a job using ICIMS, i filled the application top to bottom... application status says incomplete"
- Reddit: duplicate iCIMS profile issue thread
