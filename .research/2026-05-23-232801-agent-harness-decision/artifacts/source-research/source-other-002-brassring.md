# Source: Brassring (Infinite BrassRing / formerly IBM Kenexa BrassRing) Apply Form Steps

## Key Findings

### Overview
BrassRing (now "Infinite BrassRing" after IBM's Kenexa divested it to Infinite Computer Solutions) is used primarily by very large enterprises: defense contractors, major law firms, financial services. Notable users include A&O Shearman. 

IBM ended support for the original Kenexa BrassRing on Cloud; support transferred to Infinite (infinitetalent.force.com).

### Landing Behavior
BrassRing job listings on the company's Talent Gateway (TG) land on a job detail page. The "Apply" button leads to a candidate account creation page.

### Account Creation
- Required: YES by default for all standard BrassRing deployments
- **However**: BrassRing introduced a "Skip Sign-in" feature in the September 2018 release for Responsive Talent Gateways: 
  > "Clients can now choose to enable their Responsive Talent Gateways to allow candidates to skip the account creation process and instead, apply directly to jobs."
- Whether "Skip Sign-in" is enabled is employer-configurable; most enterprise deployments still require accounts

### Multi-Step Application Structure
BrassRing Responsive Apply flow (standard):
1. **Sign In / Create Account** (or Skip if enabled)
2. **Resume Upload** — parses into profile fields
3. **Basic Info** — contact, address, work authorization
4. **Work History** — structured employer/title/date blocks
5. **Education** — degree, institution, dates
6. **Custom Questions** — employer-defined screening questions (BrassRing supports highly complex logic-branching question trees)
7. **EEO/OFCCP** — at end (BrassRing has robust OFCCP compliance tooling for US federal contractors)
8. **Preview / Submit**

### Known Characteristics
- BrassRing's question trees can be extremely long (government contractors sometimes have 30+ questions)
- BrassRing uses its own CAPTCHA-like validation in some enterprise deployments
- The "Social Media Share Button" was removed in 2018 for clients with Social Media functionality enabled

### Simplify Coverage
BrassRing is NOT in Simplify's covered ATS list. Given the niche enterprise user base and complex rendering, automation coverage is very limited.

### v1 Recommendation: DEFER
BrassRing is disproportionately used by defense/government contractors and large law firms. For a general-purpose job applier targeting tech/business roles, BrassRing penetration is low. The extreme configurability and question complexity make it a poor v1 candidate. Recommend deferring.

### Sources
- IBM Kenexa BrassRing on Cloud Release Document (September 2018) — Skip Sign-in feature
- IBM Kenexa BrassRing on Cloud: transferred to Infinite Computer Solutions for support
- List of Infinite BrassRing customers (A&O Shearman, enterprise clients)
- BrassRing HackerRank integration documentation
