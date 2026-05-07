# Simplify Failure Analysis

Total iterations parsed: 25
Passing iterations: 9
Total unresolved fields across passing iterations: 138

## Per-iteration summary

| Iter | ATS | URL | Confidence | Simplify | Unresolved | Pass |
|------|-----|-----|------------|----------|------------|------|
| 001 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5127050008` | None | ✗ | 0 | ✗ |
| 002 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5127050008` | None | ✗ | 0 | ✗ |
| 005 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5076929008` | 0.45 | ✗ | 27 | ✗ |
| 006 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5076929008` | 0.45 | ✗ | 27 | ✗ |
| 007 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5076929008` | 0.45 | ✗ | 27 | ✗ |
| 008 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5076929008` | 0.45 | ✗ | 27 | ✗ |
| 009 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5023394008` | 0.45 | ✗ | 8 | ✗ |
| 010 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5023394008` | 0.45 | ✗ | 8 | ✗ |
| 011 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5023394008` | 0.45 | ✗ | 8 | ✗ |
| 012 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5023394008` | 0.45 | ✗ | 8 | ✗ |
| 013 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5023394008` | 0.45 | ✗ | 8 | ✗ |
| 014 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5023394008` | 0.45 | ✗ | 8 | ✗ |
| 015 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5023394008` | None | ✗ | 0 | ✗ |
| 016 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5023394008` | None | ✗ | 0 | ✗ |
| 017 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5023394008` | None | ✗ | 0 | ✗ |
| 018 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5023394008` | 0.6 | ✓ | 4 | ✗ |
| 019 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5023394008` | 0.8 | ✓ | 4 | ✓ |
| 020 | greenhouse | `job-boards.greenhouse.io/...scaleai/jobs/4631613005` | 0.8 | ✓ | 15 | ✓ |
| 021 | greenhouse | `job-boards.greenhouse.io/...scaleai/jobs/4654897005` | 0.7 | ✓ | 20 | ✓ |
| 022 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5076929008` | 0.7 | ✓ | 26 | ✓ |
| 023 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5023394008` | 0.8 | ✓ | 4 | ✓ |
| 024 | greenhouse | `job-boards.greenhouse.io/...scaleai/jobs/4631613005` | 0.8 | ✓ | 11 | ✓ |
| 025 | greenhouse | `job-boards.greenhouse.io/...anthropic/jobs/5161980008` | 0.8 | ✓ | 25 | ✓ |
| 026 | greenhouse | `job-boards.greenhouse.io/...figma/jobs/5822886004?gh_jid=5822886004` | 0.7 | ✓ | 24 | ✓ |
| 027 | greenhouse | `boards.greenhouse.io/...cloudflare/jobs/7480799?gh_jid=7480799` | 0.8 | ✓ | 9 | ✓ |

## Per-ATS stats

| ATS | Iterations | Passes | Avg unresolved (per pass) |
|-----|-----------:|-------:|--------------------------:|
| greenhouse | 25 | 9 | 15.3 |

## Category breakdown (passing iterations)

Sorted by frequency. `required` is the count of required fields in that category that Simplify left empty; high required + high count = top priority to handle.

| Category | Total | Required | Field types | Sample labels |
|----------|------:|---------:|-------------|---------------|
| other | 30 | 8 | text(16), search(9), textarea(5) | Search · Please note that you will not be considered unless you complete the Constellation application form.  · Search |
| no_label | 29 | 29 | text(29) |  |
| work_authorization | 12 | 12 | text(12) | Are you legally authorized to work in the country where the job is located?* · Will you now or in the future require company sponsorship to retain or extend your work authorizatio · Are you legally authorized to work in the country where the job is located?* |
| location | 10 | 4 | text(10) | Country · Country · Country |
| file_upload | 10 | 0 | file(10) | Attach · Attach · Attach |
| demographics | 7 | 0 | text(7) | Gender · Veteran Status · Disability Status |
| linkedin_url | 6 | 0 | text(6) | LinkedIn Profile · LinkedIn Profile · LinkedIn Profile |
| portfolio_url | 6 | 0 | text(6) | Website · Website · Website |
| phone | 5 | 2 | tel(5) | Phone · Phone · Phone* |
| work_mode | 5 | 2 | text(5) | Are you open to working in person in our London office 2-3 times a week? · Are you open to working in person in our San Francisco office 2-3 times a week? · Are you open to working in-person in one of our offices 25% of the time?* |
| consent_checkbox | 5 | 5 | text(5) | Are you currently bound by any agreements with a current or former employer that may restrict your a · Are you currently bound by any agreements with a current or former employer that may restrict your a · AI Policy for Application* |
| relocation | 4 | 2 | text(4) | Are you open to relocation for this role? * · What is the address from which you plan on working? If you would need to relocate, please type "relo · Are you open to relocation for this role? * |
| email | 3 | 3 | text(3) | Email* · Email* · Email* |
| start_date | 2 | 0 | text(2) | When is the earliest you would want to start working with us? · When is the earliest you would want to start working with us? |
| name_first | 1 | 1 | text(1) | Last Name* |
| freeform_motivation | 1 | 1 | textarea(1) | Why do you want to join Figma?* |
| referral | 1 | 0 | text(1) | Preferred First Name |
| referral_source | 1 | 1 | text(1) | How did you hear about this job?* |

## Field-type distribution

| Type | Count |
|------|------:|
| text | 108 |
| file | 10 |
| search | 9 |
| textarea | 6 |
| tel | 5 |
