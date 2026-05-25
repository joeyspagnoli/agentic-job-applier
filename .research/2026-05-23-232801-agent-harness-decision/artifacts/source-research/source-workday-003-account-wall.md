# source-workday-003-account-wall.md

**Topic:** Workday "Create Account" wall — onboarding process details  
**Date fetched:** 2026-05-24  
**Sources consulted:**
- WebSearch: "Workday create account apply verify email password wall steps"
- https://www.refer.me/blog/workday-candidate-home-duplicate-profiles-fix-checklist
- https://careers.roche.com/global/en/candidate-account-creation
- https://careers.lilly.com/us/en/signin
- Workday Recruiting FAQs (institutional PDFs — binary, non-parseable)

---

## The Account Wall — What It Looks Like

When a user clicks "Apply" on a Workday job posting for the first time at a company, they hit a **pre-application gate** before any form fields are shown.

### Gate UI
- URL: `https://{tenant}.wd{N}.myworkdayjobs.com/{board}/login` or `/apply`
- Presents two options:
  1. **"Sign In"** — for returning candidates
  2. **"Create Account"** — for new candidates
- Also may show: **"Continue as Guest"** (rare, tenant-configured)

### Account Creation Form Fields
- Email Address
- Password (with requirements: min 8 chars, uppercase + lowercase + number + symbol — varies by tenant)
- Confirm Password
- (Some tenants) First Name + Last Name at creation time

### Email Verification Step
- After form submission: "Check your email" screen shown
- Verification email sent from Workday (sender varies by company tenant)
- Email contains a single-use verification link
- Clicking link → redirects back to Workday → now signed in → application flow begins

### Key Properties
- **Per-tenant isolation**: Each company's Workday deployment is a separate tenant
  - Applying to Microsoft and Salesforce requires TWO separate accounts
  - No shared Workday candidate identity across companies
- **No social login / Google Sign In** for candidates (enterprise SSO only for employees)
- Account persists for future applications at the same company

---

## Already-Have-Account Flow
- If user has previously applied at this company, they sign in with email + password
- Password reset available via "Forgot Password" link
- **Account-Already-Exists collision pattern**: If user applies with same email they used before, system recognizes them → proceeds directly to application form

---

## Duplicate Profile Problem

From refer.me analysis:
- Workday creates a new candidate profile rather than merging when identity fields don't match exactly
- Triggers:
  - Different email variants (name+tag@gmail.com vs name@gmail.com)
  - Phone format differences (+1-555-xxx vs 5551234xxx)
  - Name inconsistencies (Nick vs Nicholas)
- **No blocking mechanism** prevents duplicate account creation — users just accumulate multiple profiles
- Symptom: "Applied years ago, forgot the login, create a new account" → duplicate profile, prior application history lost

---

## What Happens After Account Creation

1. Email verified → signed in to Candidate Home
2. Candidate Home shows:
   - Active applications
   - Application statuses
   - Profile settings
3. User clicks on the job posting again (or is redirected)
4. Presented with **Application Start Method modal**:
   - Autofill with Resume
   - Apply Manually
   - Use My Last Application
5. Application wizard begins (My Information → ...)

---

## Implications for the Agent

- **The agent cannot create accounts** — email verification requires inbox access outside browser scope
- **Pre-condition**: User must have already created their Workday account at the target company before the agent engages
- If agent encounters the login wall, it must: detect "Sign In / Create Account" page → route to NEEDS_REVIEW
- If user is already signed in (persistent session), agent proceeds directly to Application Start modal
- **Session persistence**: If user has `staySignedIn` or cookies are alive from prior session, agent bypasses the wall automatically

---

## Simplify and the Account Wall

- No evidence Simplify handles account creation
- Simplify extension activates on form fields after the user is signed in
- Account creation wall is manual-only territory

---

## Sources

- [Process.st: How to Create a Workday Account](https://www.process.st/how-to/create-a-workday-account/)
- [Refer.me: Workday Candidate Home Duplicate Profiles Fix](https://www.refer.me/blog/workday-candidate-home-duplicate-profiles-fix-checklist)
- [Roche: Candidate Account Creation](https://careers.roche.com/global/en/candidate-account-creation)
- [Lilly Careers: Workday Login](https://careers.lilly.com/us/en/signin)
