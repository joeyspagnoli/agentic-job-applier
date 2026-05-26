# Apply-worker field-gap synthesis (Greenhouse, Lever, Ashby)

**Date:** 2026-05-24
**Inputs:**
- 14 smoke iterations under `.research/simplify-loop/iterations/`
- 3 parallel sub-agent reports: `gap-analysis-{greenhouse,lever,ashby}.md`
- Iterations 001-014; the relevant working-state subset for each ATS:
  - Greenhouse / Cloudflare: 001, 006, 007, 008 (4 roles)
  - Lever / Coupa: 009, 010, 011 (3 roles)
  - Ashby / Notion: 005, 012, 013, 014 (3 roles, BDR run twice)

The goal is a single per-ATS brief for the future Layer-3 "finisher" agent: **what Simplify reliably handles, what it doesn't, and how an AI agent should treat each gap.**

---

## 0. Top-line findings

| ATS | Cleanest run | Worst run | Reliability verdict |
|---|---|---|---|
| **Ashby** (Notion) | 0 required unresolved (iters 005, 013, 014) | 1 required unresolved (iter 012, resume input flagged as a scanner false positive) | ✅ **Near-complete.** Engineering roles (App Sec, SWE Data Platform) were as clean as BDR. |
| **Greenhouse** (Cloudflare) | 7 required (iter 008, sales) | 18 required (iter 006, intern in Singapore) | ⚠️ **Partial.** Simplify fills first/last/email/resume reliably; every React-Select dropdown is left blank. Counts are **inflated** — the field scanner double-counts React-Select internals as phantom `input:nth-child(1)` entries, so real logical gaps are roughly 60% of the reported number. |
| **Lever** (Coupa) | 5 required (iter 009) | 9 required (iters 010, 011) | ❌ **Intermittent and unreliable.** Same Coupa form across 3 runs: one run had standard fields (name/email/phone) filled, two runs had them empty. Simplify's autofill is racy on Lever. |

**Headline takeaway:** the only ATS where today's worker + Simplify alone produces a submission-ready application is **Ashby**. Greenhouse needs a finisher for ~5-10 fields per form. Lever needs a finisher for the entire form because Simplify is unreliable even on standard fields.

---

## 1. Cross-ATS taxonomy of unfilled question categories

What follows is the **categorical** view — common to all three ATSes. Per-ATS specifics in section 2.

### Tier 1 — Auto-fill from profile (high confidence, fire-and-forget)
| Category | Typical labels | Source |
|---|---|---|
| Phone with country flag | "Phone", `intl-tel-input` widgets | Profile (E.164) + click flag selector |
| Country / state dropdown | "Country*", "State" | Profile + dropdown fuzzy match |
| Location autocomplete (async) | "Current location" / "Start typing…" | Profile + type→wait→click pattern |
| Personal URLs | "LinkedIn URL", "GitHub URL", "Portfolio URL" | Profile direct |
| Pronouns | "Pronouns", "What pronouns…" | Profile or "Prefer not to say" |
| Work authorization (Yes/No) | "Do you have legal authorization to work in $COUNTRY" | Profile boolean |
| "How did you hear about us?" | Dropdown (~20 sources) or short text | Profile default ("LinkedIn") |
| Source-of-application multi-select | "How did you hear about this opportunity? (select all)" | Profile + safe defaults |
| Graduation date / degree | "When do you expect to graduate?" / "What degree?" | Profile + fuzzy match |
| Earliest start date | "When could you start?" / "Notice period" | Profile + role start window |

