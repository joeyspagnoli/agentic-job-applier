# source-niche-005: Real Custom Careers Pages — Apply Route Analysis

Examined via WebFetch (2026-05-23). Note: some pages returned 403/minimal content due to bot protection on live fetches.

## 1. anthropic.com/jobs
- **UI style**: Custom branded page listing departments and open roles
- **Apply route**: Click job → links to `job-boards.greenhouse.io/anthropic/jobs/{id}`
- **Form location**: Greenhouse domain (not Anthropic)
- **Worker action**: Navigate to Greenhouse URL; Simplify activates normally

## 2. openai.com/careers
- **UI style**: Custom page (403 during fetch — Cloudflare or similar protection)
- **Apply route**: Historically Greenhouse; current state unknown from static fetch
- **Worker action**: Must handle 403 on initial load → FAILED_NAVIGATION or UNCERTAIN liveness

## 3. stripe.com/jobs
- **UI style**: Custom Stripe-branded jobs portal at stripe.com/jobs/search
- **Job URLs**: `stripe.com/jobs/listing/{title-slug}/{id}` — custom domain, not ATS
- **Apply route**: Clicking Apply from listing page leads to Greenhouse form (per community knowledge)
- **Worker action**: Navigate to listing URL → detect "Apply" button → click → land on Greenhouse

## 4. ramp.com/careers
- **UI style**: Custom marketing page with "See open positions" CTA
- **Apply route**: Links to `jobs.ashbyhq.com/ramp`
- **Form location**: Ashby domain
- **Worker action**: Navigate to Ashby URL; Simplify supports Ashby

## 5. replit.com/jobs
- **UI style**: Custom page linking to Ashby
- **Apply route**: `jobs.ashbyhq.com/replit`
- **Form location**: Ashby domain
- **Worker action**: Navigate to Ashby URL directly

## Summary Pattern

| Company | First URL loaded | Redirects to ATS? | Apply form domain |
|---------|-----------------|-------------------|-------------------|
| Anthropic | anthropic.com/jobs | Via Apply click | greenhouse.io |
| OpenAI | openai.com/careers | (403 - blocked) | Unknown |
| Stripe | stripe.com/jobs/listing/{id} | Via Apply click | greenhouse.io |
| Ramp | ramp.com/careers | CTA links directly | ashbyhq.com |
| Replit | replit.com/jobs | CTA links directly | ashbyhq.com |

## Worker Pre-flight Implication

When `source_url` is on a company's own domain (not a known ATS):
- Page will likely have an "Apply" or "Apply Now" button
- Pre-flight should detect the BUTTON, not necessarily a `<form>` element
- Button click → navigation → ATS URL → second ATS detection pass
- If the page has NO apply button AND no form → `NO_FORM_FOUND` → hand off
