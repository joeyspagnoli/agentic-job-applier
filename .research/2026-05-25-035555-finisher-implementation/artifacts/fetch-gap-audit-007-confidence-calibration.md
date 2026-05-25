# fetch-gap-audit-007 — LLM self-reported confidence calibration

**Sources:**
- https://www.nyckel.com/blog/calibrating-gpt-classifications/ (WebFetched 2026-05-25)
- https://adam.holter.com/confidencebench-calibrating-llm-confidence-not-just-accuracy/
- https://arxiv.org/pdf/2404.04689 (Multicalibration for Confidence Scoring in LLMs)
- https://cleanlab.ai/blog/tlm-structured-outputs-benchmark/

**Trigger:** Locked decision #14 (the **REVERSED** submit gate): "Auto-submit if `all_required_filled AND (no_tier2_pending OR all_tier2_drafts_confidence >= 0.92) AND no_tier3_deferred`. LLM emits per-draft confidence in JSON output."

## The hard finding

**Self-reported GPT confidence is poorly calibrated and frequently inversely correlated with accuracy.** Direct quote from the Nyckel research:

> "the more confidence the LLM claims to be, the more likely it is to make a mistake!"

Their measured raw calibration error for self-assessed confidences: **~45%** (vs ~11% for a transfer-learning baseline — roughly 4x worse).

Additional finding: GPT-class models exhibit a **high density of >90% predictions** even on incorrect outputs. Selecting "all drafts with confidence ≥ 0.92" therefore does NOT mean "all drafts that are actually accurate ≥ 92% of the time." On the contrary, that bucket is heavily polluted with confident mistakes.

## Why the 0.92 threshold is risky

1. **Threshold misses the unreliable bucket.** The histogram of GPT-reported confidence has a heavy spike above 0.9 covering both correct and incorrect outputs. A 0.92 cutoff includes most of the spike, including its incorrect tail.

2. **Recent GPT-5 / gpt-5.x models do not expose token-level log-probabilities** (per cleanlab.ai's recent benchmark). That means we cannot fall back to log-prob aggregation as a sanity check on the model's stated number. We're locked into the self-report.

3. **Calibration-aware approaches require labeled data.** Post-hoc calibration techniques (Platt scaling, isotonic regression) reduced error from 45% → 8% in the Nyckel study — but those techniques need a labeled validation set per question category, which we don't have for "Why $COMPANY?" essays or skill-screen Yes/Nos.

## What the reversal actually buys us

The original binary gate (locked decision #14 before the reversal) said: "any Tier-2 draft → NEEDS_REVIEW." That's restrictive but **safe** — the human sees every essay before submission.

The reversed gate auto-submits Tier-2 drafts where the LLM self-reports ≥0.92 confidence. Given the calibration research, **a non-trivial fraction of those auto-submitted drafts will be high-confidence-but-wrong**. Two failure modes:

1. **Tier-2 skill screen Y/N answered confidently in the wrong direction.** E.g., "Are you fluent in Mandarin?" The agent infers "no" with 0.95 confidence (overstating its certainty). Auto-submits. The user is now on record as not speaking Mandarin to that company even if they actually do.
2. **"Why $COMPANY?" essay drafted with 0.95 confidence but factually wrong about the company.** E.g., misidentifies the user's reason or attributes a product to the wrong team. Auto-submitted essays are visible artifacts on the user's permanent application record.

## Mitigations if the reversal stays

1. **Use a higher threshold (≥0.97) and add a length+keyword sanity check** for essays (≥150 words, contains $COMPANY token literally, no "I don't know" / "I am unsure" phrases).
2. **Whitelist Tier-2 categories eligible for auto-submit.** Multi-select preferences and source-of-application are arguably safe to auto-submit on high confidence; essays and skill-screen Y/N likely aren't.
3. **Add a "sanity check" 2nd model call** that re-reads the draft and rates it independently. Two-shot agreement is a stronger signal than single self-report. Cost: 2x for essays, acceptable.
4. **Log every auto-submitted Tier-2 draft with its confidence + the human's later correction**, so we can build a calibration curve over time and switch to a post-hoc calibrated threshold in v2.

## Locked decision recommendation: keep the reversal but constrain it

The reversal is intellectually reasonable — it captures "high confidence on cheap categories" — but the **0.92 threshold is not defensible from current research**. Either:

- **Raise to 0.97 + category whitelist** (recommended), OR
- **Keep the binary gate from the original epic body and treat the reversal as deferred to v2**, after we've collected labeled calibration data from real applies.

Either way, **this is the single most important locked decision to re-examine before implementation starts.** It is a user-facing, legally-consequential default behavior.

## Prompt pattern for emitting confidence (if we keep it)

The structured-output pattern that the research community uses:

```python
class DraftField(BaseModel):
    field_id: str
    drafted_value: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str  # forces the model to justify before scoring

class FinisherDraft(BaseModel):
    drafts: list[DraftField]
```

**Key:** force the `reasoning` field to come BEFORE the `confidence` score in the schema order — Pydantic AI / OpenAI structured output preserve field order, and "chain-of-thought-before-confidence" is the most cited calibration-improving prompting trick (modest effect, but real). Plus a system-prompt rule: "Express LOW confidence (≤0.5) whenever you cannot verify the claim from the provided profile or JD. Express HIGH confidence (≥0.9) ONLY when the answer is a direct profile lookup."

This pattern doesn't fix calibration but it does shift the distribution leftward, which is the conservative direction.
