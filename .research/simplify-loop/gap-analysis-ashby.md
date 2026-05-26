# Ashby Apply-Worker Field Gap Analysis

**Source artifacts:** `iterations/005/` (Notion Outbound BDR, the only Ashby capture in this run; iterations 006-008 are Greenhouse/Cloudflare or not-yet-populated).
**Result:** 1 unresolved, 0 required, confidence 1.00, `hard_blockers: False`. Ashby + Simplify is the cleanest ATS pairing observed.

## 1. What Simplify DOES fill on Ashby

Confirmed by diffing `dom_pre.html` -> `dom_post.html` (only POST values shown):

| Field (DOM) | Label | Filled value |
|---|---|---|
| `input#_systemfield_name` | "Full Name" | `Joseph Spagnoli` |
| `input#_systemfield_email` | "Email" | `jspagnoli1705@gmail.com` |
| `input[name=8039f8aa-...]` (tel, role-scoped UUID) | "Phone" | `+15613292705` |
| `input[role=combobox][placeholder="Start typing..."]` | "Location" | `West Palm Beach, Florida, United States` |
| `input#_systemfield_resume` (type=file, required) | "Resume" | shown as `Joseph_Spagnoli_resume.pdf` in sibling `<div class="_file_1fd3o_77">` |
| `input[name=dbb7e595-...]` (UUID) | "LinkedIn Profile" | `https://www.linkedin.com/in/joseph-spagnoli` |

Per the Ashby docs, only `resume`, `candidate's location`, and `candidate's education history` are true Ashby "system fields." `Phone` and `LinkedIn Profile` are mapped to **per-job UUID fields**, not `_systemfield_*` — Simplify still fills them via label heuristics. That match is reliable for BDR; engineering roles may use slightly different labels (e.g. "GitHub" instead of "LinkedIn") which would test the heuristic.

## 2. What Simplify MISSES

Only one literal entry in `unresolved_fields.json`:
```json
{"field_type": "file", "is_required": false, "selector": "input:nth-child(1)"}
```
That input is the **autofill-uploader file input** inside the `_autofillPane` sidebar — *not* the real application resume (which is filled). It is unreliably labelled (`field_id: null`, `label: null`) and not required; **safe to ignore**.

