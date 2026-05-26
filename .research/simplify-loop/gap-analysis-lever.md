# Lever Apply — Field-Gap Analysis for the AI Finisher

**Samples**: Iterations 002, 003, 004 (all `jobs.lever.co/coupa/f7fce723-…`)
**Iteration 004** is the only one with a captured `unresolved_fields.json` (16 entries, 6 required).
Cross-referenced with `dom_post.html` (form rendered after Simplify) and Lever's documented form schema.

---

## 0. Headline finding — Simplify is essentially absent on Lever

Across all three Lever iterations, `simplify_pre_attach.autofill_present = False` and the runlog
shows `simplify_pre_attach: MISSING`. The Simplify shadow root injects (the resume-score banner
and job-tracker panel render), but **Autofill never executes**. In `dom_post.html` every
standard field — `name`, `email`, `phone`, `org`, `urls[*]`, `location` — is empty. The only
values Simplify writes are the hidden fingerprint inputs `origin=Simplify` and `source=Simplify`,
plus the `referer` field. Net result: on Lever, the apply worker must treat **the entire form**
as the gap, not just the long-tail.

This is fundamentally different from Greenhouse (iter 001/006/007) and Ashby (iter 005) where
Simplify filled identity fields cleanly.

---

## 1. What Simplify DOES fill on Lever

In practice on the Coupa form: **nothing user-facing**. The expected Lever-standard fields
(`input[name=name]`, `[name=email]`, `[name=phone]`, `[name=org]`, `[name=urls[LinkedIn]]`,
`[name=urls[GitHub]]`, `[name=urls[Portfolio]]`, `[name=urls[Other]]`, `[name=resume]`) all
remain empty post-Autofill. Simplify only sets:

- `input[name=origin]` → `Simplify`
- `input[name=source]` → `Simplify`
- `input[name=referer]` → the /apply URL
- `input[name=timezone]` → browser TZ (`America/Los_Angeles`)

The "LinkedIn Apply" widget loads (a third-party LinkedIn iframe) but is gated behind the user
clicking the LinkedIn button — Simplify does not trigger it.

---

## 2. What Simplify MISSES (categorized)

### 2a. Core identity (profile-direct, ALWAYS empty on Lever)

| Selector | Label | Required |
|---|---|---|
| `input[name="name"]` | `Full name✱` | yes |
| `input[name="email"]` | `Email✱` | yes |
| `input[name="phone"]` | `Phone ✱` | yes |
| `input[name="org"]` | `Current company` | no |
| `input[name="urls[LinkedIn]"]` | `LinkedIn URL` | no |
| `input[name="urls[GitHub]"]` | `GitHub URL` | no |
| `input[name="urls[Portfolio]"]` | `Portfolio URL` | no |
| `input[name="urls[Other]"]` | `Other website` | no |
| `input[name="resume"]` | `Resume/CV ✱` | yes |

**Fill strategy**: straight from `candidate_profile.yaml`. The resume input is a `type=file`
hidden behind `a.visible-resume-upload`; needs `setInputFiles` not click.

### 2b. Location autocomplete (inference + dropdown selection)

`input#location-input` (name=`location`) is an **async-validated autocomplete**, paired with a
hidden `input#selected-location` (`name=selectedLocation`). Typing alone leaves the dropdown
showing "No location found. Try entering a different location" until a Lever AJAX call
resolves, at which point the user must click a `.dropdown-results` row, which populates the
hidden field with a Lever location ID. **A blind `fill()` will not satisfy submit validation
because `selectedLocation` stays empty.**

**Fill strategy**: type city → wait for `.dropdown-results > div` → click first match →
verify `#selected-location` has a value. Defer if no match.

### 2c. Pronouns (multi-select checkbox; 11 options + Custom textbox)

Group `ul#candidatePronounsCheckboxes` with 11 `input[name="pronouns"]` checkboxes plus a
hidden custom-text input (`#customPronounsTextField`) revealed when the user picks "Custom".
Not required, but defaults to all-unchecked.

**Fill strategy**: profile-direct (`candidate_profile.pronouns`) → check matching boxes; skip
if user has no preference.

### 2d. Lever `customQuestions` / "cards" block (the real screening gauntlet)

