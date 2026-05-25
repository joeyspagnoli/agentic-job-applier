# source-aggregator-008-real-code.md
## Real-World Projects: Aggregator Routing Patterns

### GitHub Search Results
Query: `indeed apply playwright language:python`

#### 1. `cucia/job-sentinel` — `src/platforms/indeed/apply.py`
Uses Playwright with session storage state (saved cookies). Key patterns:
- Detects Indeed Apply via selectors: `.jobsearch-IndeedApplyButton`, `#indeedApplyButton`, `button[data-testid*='apply']`
- Uses `ensure_session()` to load saved cookies before navigation
- Random human delays between actions (500–2000ms)
- If no apply button found → falls back to "deferred" status

Routing insight: This project explicitly checks for Indeed Apply button selectors BEFORE deciding whether to proceed. No handling of "Apply on company site" (company-site apply is treated as out-of-scope or deferred).

#### 2. `Paul-Berdier/job_bot` — `applicator/indeed_applicator.py`
French-language project, Playwright + async. Key patterns:
- Logs into Indeed using `secure.indeed.com/auth` before navigation
- CAPTCHA detection via `check_for_captcha()` utility
- Human behavior simulation: `random_delay`, `human_type`, `human_click`
- Multi-step: login → navigate to job URL → detect apply mode → fill form

Routing insight: Treats Indeed login as a prerequisite. Our worker uses the user's real session so login is pre-done.

#### 3. `KhaoulaMaleh/MobileCVMind` — `playwright_applicator.py`
More general applicator. Key patterns:
- Intercepts new tabs/popups via `context.on('page', handler)` to handle "Apply on company site" tab-spawns
- Falls back to NEEDS_REVIEW on CAPTCHA or unknown form structures

Routing insight: **`context.on('page', handler)` is the standard pattern for catching company-site apply tab-spawns.** Our `browser.py` currently has NO such handler — it only creates a new page on line 199 (`page = await context.new_page()`). This is a gap.

### Pattern Summary Across Projects
1. **All projects use session/cookie state** to avoid login gates — our worker already does this
2. **Indeed Apply detection**: selectors `#indeedApplyButton`, `.jobsearch-IndeedApplyButton`, `[data-testid*='apply']`
3. **Company-site tab handling**: `context.on('page', ...)` event listener is universal
4. **Fallback to NEEDS_REVIEW** on CAPTCHA, login gate, or unknown structure — this matches our architecture
5. **Human-like delays**: 500–4000ms between navigation steps — important for Glassdoor/Indeed behavioral detection

### Key Gap Identified
`browser.py` does not register a `context.on('page', ...)` listener. When "Apply on company site" spawns a new tab, the worker's page reference still points to the aggregator listing page, not the ATS form. The worker will time out or see no form fields. This needs to be addressed in the apply worker design.
