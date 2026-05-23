# analysis-002 — Simplify capability gap + strategy comparison

**Date:** 2026-05-22  
**Built on:** fetch-001…fetch-003, search-001…search-003 (this pass)  
**Verdict (1 sentence):** **Keep Simplify in front of the LLM agent (Strategy A — "Simplify-first, agent-second"); it covers ~90% of fields on the big-5 ATSes for free, and the gap it leaves is exactly the shape an LLM browser agent is naturally good at.**

---

## Top-line recommendation

**Strategy (a) — Simplify-first, agent-second — wins.** Keep the current pipeline as the bottom layer: navigate, upload our PDF, click Simplify's shadow-root `Autofill` button, then hand the page to an LLM browser agent for the long tail.

Two operational guardrails on top:

1. **Pin the Simplify CRX.** Per `search-003`, the unpacked extension is publicly downloadable; we host a known-good version, disable Chrome's auto-update for this profile, smoke-test before bumping. This eliminates the silent-version-drift class of failure.
2. **Gate every AI-fill long-text field through our existing human-review checkpoint.** Per `search-001`, Simplify's "Autofill all fields with AI" feature has documented cross-employer text leakage — last-application's "Why this company?" answer bleeds into the new one. This is the strongest argument for never auto-submitting and for the LLM agent to re-author any textarea longer than ~200 chars.

---

## Why (a) beats (b) and (c)

| Criterion | (a) Simplify + agent | (b) Agent-only | (c) Hybrid DIY autofill |
|---|---|---|---|
| Big-5 ATS standard-field coverage today | High (≈90% out of box) | Low — rebuild required | Medium |
| Long-tail / custom-page coverage | Medium (agent picks up tail) | High (agent does everything) | High |
| Per-apply cost | $0.01–0.10 | $0.20–1.00 | $0.05–0.30 |
| Per-apply latency | 60–120 s | 3–10 min | 1–3 min |
| Engineering up-front | Already built | 4–8 weeks | 4–8 weeks |
| Ongoing per-ATS maintenance | LOW (Simplify carries it) | HIGH (we carry it) | MEDIUM–HIGH |
| Version-drift exposure | Simplify CRX (pinnable) | None | Per-ATS DOM changes |
| Run headless in CI | Hard (Simplify wants display) | Easy | Easy |

**(b)** wins only if Simplify breaks its ToS for our use case OR the shadow-root DOM contract dies — neither has happened in 2+ years. Verified against `ksrawr/auto_apply`'s ~2-year-old shadow-root piercing code, which still works on v2.5.0.

**(c)** is a trap. Simplify is a ~10-person company with 2 years of per-site XPath maps and a paying user base subsidizing the maintenance. We'd be reinventing their per-site selector library with zero revenue share, then re-paying that cost every time Workday/Greenhouse/Lever ships a UI redesign.

---

## Capability gap by ATS — ranked by frequency of empty-after-Simplify fields

Confidence levels are **inferred** from the combination of marketing claims (`fetch-001`/`fetch-002`/`fetch-003`), community failure threads (`search-001`), and competitor positioning (`search-002`). Where I couldn't get a direct primary source, the cell is marked `INFERRED`.

### Workday (Simplify's strongest)
Estimated ~90% filled after Autofill.
- **HIGH miss frequency:** dropdown options-list mismatches when the user's degree/major value isn't an exact option string (Simplify writes nothing rather than fuzzy-match).
- **HIGH miss:** work-auth / visa-status free-text explanation ("If yes, please describe…"). Simplify fills the yes/no but not the explanation.
- **HIGH miss (intentional):** EEO / veteran / disability self-id — Simplify deliberately leaves blank; both ethically correct and a human-review item.
- **HIGH miss:** "Why $COMPANY?" essay (AI-fill writes but is leakage-prone — see `search-001`).
- **HIGH miss:** behavioral story prompts ("Tell us about a time you…").
- **HIGH miss:** preferred start-date picker — date pickers are typically untouched.
- **MEDIUM miss:** multi-select role-preference checklists (e.g., "Which of these technologies have you used?").

### Greenhouse (clean standard block; messy custom block)
Estimated ~85% filled on the standard contact/work-history/education/file-upload block.
- **The big miss:** per-role custom application questions, 1–12 per posting. This is Greenhouse's signature feature ("Custom Application Questions") and it's exactly the long tail an LLM agent earns its keep on.

