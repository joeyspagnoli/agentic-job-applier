# Filling Simplify's Gaps — Scaffold Proposal

> Working draft. Pattern data from iterations 19-N (greenhouse-only initially, more ATSes survey in progress).

## Where Simplify falls short — observed categories

After Simplify Autofill clicks (passing iterations only), we consistently see these categories of fields left empty. Counts are aggregated across iterations 19-24 (Anthropic + Scale AI; ~80 unresolved fields total).

### High-confidence Simplify gaps (LLM or profile-fill required)

| Category | Count | Required | What it looks like | Resolvable how? |
|----------|------:|---------:|--------------------|-----------------|
| `work_authorization` | 8 | **8 / 8** | "Are you legally authorized to work in [country]?" "Will you require company sponsorship?" | **Profile** (yes/no boolean per country) — never LLM |
| `consent_checkbox` | 4 | **4 / 4** | "AI Policy for Application*", "Are you bound by agreements with prior employer?" | **Profile** (default consent values) + **LLM** for nuanced phrasing |
| `work_mode` | 4 | 1 | "Open to working in-person at [office] X% of the time?" | **Profile** (in-office tolerance) — LLM if needed for tone |
| `relocation` | 2 | 1 | "Open to relocating?" "What's your address — type 'relocating' if you'd relocate" | **Profile** + **LLM** for the "type 'relocating'" instruction |
| `freeform_motivation` (cover letter etc.) | 0-1 | 1+ | "Why are you interested in [company]?" "What excites you about this role?" | **LLM** (job-context-aware) |
| `start_date` | 1 | 0 | "When can you start?" | **Profile** (earliest_start_date) |
| Country (label `Country`) | 6 | 1 | Greenhouse typeahead — `<input type="text">` | **Profile** + **typeahead-aware filler** (special UI) |

### Medium-confidence gaps (Simplify partially fills)

| Category | Count | Required | Notes |
|----------|------:|---------:|-------|
| `email` | 2 | **2** | Simplify usually fills primary email; the unresolved cases are likely SECONDARY email fields. **Profile** |
| `phone` | 3 | 1 | Same: secondary phone fields. **Profile** |
| `linkedin_url` / `portfolio_url` | 7 | 0 | Simplify sometimes fills, sometimes not. **Profile** |
| `demographics` | 3 | 0 | Gender / Veteran / Disability dropdowns. Always optional. **Profile** with "decline to answer" defaults |
| `file_upload` (extra) | 6 | 0 | Optional transcript / cover-letter PDF uploads. Defer (or **profile** with optional file paths). |

### Likely false positives — fix in scanner, not in agent

| Pattern | Count | Fix |
|---------|------:|-----|
| `field_type=search` with placeholder "Search" | 6 | Greenhouse autocomplete UI inputs. Skip in `field_scanner.py`. |
| `field_type=text` with selector `input:nth-child(1)`, no label, no placeholder, marked required | 17 | Likely the hidden text-input portion of an autocomplete — same field as the typeahead. De-dupe. |

These ~23 "fields" inflate the unresolved count without representing real gaps. Removing them would put the avg unresolved-required-count from ~5 down to ~2 per application.

---

## Architecture proposal

### Two-layer fill strategy

```
                     ┌──────────────────────────────────┐
                     │   Simplify Autofill (existing)   │
                     │   ─ resume, name, email, etc.    │
                     └──────────────┬───────────────────┘
                                    │
                                    ▼
                  ┌─────────────────────────────────────┐
                  │ unresolved_fields scanner (existing) │
                  └────────────┬────────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                │                              │
                ▼                              ▼
   ┌──────────────────────────┐   ┌────────────────────────────┐
   │ Layer 1 — Profile Fill   │   │ Layer 2 — LLM Field Agent  │
   │                          │   │                            │
   │ Direct lookup from       │   │ Single-shot: feed the      │
   │ candidate_profile.yaml   │   │ field {label, type, options,│
   │ for known categories:    │   │ context} + candidate profile│
   │ ─ work_authorization     │   │ + job description, ask for │
   │ ─ work_mode              │   │ a value.                   │
   │ ─ relocation             │   │                            │
   │ ─ start_date             │   │ Used for:                  │
   │ ─ consent_defaults       │   │ ─ freeform_motivation       │
   │ ─ email/phone alternates │   │ ─ "Anything else?" textareas│
   │ ─ demographics defaults  │   │ ─ unfamiliar custom Qs      │
   └──────────────────────────┘   └────────────────────────────┘
                │                              │
                └──────────────┬───────────────┘
                               │
                               ▼
                ┌─────────────────────────────┐
                │ Apply Filler (Playwright)   │
                │ ─ Fill text/select/checkbox  │
                │ ─ Handle typeahead UI        │
                │   (country, school)          │
                │ ─ Re-scan for remaining      │
                │   unresolved fields          │
                └──────────────────────────────┘
                               │
                               ▼
              Confidence score → NEEDS_REVIEW / SUBMITTED
```

### Why two layers?