Every custom question lives under `form#application-form > div.section[data-qa="additional-cards"]`
with field names of the form `cards[CARD_UUID][fieldN]`. The label appears in a sibling
`div.application-label > div.text`. A hidden `cards[CARD_UUID][baseTemplate]` input holds the
full JSON schema (with `type`, `text`, `required`, `options` including stable `optionId`s) — an
extractor can read this directly instead of scraping labels.

Coupa card "US/Canada/EMEA/APAC" (`card UUID dd2e8824-…`) had 6 required questions, all left
blank by Simplify:

| field | Verbatim label | Type | Options |
|---|---|---|---|
| field0 | `How did you learn about this role?` | dropdown | 24 sources (LinkedIn, Glassdoor, Coupa Career Site, ALPHA, AnitaB, "Other"...) |
| field1 | `Are you now, or have you previously been employed by Coupa?` | dropdown | Yes/No |
| field2 | `Do you have legal authorization to work in the country where this job is located?` | dropdown | Yes/No |
| field3 | `Will you require sponsorship or a visa for employment now or in the future?` | dropdown | Yes/No |
| field4 | `Are you fluent in any language other than English? Please specify.` | text | (free-text, placeholder="Type your response") |
| field5 | `If your role requires it, would you be prepared to work in the office for 2-3 days per week?` | dropdown | Yes/No |

**Fill strategy mix**: work-auth/sponsorship/prior-employment/RTO → profile-direct boolean.
"How did you hear about us?" → fuzzy-match against profile preference, fallback to "LinkedIn"
or "Other". "Fluent in other languages?" → generated short text from profile language list.

Simplify never fills any `cards[...]` field on any Lever sample we have.

### 2e. EEO / demographic survey ("countrySurvey" / `surveysResponses[...]`)

