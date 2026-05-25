# Research Pass — Finisher Implementation Prerequisites

**Date:** 2026-05-25 03:55:55 UTC
**Mode:** Implementation + Design (mixed)
**Built on:**
- `.research/2026-05-23-232801-agent-harness-decision/` (Pydantic AI choice, BYO Playwright tools, model-choice context)
- `.research/simplify-loop/` (14-iteration empirical smoke run, gap-synthesis.md)
- Issue #59 (locked epic body)
- 2026-05-25 planning conversation (this session)

## Purpose

Fill the research gaps surfaced during the 2026-05-25 planning conversation before implementation of issue #59 begins. Four parallel sub-agents fan out from this pass.

Locked decisions going into this pass (do NOT re-litigate):

1. **Pydantic AI** is the agent harness.
2. **BYO Playwright tools over CDP** (~250 LOC of typed function tools).
3. **Greenhouse + Ashby** are the v1 ATS set.
4. **3-tier trust model** (Tier 1 auto-fill, Tier 2 draft+flag, Tier 3 always defer).
5. **Defer rules** = regex list in `config/defer_rules.yaml`.
6. **Onboarding wizard** = React `/onboarding` route in dashboard (NOT the SKILL.md path); new step 7 "Apply Preferences" with new `ApplyPrefsDraft` slice.
7. **Pydantic schema** for `candidate_profile.yaml` in `src/config/schema.py`, validated on app boot.
8. **Cache** = `data/answer_cache.yaml`, RapidFuzz `token_set_ratio >= 85`, anonymized `$COMPANY` default + per-company override.
9. **Tier 2 default strategy** = draft + flag.
10. **Cost cap** = soft $0.05 per apply, log only.
11. **Vision fallback** = build in v1, screenshot → same OpenAI model (specific variant TBD this pass).
12. **Per-ATS prompt fragments** concatenated to a shared base.
13. **OpenAI-only provider** for v1 (multi-provider BYOK is issue #35).
14. **Submit gate REVERSAL (new):** Auto-submit if `all_required_filled AND (no_tier2_pending OR all_tier2_drafts_confidence >= 0.92) AND no_tier3_deferred`. LLM emits per-draft confidence in JSON output.
15. **Cost tracking** is broken end-to-end — design a provider-abstracted interface, OpenAI adapter today, applied across the whole pipeline (gate + tailor + review + finisher).
16. **Model names:** `gpt-5-mini` and `gpt-5.4` exist; `gpt-5.4-mini` does NOT. Earlier research docs that say `gpt-5.4-mini` are wrong.

## Sub-agent fan-out

All four sub-agents write to `./artifacts/` in this pass directory (the shared-artifact-dir rule from better-search-claude/SKILL.md §"Sub-Agent Research Directory Rule").

| Slot | Topic | Output file prefix |
|---|---|---|
| A | Pydantic AI + Playwright real-world browser-automation patterns | `pydantic-ai-*` |
| B | OpenAI vision input on gpt-5-mini / gpt-5.4 | `openai-vision-*` |
| C | Cost tracking — repo audit + provider-abstracted design | `cost-tracking-*` |
| D | Gap audit across locked decisions | `gap-audit-*` |

After all four return, this README will be updated with:
- Evidence table (source / type / date / relevance / confidence)
- Per-topic recommendation
- Updated open questions for issue #59

## How the synthesized output feeds back to planning

Each sub-agent writes a `recommendation.md` that this parent agent (Opus) reads and turns into:
- Concrete code-level decisions for Phase C / D / E / F.
- An updated issue #59 comment listing the reversed/expanded decisions (binary gate → confidence gate, cost-tracking phase, doc phase).
- Pydantic AI version pin for `pyproject.toml`.
- Vision-model decision (probably `gpt-5.4` if `gpt-5-mini` doesn't take images; TBD by Agent B).
- Cost-tracking interface signature.