The substantive gaps that an AI finisher must close are categories Simplify silently skipped (they don't surface as `unresolved` because none are required on this BDR form, but they appear on the form and the user is expected to answer):

| Category | Roles | Strategy | Examples (verbatim labels) |
|---|---|---|---|
| Pronouns radio | BDR (likely all) | profile-direct (`candidate_profile.pronouns`) + dropdown fuzzy match | "What pronouns would you like our team to use when addressing you?" -> `He/Him`, `She/Her`, `They/Them`, `Prefer not to say`, `Not represented here` |
| Sponsorship checkbox/yes-no | BDR + Eng | profile-direct (`needs_sponsorship`) | "Will you now or in the future require Notion to sponsor an immigration case in order to employ you?" |
| Hybrid/in-office attestation | BDR + Eng (NY/SF based) | profile-direct or defer | "We work from our offices on Mondays, Tuesdays, and Thursdays (Anchor Days)... Are you [able to comply]?" |
| Source-of-application multi-select | All | profile-direct (`referral_source`) | "How did you hear about this opportunity? (select all that apply)" -> `LinkedIn`, `Glassdoor`, `Notion Blog`, `Notion Employee`, `Notion Website`, `Billboard/Outdoor Ads`, `Conference or Meetup` |
| EEO: Gender | All | profile-direct (with `Decline to self-identify` default) | "Gender" -> `Male`, `Female`, `Decline to self-identify` |
| EEO: Race / Ethnicity | All | profile-direct | "Race" -> `Hispanic or Latino`, `White (Not Hispanic or Latino)`, ... `Decline to self-identify` |
| EEO: Veteran status | All | profile-direct | "Veteran Status" -> `I identify as one or more of the classifications of protected veteran listed above`, `I am not a protected veteran`, `I decline to self-identify for protected veteran status` |

Note: the post-fill DOM shows `label._label_1v5e2_43 _checked_1v5e2_58` on race -> `Decline to self-identify`, so **Simplify did click one EEO race option** for this iteration. Gender + Veteran were not clicked. Coverage of the EEO block is partial and unreliable.

## 3. Ashby's custom-question format

Each question is a `div._fieldEntry_17tft_29.ashby-application-form-field-entry` (or a `fieldset._container_1v5e2_29._fieldEntry_17tft_29` for multi-option groups). Inside:

- A `label._heading_101oc_53._label_17tft_43.ashby-application-form-question-title` carries the question text (and `_required_101oc_92` if required).
- Inputs are named by a **per-form UUID** (e.g. `dbb7e595-3d7b-4a1f-b0b6-76497b74b4cb`). Multi-option radios concatenate two UUIDs: `<question_uuid>_<option_set_uuid>` and then `-labeled-radio-<n>` per option id.
- Labels for individual options live in sibling `label._label_1v5e2_43` elements (no `for=` attribute — they wrap a hidden `input`), so matching is by **DOM proximity, not `for`**.
- "If yes, explain" follow-ups: not present in this iteration's DOM. Based on the Ashby docs (yes/no + short answer as separate field types) they appear as a separate sibling `_fieldEntry_` that the finisher must detect by conditional visibility post-click.

Simplify never appears to use these UUID names — it relies entirely on the question-title text. That works for stable canonical questions (sponsorship, pronouns) and fails on bespoke ones.

## 4. React-controlled input concern (verified)

- The DOM's EEOC fieldset UUIDs **change between `dom_pre.html` and `dom_post.html`** (`5f05dbce-...` -> `468d3724-...`, `f78f4c10-...` -> `39fb2c44-...`). Ashby's React tree re-mounts the EEOC component, which means **any value written to the pre-mount input is discarded**. The finisher must (a) wait for stable mount, then (b) re-verify after a brief delay.
- **Zero** inputs carry a literal `checked` HTML attribute even though one race option visually shows `_checked_1v5e2_58`. State lives only in React; the apply worker must drive clicks via `element.click()` (not `input.checked = true`) and must dispatch React's synthetic `change` event, or the post-submit payload will be empty.
- Text inputs (`_systemfield_name`, etc.) survive the round-trip — confirms Simplify is using a React-compatible setter for those.

## 5. Engineering-specific questions

**Not observable in this run** — iterations 005-008 contain one Ashby capture (BDR) and three Greenhouse Cloudflare captures. No App Sec / SWE Data Platform Ashby DOMs landed. Based on Ashby's field-type catalogue and the BDR layout, expect engineering forms to add:

- A `Long unformatted answer` field (textarea, no character limit) for "Hardest technical problem you've solved" or "Why this team?" -> **generated text** strategy.
- One or more `Short answer` UUID inputs for "GitHub", "Personal website", "Link to writing/project" -> **profile-direct** (extend candidate_profile with `links: {github, portfolio, writing}`).
- `Multiple choice` or `Checkboxes` for "Familiarity with: Rust / Go / Python / AWS / k8s" -> **profile-direct from skills list** with dropdown fuzzy match.
- Possibly a `Number` field for years of experience -> **inference from resume**.

These should be re-validated as soon as an Ashby eng capture lands in `iterations/`.

## 6. Common Ashby patterns beyond our samples (web-confirmed)

Per docs.ashbyhq.com/application-forms, Ashby's native field types are: short answer, long unformatted, phone, email, multiple choice, checkboxes, date, yes/no, number, resume, candidate's location, other location, referral URL, file, education history. The **only** true system fields are `resume`, `candidate's location`, and `education history`. Everything else — **including compensation, sponsorship, pronouns, EEO** — is implemented as a custom question with a UUID name, optionally surfaced as a "Global application question" set at the org level. There is no `_systemfield_compensation`. The EEOC block, however, does use `__systemfield_eeoc_gender / _race / _veteran_status` suffixes (visible in our DOM), so EEOC is a hybrid: org-scoped UUID prefix + system suffix.

## 7. Defer policy recommendation (3-tier)

- **Tier 1 — Auto-fill from profile (high confidence):** Pronouns, sponsorship Yes/No, work-authorization Yes/No, hybrid attestation, source-of-application multi-select, all three EEOC blocks. Drive via React-aware click + change-event dispatch; re-verify after 300 ms.
- **Tier 2 — Generate then auto-fill (medium confidence):** Long-answer technical/behavioural questions on eng forms ("hardest problem", "why this team"). Generate with role context, write via React-compatible setter, leave a confidence score on the field for human review.
- **Tier 3 — Defer to human:** Ambiguous file inputs without labels (the autofill-uploader sidebar), conditional "If yes, explain" follow-ups that didn't render, and any required field whose UUID label didn't match the profile schema after fuzzy match below threshold 0.7. The autofill-uploader is **always Tier 3 ignore** — never required, distinct from `_systemfield_resume`.