### Tier 2 — Draft + flag for verify (medium confidence; agent fills, human reviews)
| Category | Typical labels | Source |
|---|---|---|
| "Why $COMPANY / Why this role?" essay | Textarea, often required | LLM generation from JD + profile |
| "Hardest technical problem" / experience essay | Textarea, eng roles | LLM generation from resume + JD |
| Skill-screening Yes/No | "Do you have proficient knowledge of Python and SQL?" | Resume keyword overlap → score; flag if &lt; 0.85 |
| Relocation willingness | "Are you willing to relocate to $CITY?" | Profile location policy; flag any non-trivial move |
| Hybrid / in-office attestation | "Can you commit to working from our office on…" | Profile remote-policy boolean |
| "If yes, explain" conditional follow-ups | Sibling textarea revealed by parent radio | Generated from parent answer |
| Language proficiency free-text | "Are you fluent in any language other than English?" | Profile + generate |

### Tier 3 — Always defer to human (legally/personally consequential)
| Category | Typical labels | Reason |
|---|---|---|
| Sponsorship | "Will you now or in the future require sponsorship?" | Legally consequential; never auto-answer |
| EEO / Demographics | gender, race/ethnicity, veteran status, disability status | Sensitive; user policy varies |
| Salary expectations | "Desired salary" / "Compensation expectations" | High-leverage; needs user input |
| Specific start date | When offer-conditional | Depends on user's other offers |
| File uploads beyond resume | Cover letter, transcript, portfolio | Often role-specific, often not in profile |

**Detection heuristic for Tier 3** (centralizable in `config/defer_rules.yaml`): any label containing
`sponsor | authorize | veteran | disability | ethnicity | gender | salary | compensation | start date | when can you start`.

---

## 2. Per-ATS field gaps

### 2a. Greenhouse (Cloudflare boards)