Lever renders an optional "Equal Employment Opportunity Survey for Coupa (EMEA)" block as a
second hidden-JSON-driven card with selector pattern `surveysResponses[SURVEY_UUID][responses][fieldN]`.
On iter 004 it was rendered but **the unresolved scanner did not enumerate these inputs**
(they're checkboxes/radios and `required=false`). Verbatim questions:

- `What is your age range?` (18-24…65+, Decline to self-identify)
- `What gender do you identify as?` (Female/Male/Non-binary/Decline)
- `What race or ethnicity do you identify with?` (Asian/Black/Mixed/White/Other/Decline)
- `What is your highest level of education completed?` (Secondary/BSc/Advanced/Decline)

The section ID encodes a giant country-allowlist (`countrySurvey_<uuid>_<uuid>_…`), meaning
Lever picks which survey to show by geo. EMEA gets the UK-style ethnicity bands; US would get
EEOC bands; APAC may get none.

**Fill strategy**: profile-direct if user opted in; otherwise default to "Decline to self-identify"
for every field.

---

## 3. Custom-questions block — detection recipe

```text
form#application-form
  > div.section[data-qa="additional-cards"]
      > h4[data-qa="card-name"]              # human card title
      > input[type=hidden][name="cards[UUID][baseTemplate]"]   # JSON schema
      > ul > li.application-question.custom-question
           > div > div.application-label.full-width.<type>     # type ∈ dropdown|text|multiple-choice|textarea
                > div.text                                     # verbatim question text + <span class="required">✱
           > div.application-field.full-width[.required-field]
                > select|input|textarea|ul (checkbox group)
```

Recommended: **parse `baseTemplate` JSON** rather than DOM-scrape labels. It gives stable
`fields[].id`, `fields[].required`, `fields[].type` (`dropdown`/`text`/`textarea`/`multiple-choice`),
and `options[].optionId` — clean structured data with no escaping ambiguity.

Simplify ignored all `cards[...]` on every Lever sample.

---

## 4. hCaptcha situation

Confirmed loaded: `<script src="https://js.hcaptcha.com/1/secure-api.js?...&onload=onLoad">`,
plus two `iframe[sandbox][title="Widget containing checkbox for hCaptcha security challenge"]`
elements with `visibility: hidden` styling, position-fixed full-viewport at `z-index:2147483647`.

The captcha is **invisible/embedded** and triggered on submit-button click. Page logic:
`btn-submit` calls `hcaptcha.execute()` first; if the hidden `#hcaptchaResponseInput` has no
token, the real submit is deferred until `onSuccess`. Implications:

- Does **not** interfere with our pre-submit DOM scan or field fill. Form fields are normal
  same-origin inputs; only the hCaptcha iframe is cross-origin.
- `unresolved_fields.json` correctly did not surface any captcha input — `h-captcha-response`
  is a hidden input that gets filled by JS post-challenge, and our scanner ignored it.
- The apply worker's "stop before submit" policy means we never trigger the challenge, so the
  captcha is a non-issue at scan time. **If we ever auto-submit on Lever we will need a captcha
  solver or human-handoff** — Lever uses hCaptcha enterprise on a non-trivial share of postings.

---

## 5. Hard-blocker root cause on iter 004

Required-true unresolved fields, ordered:

1. `input[name=name]` — Full name ✱
2. `input[name=email]` — Email ✱
3. `input[name=phone]` — Phone ✱
4. `select cards[…][field0]` — How did you learn about this role ✱
5. `select cards[…][field1]` — Prior Coupa employment ✱
6. `select cards[…][field2]` — Legal work authorization ✱
7. `select cards[…][field3]` — Sponsorship required ✱
8. `input cards[…][field4]` — Other languages spoken ✱
9. `select cards[…][field5]` — Office 2-3 days/week ✱

Plus implicit: `input[name=resume]` (Resume/CV ✱) — not in unresolved JSON because the field
is `type=file` and our scanner doesn't list file inputs even when empty.

**Root cause**: Simplify Autofill did not run. The blocker isn't a single tricky field — it's
that we got zero coverage on Lever. The finisher must own the entire identity layer here.

---

## 6. Common Lever patterns beyond our sample

From the Lever schema and public job postings:

- **Work authorization** + **sponsorship now/future** — near-universal Yes/No dropdown pair.
  Often phrased "Are you legally authorized to work in $COUNTRY?" / "Will you now or in the
  future require sponsorship for employment visa status?".
- **"How did you hear about us?"** — usually a `dropdown` cards field with a giant source
  list, often with `Other` triggering a conditional follow-up textarea (`fieldN+1`).
- **Salary expectations** — `text` cards field, label like `Desired salary` or
  `Compensation expectations (USD)`.
- **Notice period / earliest start date** — `text` or `dropdown` cards field.
- **Pronouns** — Lever's standardized `ul#candidatePronounsCheckboxes` (covered above).
- **"Additional information"** — Lever exposes a built-in optional `textarea[name="comments"]`
  on many postings (not present on Coupa Coupa, but extremely common). Treat as opt-in cover-letter slot.
- **EEO/demographic survey** — `surveysResponses[UUID][responses][fieldN]`, region-gated by
  the `countrySurvey_<...>` section ID.
- **File uploads beyond resume** — occasional `[name="cards[UUID][fieldN]"]` of type `file`
  for portfolio/cover letter/transcript. Always defer; never auto-upload arbitrary files.

---

## 7. Defer-policy recommendation

| Field class | Auto-fill | Draft + flag | Always defer |
|---|---|---|---|
| Name / email / phone | ✓ (profile-direct) | | |
| Resume file | ✓ (setInputFiles) | | |
| LinkedIn / GitHub / Portfolio / Other URLs | ✓ | | |
| Current company / org | ✓ | | |
| Location autocomplete | ✓ when dropdown match found | type-and-wait fallback | no match after 3s → defer |
| Pronouns checkboxes | ✓ if profile has pronouns | | leave blank if not set |
| Work auth / sponsorship Yes/No | ✓ (profile boolean) | | |
| Prior-employment-at-this-company Yes/No | ✓ (default No, profile override) | | |
| RTO / office days Yes/No | ✓ (profile preference) | | |
| "How did you hear about us?" | | ✓ — pick profile pref or "LinkedIn" | |
| Other-languages free-text | | ✓ — generate from profile languages list | |
| Salary expectations | | ✓ — draft from profile range, flag for review | |
| Notice period / start date | | ✓ — compute from profile + today | |
| EEO/demographic survey | ✓ "Decline to self-identify" everywhere unless user opted in | | |
| `comments` / "Additional information" textarea | | ✓ — short tailored note | |
| hCaptcha | | | always defer (human or solver service) |
| Arbitrary file-upload cards fields | | | always defer |

**Operational note**: because Simplify reliably fails to attach on Lever, the finisher should
**not** be gated behind a `simplify_autofill_detected=True` precondition for this ATS — it
should fall straight through to full-form synthesis using the `cards[UUID][baseTemplate]`
JSON as the question schema.
