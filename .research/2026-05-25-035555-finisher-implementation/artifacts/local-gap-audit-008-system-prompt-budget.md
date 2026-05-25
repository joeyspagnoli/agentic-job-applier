# local-gap-audit-008 — system prompt size budget

**Trigger:** Gap area #9 — "With the 8-tool finisher + per-ATS prompt fragments + profile YAML serialized as context, how large does the system prompt get?"

## Components and rough sizes (token estimates, OpenAI tokenizer)

| Component | Estimated tokens | Notes |
|---|---|---|
| Base system prompt (tool semantics, defer policy, 3-tier model) | 1500-2500 | One-time per run; shared across ATSes |
| Per-ATS fragment (Greenhouse OR Ashby) | 600-1000 | Markdown bullet list + 3-4 example Q-and-A patterns |
| `candidate_profile.yaml` serialized as YAML | 800-1500 | Existing yaml is ~50 fields; new fields add ~30 lines |
| `defer_rules.yaml` (regex list, ~10 lines) | 100-150 | Effectively trivial |
| Job metadata (title, company, JD excerpt) | 500-2000 | JD can be long; we should truncate to ~1500 tokens |
| AX-tree snapshot (one frame, all unfilled fields) | 800-3000 | Variable; Cloudflare Greenhouse intern was ~30 fields → ~1500 tokens |
| Tool definitions (8 tools, JSON schema each ~50-100 tokens) | 400-800 | Pydantic AI auto-generated |
| Conversation history (snapshots + tool responses across N turns) | 2000-15000 | Grows linearly per turn; N≤25 turns |
| **TOTAL per turn (early turns)** | ~6000-12000 | Comfortable |
| **TOTAL by turn 20-25** | ~25000-40000 | Still within any GPT-5.x window |

## Context limits for the candidate models

Per WebSearch 2026-05-25:
- `gpt-5.4` — large context window (≥256K, exact varies by release).
- `gpt-5.5` — 1M token API context window, 128K max output.
- `gpt-5-mini` — same family; large context.

**Conclusion: even at 40k tokens per turn, we are nowhere near the context limit.** The full conversation fits in any current GPT-5.x context budget by 1-2 orders of magnitude.

## The real cost spike risk is not context limit — it's repeated AX-tree resends

The agent receives a fresh AX-tree snapshot after every click in the Pydantic AI multi-turn loop. **If the snapshot is 3000 tokens and the loop runs 25 turns, that's 75k input tokens worth of snapshots alone — most of it redundant.** OpenAI charges per input token even when prompt-caching kicks in (cached input is cheaper but still billed).

Estimated cost per apply at gpt-5.4 pricing (~$1.25 / 1M input, $10 / 1M output):
- Input: 80k tokens × $1.25/M = **$0.10**
- Output: 5k tokens × $10/M = **$0.05**
- **Total: ~$0.15 per apply**

The locked decision #10 cost cap is **$0.05 per apply, log only**. Our estimate is **3x that** on a typical Greenhouse Cloudflare form. Two consequences:

1. The "log only" policy is correct for v1 — actually capping at $0.05 would abort most runs mid-flow.
2. We should plan for **$0.10-$0.20 per apply** as the realistic baseline, and budget the cost-tracking work (sub-agent C) accordingly.

## Mitigation: AX-tree diffing between turns

The Pydantic AI agent typically gets the FULL snapshot each turn. **An optimization** for v2 (out of scope for #59): send only the delta from the previous snapshot. For a form where the agent fills one field per turn, the delta is ~50 tokens vs 3000 tokens full. 60x reduction. This would bring cost back under $0.05.

For v1, we accept the cost overrun.

## Locked decisions to sanity-check

- **Locked decision #10 ("Cost cap = soft $0.05 per apply, log only")** — the dollar figure is unrealistic for a 20-turn Pydantic AI loop with full-snapshot resends. Recommend changing to `$0.20 soft cap, log only` to align with the realistic measurement we'll observe. This isn't a hard limit so functionally it doesn't matter, but the per-apply cost dashboards will show every run as "over budget" if we keep $0.05.
- **Sub-agent C's cost-tracking design** should accommodate the 3x variance: cost will spike with form complexity. The interface needs `cost_per_apply` AND `cost_per_turn` so we can see if a specific form burned 40 turns at the high end.