**What Simplify fills reliably:** first_name, last_name, email, resume upload. Sometimes a well-labelled custom text field ("Legal Name" → user's full name).

**What Simplify leaves blank (verbatim labels from our captures):**

| Field type | Verbatim label | Iters | Frequency | Tier |
|---|---|---|---|---|
| `intl-tel-input` widget | "Phone" + flag selector + search | 001, 006-008 | 100% | 1 |
| React-Select | "Country*" | 001, 006-008 | 100% on EEO-attached roles | 1 |
| Text | "Would you like to include your LinkedIn profile, personal website or blog?" | 001, 006-008 | ~90% | 1 |
| React-Select | "How did you hear about this job?*" | 001, 006-008 | ~100% | 1 |
| React-Select | "Do you currently live or are you willing to relocate to the job's location?*" | 001, 006, 007 | role-dependent | 2 |
| React-Select | "Do you now or will you in the future require immigration sponsorship to work at Cloudflare?*" | 001, 006-008 | ~100% | 3 |
| React-Select | "Are you currently enrolled in a university or program…?*" | 001, 006 (intern) | intern-only | 1 |
| React-Select | "When do you expect to graduate?" / "What degree?" / "When would you be available to start?" | 001, 006 (intern) | intern-only | 1 |
| Textarea | "Why are you interested in this internship?" | 006 | role-dependent | 2 |
| File | `input#cover_letter` (optional) | 001, 006-008 | ~100% | 1 if cover-letter generation enabled |
| React-Select × 4 | EEO: gender, hispanic_ethnicity, veteran_status, disability_status | all | 100% on US roles | 3 |

**Phantom-input issue:** our field scanner finds the React-Select hidden text-search input AND the visible combobox input — both inherit `aria-required="true"`. Each combobox is double-counted, inflating `unresolved_required_count` by ~50%. Iter 001 reported 17 required; logical real fields are 8-9. Iter 008 reported 7; logical real fields are ~4.

**Fix recommendation for the scanner:** dedupe by collapsing `input:nth-child(1)` entries whose parent contains a sibling `[role="combobox"]`.

### 2b. Lever (Coupa hosted forms)

**What Simplify fills *sometimes*:** name, email, phone, org, urls[LinkedIn|GitHub|…], location, resume.

**What Simplify NEVER fills:** any `cards[CARD_UUID][fieldN]` custom question, any `surveysResponses[SURVEY_UUID][...]` EEO survey, pronouns multi-select.

**Reliability problem:** across iters 009, 010, 011 (same Coupa company, different roles), only iter 009 had standard fields filled. 010 and 011 left name/email/phone blank too. The smoke runner reported `simplify_autofill_detected: True` for all three — meaning the click happened, but the actual fills didn't always land. This is a Simplify-on-Lever race condition, not an worker-side bug.

**Custom-question structure (gold for an agent):** every Lever custom question has a hidden input `cards[UUID][baseTemplate]` containing the **full JSON schema** of the card — fields, types, options, required flags. An agent can parse this directly instead of DOM-scraping. Same for `surveysResponses[UUID][baseTemplate]`.

**Common Lever screening Qs we saw on Coupa (iter 009/010/011 are identical because same company):**

| Selector | Verbatim label | Type | Tier |
|---|---|---|---|
| `cards[UUID][field0]` | "How did you learn about this role?" | dropdown (24 sources) | 1 |
| `cards[UUID][field1]` | "Are you now, or have you previously been employed by Coupa?" | Yes/No | 1 (from profile) |
| `cards[UUID][field2]` | "Do you have legal authorization to work in the country where this job is located?" | Yes/No | 1 |
| `cards[UUID][field3]` | "Will you require sponsorship or a visa for employment now or in the future?" | Yes/No | 3 |
| `cards[UUID][field4]` | "Are you fluent in any language other than English? Please specify." | text | 2 |
| `cards[UUID][field5]` | "If your role requires it, would you be prepared to work in the office for 2-3 days per week?" | Yes/No | 2 |

**hCaptcha:** invisible widget loaded at submit-click time only. Does NOT block pre-submit fill or scan. Becomes a hard blocker only if/when we enable auto-submit on Lever.

### 2c. Ashby (Notion)

**What Simplify fills reliably:** `_systemfield_name`, `_systemfield_email`, phone (UUID-named), location (autocomplete), `_systemfield_resume`, LinkedIn URL (UUID-named, via label heuristic), often one EEO race option, occasionally pronouns.

**What Simplify leaves blank (categorical, since no required fields were missed on 3 of 4 runs):**

| Category | Verbatim label | Iters | Tier |
|---|---|---|---|
| Pronouns radio | "What pronouns would you like our team to use when addressing you?" | 005, 012, 013, 014 | 1 |
| Sponsorship Yes/No | "Will you now or in the future require Notion to sponsor an immigration case…" | all | 3 |
| Hybrid attestation | "We work from our offices on Mondays, Tuesdays, and Thursdays (Anchor Days)…" | all NY/SF roles | 2 |
| Source multi-select | "How did you hear about this opportunity? (select all that apply)" | all | 1 |
| EEO: gender | "Gender" → Male / Female / Decline | all US roles | 3 |
| EEO: race/ethnicity | "Race" → Hispanic / White / … / Decline | all US roles | 3 (Simplify sometimes clicks "Decline") |
| EEO: veteran | "Veteran Status" → 3-option | all US roles | 3 |

**React-controlled input risk (CONFIRMED by sub-agent):** between `dom_pre.html` and `dom_post.html`, Ashby's EEO fieldset UUIDs change (component re-mounts). Any value written before re-mount is discarded. **The finisher must wait for stable mount (300+ ms idle) and re-verify after every fill.** No literal `checked` HTML attribute survives — state lives in React only.

**Custom-question detection:** every Ashby custom Q is a `div._fieldEntry_17tft_29.ashby-application-form-field-entry` with a sibling `label._heading_101oc_53.ashby-application-form-question-title`. Multi-option groups are `fieldset._container_1v5e2_29`. Per-form UUIDs in `name=` attributes; option labels in `label._label_1v5e2_43` wrapping hidden inputs (match by DOM proximity, not `for=`).

**Engineering roles** (iters 013 App Sec, 014 SWE Data Platform): **0 required unresolved on both**. Notion's engineering Ashby forms are surprisingly clean — same canonical questions as BDR, no extra coding/take-home/portfolio Qs surfaced as required.

---

## 3. Implications for the Layer-3 finisher

### 3a. The "what does the agent actually do" picture per ATS

| ATS | Agent's job on a typical form | Worth building the agent? |
|---|---|---|
| **Ashby** | Fill 4-6 silent-skip fields (pronouns, sponsorship, source, hybrid, EEO). All deterministic — profile lookups + dropdown fuzzy match. No essays. | ✅ Yes — agent is mostly a defer-policy enforcer + dropdown matcher. **Not** an LLM-generation problem. |
| **Greenhouse** | Fill 4-10 dropdowns + 0-2 essays. Phone widget + country combobox always present. Sponsorship/EEO always defer. Essays only on subset of roles. | ✅ Yes — moderate LLM use for essays only; the rest is deterministic. |
| **Lever** | Fill EVERYTHING because Simplify is unreliable. Standard fields + `cards[…]` Qs. The `baseTemplate` JSON gives the agent clean structured data. | ⚠️ Yes, but agent must own the whole form — bigger lift than Ashby/Greenhouse. |

### 3b. Defer rules to centralize (`config/defer_rules.yaml`)

```yaml
# Tier 3 — always defer to human review, never auto-fill
always_defer_labels:
  - regex: '(?i)sponsor|visa|authorize.*sponsor'
  - regex: '(?i)veteran|disability|ethnicity|gender|race|self.?identify'
  - regex: '(?i)salary|compensation|desired pay'
  - regex: '(?i)start date|when can you start|earliest start'

# Tier 2 — draft + flag (LLM-generated, mark needs_review=True)
draft_and_flag_labels:
  - regex: '(?i)why .{0,30}(this role|this position|us|company|interest)'
  - regex: '(?i)tell us about|describe.*experience|hardest problem'
  - regex: '(?i)cover letter'

# Tier 1 default: profile-direct lookup + dropdown fuzzy match
```

### 3c. The phantom-input scanner fix (Greenhouse-specific, but cheap)

`src/agents/apply_worker/field_scanner.py` should skip an `input:nth-child(1)` with no label, no id, and no name when its closest ancestor with `[role="combobox"]` already has a separate visible input. That alone cuts Greenhouse reported gaps roughly in half.

### 3d. The Simplify intermittent-fill problem (Lever-specific)

`_run_application_flow` reports `simplify_autofill_detected=True` based on the click status. It should also **verify by reading 2-3 known input values** (e.g., `_systemfield_email` for Ashby, `name`+`email` for Lever, `first_name`+`email` for Greenhouse) after the 8s settle. If those are still empty after the click, the finisher should treat the form as un-autofilled and start from scratch.

### 3e. The "minimum viable autofill" path

For a v1 "click Auto Apply, it works" experience:
- **Ashby** is shippable today with just deterministic fills for the 6 silent-skip categories. No LLM needed.
- **Greenhouse** is shippable today **without essays** — defer any role with required textareas; fill the dropdowns deterministically. 80% coverage of jobs.
- **Lever** needs the agent to own the entire form. Defer-by-default while we build it; ship later.

---

## 4. Open questions / things this synthesis can't answer

- **Form variability across companies on the same ATS.** We only tested Cloudflare on Greenhouse, Coupa on Lever, Notion on Ashby. Other companies on the same ATS may have radically different custom-Q sets. Especially: Greenhouse with NO EEO block (international roles), Lever with `comments` textarea, Ashby with `_systemfield_compensation`.
- **How Simplify behaves when the user is NOT logged into the Simplify account.** Our cloned profile is signed in; non-onboarded users will see different behavior.
- **The "Apply on company site" redirect path** from aggregators (Indeed, Glassdoor). Out of scope for this study; deferred to v2.
- **LinkedIn Easy Apply.** Out of scope for this study; deferred to v2.
- **Whether the React re-mount on Ashby EEO breaks Simplify's pre-fill or only ours.** Worth a targeted experiment: observe Simplify's behavior step-by-step on Ashby EEO.
