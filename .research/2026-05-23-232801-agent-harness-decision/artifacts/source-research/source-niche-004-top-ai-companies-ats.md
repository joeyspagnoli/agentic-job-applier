# source-niche-004: Top AI Companies ATS Platforms

Researched via WebFetch against live careers pages (2026-05-23).

## Findings

| Company | Careers URL | ATS | Evidence |
|---------|-------------|-----|---------|
| Anthropic | anthropic.com/jobs | **Greenhouse** | Apply links → `job-boards.greenhouse.io/anthropic/jobs/{id}` |
| OpenAI | openai.com/careers | Unknown (403 on fetch) | Historically Greenhouse; may have migrated |
| Stripe | stripe.com/jobs | **Custom + Greenhouse** | Custom `/jobs/listing/{title}/{id}` URLs on stripe.com; apply flow goes to Greenhouse |
| Ramp | ramp.com/careers | **Ashby** | Redirects to `jobs.ashbyhq.com/ramp` |
| Replit | replit.com/jobs | **Ashby** | Links to `jobs.ashbyhq.com/replit` |

## General Pattern for Top AI/Tech Companies

- **Greenhouse**: Anthropic, Stripe, most Series B+ startups — `job-boards.greenhouse.io/{slug}/jobs/{id}`
- **Ashby**: Growing adoption among tech-forward companies (Ramp, Replit, Linear, etc.) — `jobs.ashbyhq.com/{slug}/{id}/application`
- **Lever**: Used by some companies — `jobs.lever.co/{slug}/{id}`
- **Workday**: Large enterprises — `company.wd5.myworkdayjobs.com/careers`
- **Truly custom**: Apple, Google use fully proprietary systems

## Key Insight for Apply Worker

Even when `source_url` is on a company's branded domain (e.g., `stripe.com/jobs/listing/senior-engineer/123`), the apply button click will navigate to a known ATS. The worker should:
1. Navigate to `source_url`
2. Detect: is this page the ATS form OR a company "job detail" page with an Apply button?
3. If it's a detail page with Apply button → click Apply → land on ATS form → proceed
4. The existing `ats_detection.py` URL-pattern matching will fire after step 3's navigation
