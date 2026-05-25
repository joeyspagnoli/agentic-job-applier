# analysis-015 — Defer policy, the "keep filling on defer" loop, and the persistent answer cache

**Date:** 2026-05-24  
**Mode:** Design  
**Built on:** `analysis-010-final-synthesis.md` (Layer-3 finisher architecture), `local-001-current-apply-pipeline.md` (handoff schema)  
**Trigger:** User question about the trust threshold between agent-answered and human-deferred fields, plus a Q→A cache to avoid re-asking the same human questions.

---

## 1. The three-tier trust model

Every form field falls into exactly one of three tiers. The agent decides per-field based on **deterministic rules first, model judgment second.**

```
┌────────────────────────────────────────────────────────────────────┐
│ TIER 1 — AUTO-FILL (no flag, no defer)                              │
│ Direct match against candidate_profile.yaml + the answer cache.    │
│ Examples: name, email, phone, city/state, LinkedIn URL,            │
│   work-history dates, education dates, GPA, file upload (resume).  │
│ Selects where one option string EXACTLY matches the profile value. │
└────────────────────────────────────────────────────────────────────┘
                              │
              if no profile / cache hit AND not Tier 3
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│ TIER 2 — DRAFT + FLAG (agent fills, reviewer verifies before       │
│         submit; never blocks the loop)                              │
│ Examples: "Why $COMPANY?" essays, behavioral stories,              │
│   fuzzy-matched dropdowns ("United States" → "United States of     │
│   America"), multi-select preferences, cover-letter fields.        │
│ Agent uses cache lookup first; falls back to profile-grounded     │
│   drafting; persists confidence + reasoning into the handoff row. │
└────────────────────────────────────────────────────────────────────┘
                              │
              if label matches the always-defer ruleset
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│ TIER 3 — DEFER (agent never fills; loop continues past defer)      │
│ Examples: EEO / race / gender / veteran / disability self-id,     │
│   salary expectation, start date, sponsorship text fields,         │
│   visa-status details beyond yes/no, anything legally loaded.     │
│ Agent calls `defer(field_id, reason, question_text)` and moves on.│
└────────────────────────────────────────────────────────────────────┘
```

**The threshold is rule-driven for Tier 3 (defense by ignorance + denial hook, same triple-defense as the no-Submit rule), profile/cache-driven for Tier 1, and model judgment for Tier 2.** This means the model cannot accidentally answer an EEO question — the snapshot filter strips Tier-3 fields from the AX-tree the model sees, and even if a label slips through (e.g., "Self-Identification" without the EEO keyword), the `before_tool_callback` hook denies any non-defer tool call against a Tier-3 field.

---

## 2. The Tier-3 deny-list (config-driven, user-tunable)

Live in a new `config/defer_rules.yaml`. Same shape and location convention as `candidate_profile.yaml` / `companies.yaml` / `filters.yaml`. Pre-seeded for the dist/ workflow.

```yaml
# config/defer_rules.yaml
# Field label keywords that trigger Tier-3 defer. Match is case-insensitive
# substring against the field's accessible name + nearby help text.

always_defer_keywords:
  # EEO / demographics (legal sensitivity + user choice)
  - eeo
  - equal employment
  - race
  - ethnicity
  - hispanic
  - gender identity
  - sexual orientation
  - veteran status
  - protected veteran
  - disability
  - self-identification
  - voluntary self
  # Financial / commitment
  - salary expectation
  - desired salary
  - compensation expectation
  - start date
  - earliest start
  - notice period
  # Legal / visa text (yes/no is OK; free-text is not)
  - visa details
  - sponsorship explanation
  - work authorization explanation
  - immigration

# Override list — labels that match keywords above but should NOT defer.
# Example: a "Race" column in a school history grid; rare but possible.
never_defer_overrides: []

# Field types that bypass deny-list matching entirely.
# File inputs and hidden inputs never need defer.
bypass_field_types:
  - file
  - hidden
  - submit
  - button
```

The rule check is **the snapshot filter**: when serializing the AX-tree for the model, any field whose label hits `always_defer_keywords` AND is not in `never_defer_overrides` is marked with a `[DEFER]` tag in the snapshot. The model is *told in the system prompt* that `[DEFER]`-tagged fields can only be acted on with the `defer()` tool, not `type()` or `select()`. Plus the denial hook enforces it.

---

## 3. The "keep filling on defer, never bail" loop

This is a key change from today's flow. Currently the worker fills what Simplify autofilled, finds unresolved fields, bails to NEEDS_REVIEW. The Layer-3 finisher with deferrals works differently:

```
agent loop:
  while turns < max_turns and not done:
    ax_tree = snapshot()              # tool 1
    for each unfilled field in ax_tree:
      if field.tag == [DEFER]:
        defer(field.ref, reason, question_text)    # tool 6 — DOES NOT exit loop
        continue
      elif cache.lookup(field.question_text):
        type(field.ref, cache.value)               # tool 3
      elif profile.lookup(field.label):
        type/select(field.ref, profile.value)      # tool 3 or 4
      else:
        type(field.ref, draft_answer)              # Tier 2 — model authors
        flag_for_verify(field.ref, confidence)     # tool 7
    if all_fields_handled(ax_tree):
      complete_apply()                              # tool 8 — clean exit
      break
```

Concretely:

- **`defer(field_id, reason, question_text)`** is just a recording tool. It writes to a per-run `deferred_questions[]` list in the agent's `tool_context.state` (ADK) or run-state (Pydantic AI / OpenAI). **It does not stop the loop.** The agent keeps fielding the next snapshot.
- **`complete_apply()`** is the clean exit. The agent calls it when there's nothing left to do (filled or deferred). The harness's `after_tool_callback` checks this and breaks the loop.
- **Run cap** (`max_turns=25`, `max_llm_calls=40`) bounds the loop independently — if the agent loops without progress, the cap fires and the worker still bails to NEEDS_REVIEW (just with fewer fields filled).

**Outcome shape:**
```python
# Layer-3 returns this back to browser.py
FinisherResult(
    turns_used=12,
    cost_usd=0.0085,
    fields_filled=18,              # Tier 1 (auto) + Tier 2 (drafted)
    fields_deferred=3,             # Tier 3 (and cache-miss Tier 2 the agent chose to defer)
    deferred_questions=[
        {"field_id": "salary_expect", "question": "What are your salary expectations?", "reason": "tier3_keyword:salary expectation"},
        {"field_id": "self_id_race", "question": "Race / Ethnicity (Voluntary Self-Identification)", "reason": "tier3_keyword:self-identification"},
        {"field_id": "custom_q_4", "question": "Tell us about a project you're particularly proud of.", "reason": "tier2_low_confidence_no_cache"},
    ],
    fields_drafted_flagged_for_verify=[...],   # Tier 2 fills that want review
    outcome="COMPLETE",                          # or "AGENT_GAVE_UP" / "COST_CEILING_HIT"
)
```

The worker continues to its existing NEEDS_REVIEW exit. The handoff row gets the new data.

---

## 4. Data-model change (small)

Add two columns to `apply_handoffs` (`src/database/_mixins/apply.py:83`):

```sql
ALTER TABLE apply_handoffs ADD COLUMN deferred_questions_json TEXT;
ALTER TABLE apply_handoffs ADD COLUMN finisher_diagnostics_json TEXT;
```

- `deferred_questions_json` — array of `{field_id, question_text, reason, normalized_question_hash}`. Surfaced in the human-review UI as "questions to answer."
- `finisher_diagnostics_json` — `{turns_used, cost_usd, model, fields_filled, fields_drafted_flagged, outcome}`. Telemetry for analyzing what the agent did over time.

The existing `unresolved_fields_json` keeps its current meaning ("fields the agent couldn't even attempt"). The new column is "fields the agent deliberately chose not to answer." Different signal, different action by the reviewer.

No schema change needed beyond those two columns. The existing `idx_apply_handoffs_status` index continues to drive the queue listing.

---

## 5. The answer cache — format, location, retrieval

### 5a. File format: YAML, not JSON

Reasoning:
- All other user-edited config is YAML (`candidate_profile.yaml`, `companies.yaml`, `filters.yaml`, `search_criteria.yaml`).
- YAML supports comments + multiline strings cleanly — essential for "Why $COMPANY?" answers that are 200-400 words and may have inline guidance.
- JSON would force escaped `\n` everywhere and forbid comments. Bad UX for the user editing the cache by hand.

JSONL would suit an append-only event log; YAML suits a curated knowledge base. The cache is the latter.

### 5b. Location: `data/answer_cache.yaml`

NOT `config/` — this is **machine-mutable runtime state** that the agent writes to. `config/` is human-curated. Use `data/` (already gitignored except the directory itself, matching the convention used for `data/tailored_resumes/`, `data/apply_runs/`).

For users who want to seed answers manually before any applies run, the onboard-user skill can seed `data/answer_cache.yaml` with starter entries from a template.

### 5c. Schema