- **Profile fill** (Layer 1) is deterministic, fast, free, and covers the biggest category by frequency (work authorization × 8, consent × 4, work mode × 4, etc.). One-time profile setup; reuse forever.
- **LLM field agent** (Layer 2) handles the long tail — every job has 1-3 unique freeform questions ("why this role specifically?") that can't be templated. Per-question LLM call is cheap and scoped: just the field metadata + the profile + the JD = ~2k input tokens, ~200 output. ~$0.001-0.005 per question.

### Concrete profile schema additions

Add to `config/candidate_profile.yaml` (or a new `apply_answers.yaml`):

```yaml
apply_answers:
  work_authorization:
    US: { authorized: true, requires_sponsorship: false }
    UK: { authorized: false, requires_sponsorship: true }
    CA: { authorized: false, requires_sponsorship: true }
    EU: { authorized: false, requires_sponsorship: true }
  work_mode:
    in_office_tolerance: "open_hybrid"   # "fully_remote" | "open_hybrid" | "in_office_ok"
    in_office_days_max: 3
  relocation:
    willing: true
    locations_acceptable: ["San Francisco, CA", "New York, NY", "Remote"]
  start_date:
    earliest: "2026-06-01"
    notice_period_weeks: 2
  consent_defaults:
    accept_ai_policy: true
    accept_data_sharing: true
    employer_agreements_clean: true   # not bound by NDAs/non-competes
  contact_secondary:
    phone: "+1-555-555-1234"
    email: "joe@example.com"
  demographics:
    gender: "decline_to_answer"
    veteran_status: "decline_to_answer"
    disability_status: "decline_to_answer"
    pronouns: "he/him"
```

### Field-to-profile mapper

Pure code, no LLM. `src/agents/apply_worker/field_filler/profile_fill.py`:

```python
def fill_from_profile(field: UnresolvedField, profile: ApplyAnswers) -> str | None:
    """Map a labeled field to its profile-derived answer.

    Returns the value to type, or None if the profile doesn't cover this field.
    """
    label_lower = (field.label or "").lower()

    # Work authorization
    if any(k in label_lower for k in ("authorized to work", "right to work")):
        country = _extract_country_from_label(label_lower)
        return _yes_no(profile.work_authorization[country].authorized)
    if "sponsorship" in label_lower or "visa" in label_lower:
        country = _extract_country_from_label(label_lower)
        return _yes_no(profile.work_authorization[country].requires_sponsorship)

    # Work mode
    if "in person" in label_lower or "in-person" in label_lower:
        return _yes_no(profile.work_mode.in_office_tolerance != "fully_remote")

    # ... etc
    return None
```

### LLM field agent

`src/agents/apply_worker/field_filler/llm_fill.py`:

Per-field prompt:

```
You are filling out a job application. Provide a value for this field.

Field label: {field.label}
Field type: {field.field_type}
Field options: {field.options or "free text"}
Required: {field.is_required}

Job context:
- Company: {job.company}
- Title: {job.title}
- Description excerpt: {job.description[:500]}

Candidate profile:
{candidate_profile.summary}
Skills: {candidate_profile.skills}
Target roles: {candidate_profile.target_roles}

Constraints:
- Match the field type and options exactly when applicable.
- Cover-letter / "why interested" answers: 2-4 sentences, specific, no
  fluff, mention 1-2 things from the JD.
- Yes/no answers: just "Yes" or "No". No explanation.
- If you don't have enough information, return "NEEDS_HUMAN_REVIEW".

Output only the value, no preamble.
```

Cost ceiling per application: 5 freeform questions × $0.005 = ~$0.025. Cheap.

### Typeahead handler (one of the trickier UIs)

Greenhouse "Country" is a typeahead `<input type="text">` that opens a dropdown. We need to:

1. Detect typeahead via the surrounding `<datalist>` or sibling `<ul role="listbox">`.
2. Click the input to focus.
3. Type the country name slowly (or use `Input.dispatchKeyEvent`).
4. Wait for the dropdown to populate.
5. Click the matching `<li>` option.

This is well-known territory. Playwright's `Locator.fill()` won't work; we need a custom helper.

### Confidence + submit gating

Before any future auto-submit:

```python
gate = (
    confidence.score >= 0.85
    and confidence.unresolved_required_count == 0
    and confidence.has_hard_blockers is False
    and not any(f.contains_forbidden_label("submit") for f in scanned_buttons)
    and llm_fills_below_threshold(profile.max_per_app_llm_cost_usd)
)
```

Even with the gate, default behavior stays NEEDS_REVIEW. Auto-submit only after a manual opt-in flag in the candidate profile (+ a daily cap).

---

## Sequencing (what to build first)

| Order | Item | Estimated effort |
|------:|------|------------------|
| 1 | Fix `field_scanner.py` false positives (`search`-type, `input:nth-child(1)` no-label) | 1-2 hours |
| 2 | Profile schema additions (`apply_answers.yaml`) + loader | 2-3 hours |
| 3 | `profile_fill.py` field-to-answer mapper for the top 5 categories | 4-6 hours |
| 4 | Typeahead handler for Country (and similar Greenhouse autocompletes) | 4-6 hours |
| 5 | LLM field agent (single-shot per field) — start with cover-letter / motivation | 1 day |
| 6 | Integration: call profile_fill → llm_fill → re-scan in `_run_application_flow` | half day |
| 7 | Per-iteration evaluation: re-run survey, measure how many remaining unresolved-required after layer 1 + 2 | half day |