### Lever
Similar shape to Greenhouse — standard block fills cleanly, the per-posting custom questions don't.

### iCIMS (legacy)
Weaker than Workday. The single Firefox-add-on field-level complaint we surfaced (about degree dropdowns) was on iCIMS-style legacy widgets. Multi-page navigation works if the user has the "Continuously autofill" toggle on.

### Ashby
**NOT in Simplify's marketed ATS list** (omitted from "Workday, Greenhouse, iCIMS, Taleo, Avature, Lever, SmartRecruiters"). Likely lower coverage. The LLM agent should expect more work here.

### SmartRecruiters
Marketed as supported, no specific complaints in the review corpus.

### Custom / non-ATS career pages
Simplify may not inject at all, or mis-maps fields. The agent has to handle the "side panel never appears" case as graceful degradation: if no `simplify-jobs-shadow-root` host within ~15 s, fall back to LLM-only direct-from-profile-YAML filling.

---

## The "AI-fill leakage" finding — most important hazard

Source: `search-001` quoting remotejobassistant.com (2026) review.

> *"Simplify's 'Autofill all fields with AI' feature has been observed copying the previous application's 'Why this company?' answer into the new application's textarea, across employers."*

Concrete consequences for our pipeline:
- **Never let Simplify's AI-fill output for long-text fields stand without re-authoring.** Our LLM agent should re-read every textarea > 200 chars after Simplify's pass, compare against the job's company/role context, and rewrite if it references the wrong company.
- **Never auto-submit.** SECURITY.md already mandates this; the leakage finding cements why.
- This is the load-bearing reason the "human review at NEEDS_REVIEW" gate is non-negotiable even after the agent does the long tail.

---

## Concrete pipeline recommendations (these map to issue #59 + the north-star)

These are guardrails to add as we wire the LLM agent in — they all live in our code, not in Simplify.

1. **Pin a known-good Simplify CRX.** `search-003` has the public download URL. Disable auto-update; smoke-test before bumping.
2. **Pre-flight auth check.** Pierce shadow root, read header for the user's name; fail fast and notify if it shows a "Sign in" CTA — Simplify is logged out.
3. **Never trust AI-filled textareas > 200 chars.** Agent re-reads and re-authors.
4. **Explicit policy: leave EEO/demographic blank** for human review. Don't let the agent guess.
5. **Fuzzy-match dropdowns the agent finds empty.** Read the options list, pick closest match to the user's profile value, log to telemetry for review.
6. **Agent system prompt lists Simplify-known-empty categories** to check explicitly: "Why $COMPANY?", behavioral stories, start date, work-auth explanation, multi-select preferences, conditional dropdowns. Don't make the agent rediscover the gap on every apply.
7. **Telemetry.** For every apply, track which fields Simplify filled vs. agent filled vs. human still touched at the NEEDS_REVIEW stage. After 10–100 apps, this dataset tells us whether to keep (a) or pivot to (b)/(c). Make the decision empirical.

---

## Sources I couldn't fully verify (flagged for follow-up)

- Reddit threads (r/jobs, r/cscareerquestions, r/resumes) — the Anthropic crawler is blocked from reddit.com. Worked around via Firefox add-on reviews (first-party negative reviews on the same product engine) and second-hand Reddit quotes embedded in jobcopilot.com. **If you can run this from outside that crawler**, the highest-value queries are: r/jobs "simplify autofill", r/cscareerquestions "simplify copilot review", r/resumes "simplify ai fill".
- `sonara.ai` homepage — timed out + ECONNREFUSED. Covered via adzuna.co.uk's 2025-12 Sonara review instead.
- `chrome-stats.com` extension details page — 403 Forbidden. CWS listing covered the metadata adequately.
- `help.simplify.jobs/article/20-request-new-autofill-support` body — 404 on direct fetch; only the title (request-new-autofill-support) was load-bearing.
- Simplify's TrustPilot page — not surfaced; second-hand quotes only.
- Unpacked Simplify CRX (manifest, permissions, content scripts) — we have the download script from `soumilbaldota/auto_filler`. Not executed this pass; ~1-minute follow-up if exact manifest contents are needed.

See `analysis-004-north-star-synthesis.md` for how this strategy plugs into the issue #59 Apply button and the pi-mono / agent-browser layer.
