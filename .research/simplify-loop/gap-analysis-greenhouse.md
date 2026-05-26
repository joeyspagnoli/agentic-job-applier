# Greenhouse Field-Gap Analysis (Apply Worker vs Simplify Copilot)

Source artifacts:
- `iterations/001/` - Cloudflare ML Engineer Intern (Summer 2026), 24 unresolved / 17 required
- `iterations/006/` - Cloudflare Business Analyst Intern (Singapore, July-Dec 2026), 19 unresolved / 18 required
- Both: `ats_platform=greenhouse`, `outcome=NEEDS_REVIEW`, `score=0.80`, `has_hard_blockers=True`

## 1. What Simplify DOES fill on Greenhouse

Verified by diffing `dom_post.html` against `unresolved_fields.json`:

| Category | Fields | Notes |
|---|---|---|
| Standard contact (text inputs) | `first_name`="Joseph", `last_name`="Spagnoli", `email`="jspagnoli1705@gmail.com" | Filled reliably via `autocomplete="given-name"` / `family-name` / `email` hints. |
| Resume upload | `input#resume` (file) | Confidence check `resume_uploaded: true`. The input itself appears in `unresolved_fields.json` (the scanner can't read file inputs), but Simplify did upload. |
| Free-text "Legal Name" custom question | `question_66747915` = "Joseph Spagnoli" | Filled because the label is well-known. |

That's it. Everything else Greenhouse renders is a React-Select combobox (`role="combobox" aria-haspopup="true"`) or a custom textarea, and Simplify leaves all of them empty.

## 2. What Simplify MISSES - categorized

### A. Phone (with country-code widget)
- **Fields:** `input#phone` (empty value), plus the `intl-tel-input` widgets `iti-0__search-input` and the anonymous `input:nth-child(1)` selectors that wrap each combobox.
- **Frequency:** Every Greenhouse form (Cloudflare uses `intl-tel-input` library on both samples).
- **Agent need:** Profile-direct (E.164 phone). Must also click the flag selector for non-US numbers.
- **Examples:** `aria-label="Phone"`, `aria-label="Change country, selected United States (+1)"`.

### B. Country dropdown (React-Select combobox)
- **Fields:** `id="country"` (required, empty).
- **Frequency:** Appears whenever the company asks "Are you legally authorized to work in $COUNTRY?" - essentially universal on Greenhouse.
- **Agent need:** Profile-direct + dropdown fuzzy-match ("United States" - listbox option).
- **Example:** `Country*` (above the EEO section).

### C. Optional URL field
- **Field:** `question_66747916` / `question_64628434`: "Would you like to include your LinkedIn profile, personal website or blog?"
- **Frequency:** ~90% of Greenhouse jobs (companies add it because the native LinkedIn/Website fields are off by default).
- **Agent need:** Profile-direct (LinkedIn URL). Not required but high-signal; should auto-fill.

### D. "How did you hear about us?" combobox
- **Field:** `question_66747917` / `question_64628435` (required).
- **Frequency:** Near-universal. Greenhouse offers it as a built-in templated question.
- **Agent need:** Dropdown fuzzy-match. Options like "Company Website", "LinkedIn", "Referral", "Other". Pick a safe default ("Company Website" or "LinkedIn"). Tier-1 with a generic answer.

### E. Conditional radios / Yes-No combobox screeners (required)
These are the bulk of the required gaps and the source of `hard_blockers=True`:

| ID | Label (verbatim) |
|---|---|
| 66747918 | "Do you currently live or are you willing to relocate to the job's location?*" |
| 66747919 | "Do you now or will you in the future require immigration sponsorship to work at Cloudflare?*" |
| 66747921 | "Are you currently enrolled in a university or program and will return to the program upon completion of internship?*" |
| 64628436 | "Do you have confirmed plans to be in Singapore for the duration of this internship?*" |
| 66747925 | "Do you possess proficient knowledge and experience in Python and SQL?" |

- **Frequency:** 3-6 per intern/early-career role; 1-3 per senior role.
- **Agent need:** Mixed. Relocation / location-presence / skill-match - **infer from JD + profile**. Sponsorship - **defer to human policy** (profile boolean OK if explicitly set, but the answer is legally consequential).

### F. Education dropdowns (combobox, required)
| ID | Label |
|---|---|
| 66747922 / 64628440 | "If you are currently enrolled... when do you expect to graduate? (Select the closest date.)*" |
| 66747923 / 64628441 | "If you are enrolled in university, what degree are you currently pursuing?*" |
| 66747924 / 64628442 | "If you were to receive a full-time offer, when would you be available to start?*" |

- **Agent need:** Profile-direct, but requires fuzzy-match against the listbox ("May 2027" - nearest option). Tier-1 with one extra inference step.

### G. Open-text essays
- **Field (iter 006 only):** `question_64628443` textarea: "Why are you interested in this internship? What in particular do you want to work on?*"
- **Frequency:** ~30% of Greenhouse jobs, higher at startups.
- **Agent need:** Generated text (cover-letter-style answer using JD + profile). Tier-2 (draft + flag for human review).

### H. EEO / Demographic block (Greenhouse-standard, never required)
- **Fields:** `gender`, `hispanic_ethnicity`, `veteran_status`, `disability_status` - all React-Select.
- **Frequency:** Universal on US Greenhouse postings (federal EEOC self-ID). Absent on iter 006 (Singapore role).
- **Agent need:** Always defer. Simplify intentionally leaves these blank.

### I. Cover-letter file upload
- **Field:** `input#cover_letter` (optional file).
- **Frequency:** ~40% of Greenhouse forms.
- **Agent need:** Profile-direct if user enabled cover-letter generation; otherwise skip.

### J. Phantom `input:nth-child(1)` entries
- **Frequency:** 7 anonymous entries in iter 001, 7 in iter 006.
- **Agent need:** None - these are the hidden text-search inputs inside each React-Select widget. The scanner double-counts. The finisher agent should de-dupe by checking whether a sibling combobox shares the parent wrapper.

## 3. Why `hard_blockers=True`

The confidence engine flips `has_hard_blockers` when `unresolved_required_count > 0`. Iter 001 reports 17 required-and-empty:

- `country` (1)
- The 6 question_XXX comboboxes marked required: 66747917, 66747918, 66747919, 66747921, 66747922, 66747923, 66747924 (7)
- The 7 phantom `input:nth-child(1)` placeholders that mirror those comboboxes (the scanner counts both the React-Select internal `<input>` and the visible combobox `<input>` as required because both inherit `aria-required="true"` from the same wrapper)

The phantom duplicates inflate the count from a real 8 to a reported 17. The finisher agent should treat them as one logical field per `question_XXX` id.

## 4. Greenhouse-specific patterns (from web research + DOM)

- **EEO block:** Always rendered as 4 React-Select dropdowns with ids `gender`, `hispanic_ethnicity`, `veteran_status`, `disability_status`. Simplify's stance per their docs: custom and open-text fields require manual entry. Demographic dropdowns appear to fall in that bucket and are skipped on purpose.
- **"How did you hear about us?":** Greenhouse offers this as a templated question; the company can either let it be free-text or attach a dropdown of source channels.
- **"Why $COMPANY / Why this role?":** Renders as a `<textarea>` with `aria-required="true"`. Cloudflare iter 006 has the verbatim "Why are you interested in this internship?" version.
- **Location dropdowns:** Greenhouse uses linked Country / State comboboxes for some roles. On these intern postings the location is pre-set, so only the demographic `country` field is present. For roles with location selection, expect a conditional cascade (state options change after country selection).
- **File-upload extras:** `cover_letter` is universal. Transcript / portfolio uploads appear only on engineering-intern and creative roles; they use the same `input[type=file]` pattern with custom labels.

## 5. Defer policy (3-tier)

### Tier 1 - Auto-fill from profile (or trivial inference)
- `phone` (+ country flag widget)
- `country` combobox
- `question_*` LinkedIn/website URL
- "How did you hear about this job?" - default to a safe channel (LinkedIn / Company Website)
- Graduation date, degree, start date - lookup in profile, fuzzy-match listbox options
- "Are you enrolled in a university?" - profile boolean
- Cover-letter file (only if user opted in)

### Tier 2 - Draft and flag for human
- "Why this internship / company?" textarea - generate from JD + profile, mark `needs_review=true`
- "Do you have proficient knowledge of Python and SQL?" / other skill-screen Yes/No - infer from resume keyword overlap, flag if confidence < 0.85
- "Are you willing to relocate to $CITY?" - infer from profile location-policy, flag for any non-trivial move

### Tier 3 - Always defer to human
- Sponsorship questions ("Do you require immigration sponsorship?") - legally consequential, never auto-answer
- EEO / Demographics (gender, ethnicity, veteran, disability) - leave blank
- Salary expectations
- Specific start date (when offer-conditional)
- Anything containing the strings "sponsor", "authorize", "veteran", "disability", "ethnicity", "gender", "salary", "compensation"

## Summary for the finisher agent

On Greenhouse, Simplify handles only 4 fields reliably (first_name, last_name, email, resume upload) plus the occasional well-labelled custom text question (e.g. "Legal Name"). It misses:
1. **Phone** + country flag widget (always required)
2. **All React-Select comboboxes** including country, EEO block, and every `question_XXX` dropdown
3. **All textareas** for "Why this role" essays
4. **Optional URL** field for LinkedIn / portfolio

The finisher agent should target a ~9-fields-per-Greenhouse-form fill plan, dedupe `input:nth-child(1)` phantoms against their parent combobox, treat the EEO block as always-skip, and route sponsorship and essay fields to Tier 2/3 review.
