# Reference: `pamelafox/personal-linkedin-agent` — Playwright + Pydantic AI

**File:** `invitations_manager.py`
**Repo:** https://github.com/pamelafox/personal-linkedin-agent (Pamela Fox @ Microsoft)
**Fetched:** 2026-05-25 via `gh api`

## What it does

Logs into LinkedIn (Playwright auth state pinned to a file), iterates through invitation cards,
asks a Pydantic AI agent to ACCEPT / IGNORE / UNDECIDED, then clicks Accept / Ignore via Playwright.

## Key architectural choice — NO tools

This agent has **zero `@agent.tool` registrations**. The Playwright code lives OUTSIDE the agent;
the agent is a pure classifier:

```python
class InvitationDecision(BaseModel):
    action: InvitationAction
    reason: str

agent = Agent(
    model,
    system_prompt="""Decide whether to accept or ignore LinkedIn invitations...""",
    output_type=NativeOutput(InvitationDecision),
)
```

The host code calls `agent.run(decision_message)`, reads `result.output`, then executes Playwright
operations directly. This is the **"LLM as field classifier, host as actuator"** pattern.

## Per-call usage capture (the pattern we need)

```python
agent_result = await agent.run(input_message)
decision = agent_result.output
logger.info(
    "%d input tokens, %d output tokens used for decision",
    agent_result.usage().input_tokens,
    agent_result.usage().output_tokens,
)
```

Each `agent.run()` returns a result with `.usage()`. The host code accumulates usage across many
runs by adding the per-run totals.

## Comparison with finisher

Finisher CAN'T use this no-tools shape because:

- LinkedIn has one screen → one decision per call (no multi-turn).
- Form-filling needs multi-turn (snapshot → click → fill → snapshot again).

But the **per-call usage capture pattern** transfers directly: every `agent.run()` (or every
`ModelRequestNode` in `agent.iter()`) returns usage. The "$0.05 soft cap" check looks like:

```python
async with agent.iter(prompt, deps=deps) as run:
    async for node in run:
        if isinstance(node, ModelRequestNode):
            # Just before this request, check the budget
            current_usage = run.usage
            cost_so_far = compute_cost(current_usage)
            if cost_so_far > 0.05:
                log.warning("finisher.cost_cap_hit", cost=cost_so_far)
                # log only — don't abort; the LLM finishes the turn
```

## Output mode choice — they use `NativeOutput`

```python
output_type=NativeOutput(InvitationDecision)
```

For OpenAI (Pamela uses gpt-4o via GitHub Models endpoint), `NativeOutput` invokes OpenAI's
Structured Outputs feature. Cheaper than tool-call mode, ~3x more reliable than prompted.

**Recommendation for finisher:** also use `NativeOutput(FinisherResult)` on the final
`complete_apply()` path, since we're OpenAI-only in v1 (locked decision #13).

## What we WON'T copy

- The auth-state file pattern (we use CDP — Chrome is already logged in).
- The "agent loops, host drives Playwright" shape (we want the model driving via tools).
- `Agent.run()` one-shot — we need `agent.iter()` for budget checks.