```yaml
# data/answer_cache.yaml — schema version 1
schema_version: 1
entries:
  - question_hash: "f3a8b2…"            # sha256(normalize(question_text))[:16]
    question_text: "Why are you interested in working at $COMPANY?"
    question_normalized: "why are you interested in working at $company"
    category: why_company                 # one of the categories below
    field_type: textarea
    company_specific: false               # if true, answer is bound to one company
    answer: |-
      I am drawn to $COMPANY because… (multiline; $COMPANY is the substitution
      token that's replaced with the actual company name at use-time).
    metadata:
      created_at: 2026-05-24T16:42:11Z
      last_used_at: 2026-05-24T16:42:11Z
      use_count: 1
      seeded_by: human                    # or "agent_drafted_and_user_approved"
      confidence: high                    # human | high | medium | low
```

**Categories** (closed enum):
- `why_company`, `why_role`, `cover_letter`
- `behavioral` (Tell us about a time you…)
- `strengths_weaknesses`
- `availability` (start date — but Tier 3, so cache lives but isn't auto-applied without confirmation)
- `salary` (Tier 3)
- `visa_yes_no` (yes/no only; details are Tier 3)
- `referral`, `how_did_you_hear`
- `multi_select_preferences`
- `custom_long_form`, `custom_short_form`
- `other`

### 5d. Retrieval (start dumb, evolve)

Version 1 (ship this):

```python
def lookup_cached_answer(question_text: str, *, company: str) -> str | None:
    # 1. Exact normalized-hash match  → O(1)
    h = sha256(normalize(question_text)).hexdigest()[:16]
    hit = exact_lookup(h)
    if hit:
        return substitute_company(hit.answer, company)
    
    # 2. Fuzzy match on normalized text  → O(n) but n is small
    best = max(
        ((rapidfuzz.token_set_ratio(normalize(question_text), e.question_normalized), e)
         for e in cache.entries),
        default=(0, None),
    )
    if best[0] >= 85:
        return substitute_company(best[1].answer, company)
    
    return None
```

`normalize()` = lowercase, strip punctuation, collapse whitespace, replace company names with `$COMPANY` token. `substitute_company()` reverses the token at retrieval time.

Add `rapidfuzz` as a pinned dep (it's tiny, MIT, pure-Rust-backed, very common). Or hand-roll Levenshtein in ~30 lines if we want zero new deps.

Version 2 (if cache exceeds ~500 entries OR we observe Version-1 misses on close paraphrases): add embedding-based retrieval. Use the same OpenAI account, `text-embedding-3-small` ($0.02/MTok). Index on write, search on read. Maintain backwards compat with the YAML file by storing the embedding inline as a list.

### 5e. The cache as an agent tool

Register `lookup_cached_answer` as one of the 6 (now 8) Layer-3 tools:

```python
@function_tool
async def lookup_cached_answer(question_text: str) -> dict:
    """Look up a past answer to a similar question. Returns {found: bool, answer: str | None, similarity: float}."""
```

The system prompt instructs the agent to call `lookup_cached_answer` BEFORE drafting any open-ended response. Cache hits flow directly to `type()`. Cache misses fall through to either draft (Tier 2) or `defer()` (if confidence is low).

---

## 6. The write-back loop: how the cache grows

```
1. Apply finishes with `deferred_questions=[Q1, Q2, Q3]`.
2. Reviewer opens the human-review row in the UI.
3. UI shows: "3 questions need your answer:" + a text input per question.
4. Reviewer answers Q1, Q2, Q3 → POST /api/human-review/{handoff_id}/answers
   { answers: [{question_hash, answer_text}, ...] }
5. Backend:
   a. Persists answers into the apply_handoffs row (for audit).
   b. Appends each {question, answer} to data/answer_cache.yaml as a new entry
      with seeded_by="human", confidence="high".
   c. If the reviewer also clicks "approve + submit", the agent can be re-invoked
      (later — phase 2) to actually click Submit with the human's answers in place.
6. Next apply that hits a similar question → cache returns the answer → Tier 1 fill.
```

**Pragmatic v1: skip the re-invoke loop.** The reviewer types answers in the UI, the cache is updated, the reviewer still has to manually paste those answers into the form themselves OR the worker just bails to NEEDS_REVIEW and the human types them in the actual browser. The cache pays off on *the next apply*, not this one. Simpler to ship.

**Phase 2 (later):** After the reviewer completes the questions in the UI, automatically re-run the agent against the same handoff with the answers in the cache. The agent re-fills the previously-deferred fields. Submit remains human-only.

---

## 7. UI surface

**Failures page** (`api/routers/failures.py`) is for the wrong concern — that's for `apply_runs.status='FAILED'` rows where the worker errored out (Chrome unreachable, navigation failed, etc.). Deferrals are not failures.

**Human-in-the-loop tab** (`api/routers/human_review.py` → existing dashboard route) is the right home. Today it shows:
- Company / position / status / confidence%
- Apply date / outcome / ATS platform
- Source URL / resume filename
- **`unresolved_fields`** — what Simplify left empty

Extend the same row payload with:
- **`deferred_questions`** — list of `{question_text, category, reason}`. Each rendered as a labeled textarea with a "Save answer to cache" checkbox (default on).
- **`drafted_fields_flagged_for_verify`** — list of `{label, drafted_value, confidence, reasoning}`. Renderer is a side-by-side "agent's draft" / "your version" diff.
- **`finisher_diagnostics`** — small footer showing turns + cost + outcome.

**New endpoint:** `POST /api/human-review/{handoff_id}/answers` (the cache-write hook from §6).

---

## 8. The trust threshold, summarized as one rule

> **A field is Tier 3 (always-defer) if its label matches the `defer_rules.yaml` deny-list. A field is Tier 1 (auto-fill) if `profile.lookup(field) is not None` OR `cache.lookup(question) returns hit`. Otherwise it is Tier 2 (draft + flag).**

The Tier-3 list is the only thing the user MUST curate. Tiers 1 and 2 derive from `candidate_profile.yaml` + the growing answer cache + the model's judgment, all of which the user already maintains in normal use.

The threshold *shifts toward Tier 1 over time as the cache fills*. After 50-100 applies, common questions like "Why $COMPANY?", behavioral stories, and standard preferences are all cached and become Tier 1. The user's review workload shrinks proportionally.

---

## 9. What does NOT change

- Auto-submit stays hard-disabled. SECURITY.md. Triple-defense. Even if every field is Tier 1 and every question is cached, the worker still bails to NEEDS_REVIEW. The human always clicks Submit.
- The `apply_handoffs` row still gates the workflow. New columns; same table; same status enum.
- The polling loop, claim mechanism, retry/backoff, cost telemetry in `process_apply_jobs.py` — untouched.
- The Tier-3 list is config; the user can add keywords or override them in their dist/.

---

## 10. Implementation order (smallest-to-largest)

1. **Add `defer_rules.yaml` + schema migration for the two new columns.** No agent changes. Existing flow unchanged.
2. **Build the answer cache module** (`src/agents/apply_finisher/answer_cache.py`) — YAML read/write, normalize, hash, fuzzy lookup. Unit tests on a fixture cache file. No agent integration yet.
3. **Build the Layer-3 finisher with all 8 tools** (snapshot, click, type, select, wait_for, goto, defer, complete_apply, lookup_cached_answer) — note this is 9 now; rename "6 tools" earlier to "8 tools" in subsequent docs.
4. **Wire the finisher into `browser.py:347-376`.** Telemetry flows. NEEDS_REVIEW exit unchanged.
5. **Extend the human-review UI to render deferred questions + the answer textareas + cache-write checkbox.** Endpoint `POST /api/human-review/{handoff_id}/answers`.
6. **(Phase 2 — later)** Re-invoke the agent after the reviewer fills cached answers, to fill the previously-deferred fields without human re-typing. Still no Submit.

Steps 1-3 are independent of the harness decision and can ship before Layer-3 itself. They benefit existing operators too (the `defer_rules.yaml` could even be honored by the existing `field_scanner.py` to mark unresolved fields with a "category" hint today).

---

## 11. Open questions for the user

1. **Is the Tier-3 deny-list complete?** I've drafted a starter set in §2. The user knows what their specific applications actually ask; they should sanity-check.
2. **Should "salary expectation" be Tier 3 or Tier 2?** I have it as Tier 3 (financial commitment) but if the user has a standard answer ("$X-$Y range, negotiable based on…"), it could be a cached Tier 1 answer instead.
3. **Should the cache be company-anonymized by default?** I assume yes (the `$COMPANY` substitution token) so a "Why X?" answer for Anthropic adapts to "Why Y?" for OpenAI. The user might prefer per-company cache entries.
4. **Phase-2 re-invoke**: ship it together with Phase 1, or defer until we observe the friction of the user manually re-typing answers in the actual browser?
5. **`drafted_fields_flagged_for_verify`** — should the agent draft Tier 2 at all on cache miss, or always defer? Drafting saves the reviewer time when the agent is right; costs them time when the agent is wrong. Recommend ON by default; user can override via a `tier2_strategy: draft|defer|always_cache` setting in `defer_rules.yaml`.