After step 7 we should see avg unresolved-required drop from ~3-4 per application to ~0-1 (the truly novel questions a human still wants to vet).

---

## Open questions

1. **Should the LLM see Simplify's already-filled values as context?** Probably yes — "name a strength" is harder if you don't know what experience the user is highlighting.
2. **Should the cover letter be generated once per company, cached, then re-used?** Yes, with a job-specific 1-line tailoring opener. Cuts cost 5×.
3. **LinkedIn-style pre-filled forms** (Easy Apply): different game; out of scope for v1.

---

## Cross-ATS notes (sweep through 2026-05-07)

### Ashby (jobs.ashbyhq.com) — Simplify supported but different UI

Probed `https://jobs.ashbyhq.com/Linear/...`. Findings:

- Simplify DOES inject 2 `simplify-jobs-shadow-root` hosts (banner + side panel).
- Side panel size ~26.7kb (vs Greenhouse's ~27.2kb).
- Side panel **lacks an `aria-label="Autofill"` button** even though there's a button with text content "Autofill". Other aria-labels: `Open job tracker`, `Tailor Resume`, `Settings`, `Minimize`, `Close`, `Hide this message`, `Collapse Resume Section`.
- The Linear listing URLs (`/Linear/<uuid>`) are job descriptions; the actual application form is on a separate URL accessed via "Apply" button click.
- **Implication**: our `_JS_DETECT_SIMPLIFY` and `_JS_CLICK_SIMPLIFY_AUTOFILL` need to fall back from `aria-label="Autofill"` to button text content matching `^(Autofill|Fill)$`.

### Lever / Workday — not yet sweeped

Pulled APIs but Lever boards I tried (eventbrite, tubitv, ramp) returned 404. Need a known-working Lever board. Workday: `nvidia.wd5.myworkdayjobs.com` returned 200 — could test next session.

### True patterns across the survey

After 9 PASS iterations across 4 distinct Greenhouse companies (Anthropic ×4, Scale AI ×3, Figma ×1, Cloudflare ×1):

**Always-required, always-fail-to-Simplify** (top priority):

- `work_authorization` × 12 (3 distinct phrasings, all map to 2 booleans: authorized + needs_sponsorship)
- `freeform_motivation` × 4-5 ("Why Anthropic?", "Why do you want to join Figma?", "Why are you interested?")
- `consent_checkbox` × 4 (AI Policy, employer-agreements binding question)
- `work_mode` × 2 ("Open to in-person 25%?")
- `location.country` × 4 (typeahead — needs special UI handling)
- `referral_source` × 1 ("How did you hear about this job?")
- `yes_no_history` × 2 ("Have you worked here before?", "Have you interviewed before?")
- `name_last` × 1 (Figma — Simplify missed it)
- `location.work_from` × 1 ("From where do you intend to work?")

**Sometimes-required, partially-filled** (medium priority):
- `email` × 2 / `phone` × 2 — secondary contact fields

**Always-optional, sometimes-filled** (defer):
- `linkedin_url`, `portfolio_url`, `demographics`, `file_upload` (extra resume/transcript)

**False positives** (fix scanner first):
- 29 of 138 unresolved fields are the same `<input class>` repeated (`input:nth-child(1)` with no label). These are Greenhouse autocomplete UI internals.
- 6 of 138 are `<input type="search">` with placeholder "Search" — Greenhouse typeahead inputs.

### Effective gap (after scanner fix)

Of 138 unresolved fields across 9 PASS iterations: **138 - 35 false positives = ~103 real fields**, of which **~35 are required** (avg 3.9 per application). After Layer 1 (profile fill) on the top 6 categories: **~5 required fields remain** (avg 0.6 per application — the freeform motivation Qs that need the LLM).

---

## Recommendation: build path forward

1. **Immediate (1 day): Ship the scanner fix.** De-dupe by element identity, skip placeholderless no-label no-id inputs, skip search-type fields. This alone drops avg unresolved-required from 3.9 to ~1.5 with no AI work.
2. **Layer 1 (3 days): Profile-fill mapper.** Cover the top 6 required categories. After this, avg unresolved-required is ~0.6 — basically just the "Why this company?" question per application.
3. **Layer 2 (1-2 days): LLM field agent.** Single-shot per remaining unresolved field. Cap cost at $0.05 per application. Use cached company-cover-letters with per-job opener.
4. **Cross-ATS (1 day): Generalize click selectors.** Add fallback to button-text matching for Ashby. Survey Lever + Workday.
5. **Submit gate (half day): Auto-submit only when `unresolved_required == 0` AND user has explicit per-day opt-in flag.**

Total: ~7-8 days of focused work to go from "submit-ready except 0.6 fields per app" to "true zero-touch submit on apps where confidence is high."
