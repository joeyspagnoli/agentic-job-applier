# Source: Simplify Copilot Coverage on iCIMS

## Key Findings

### Simplify's Claimed Coverage
Simplify Copilot (March 2026 data from Scale.jobs) claims autofill support across **20,000+ career pages and popular ATSes** including Workday, Lever, Greenhouse. iCIMS is **not explicitly listed** in the top-tier ATS coverage list in most reviews.

From r/recruitinghell Reddit thread:
> "It definitely helps a lot on sites like Workday, Taleo, Lever, Greenhouse. It does a fairly decent job of auto-inserting your background and education."

iCIMS is notably absent from the "works well" list in community reports. This is likely because:
1. iCIMS requires an account login BEFORE the form loads, so Simplify's DOM-based autofill never sees the fields
2. iCIMS forms use non-standard field naming (custom `icims-*` attributes) that Simplify may not have mapped

### What Simplify Can Fill on iCIMS (if the account already exists)
When a candidate is already logged in and reaches the actual application form, Simplify can reportedly fill:
- Standard text fields (name, phone, email — already populated from profile)
- Work history entries
- Education fields

### What Simplify Cannot Fill on iCIMS
- The account creation step itself (email/password form)
- Custom employer screening questions (free-text, custom dropdowns)
- EEO voluntary disclosure (standard dropdowns but not consistently mapped)
- File upload fields (resume, cover letter)

### Simplify's Fundamental Limitation on Heavy-Registration ATSes
Simplify Copilot is a browser-extension autofill tool — it fills DOM form fields after they are rendered. It cannot:
- Create accounts programmatically
- Handle multi-tab redirects during account creation
- Manage email verification flows
- Pre-fill fields that are rendered inside iframes or shadow DOM elements (which iCIMS uses in some implementations)

### Sources
- Reddit r/recruitinghell: Simplify works "a lot on Workday, Taleo, Lever, Greenhouse" — iCIMS not mentioned
- Scale.jobs / Simplify Copilot 2026 review: 20,000+ pages supported, lists Workday/Lever/Greenhouse as primary
- JobCopilot review of Simplify (2026): notes autofill gaps on heavily customized ATS portals
- Simplify Chrome Web Store description: "autofill job application questions in 1-click"
