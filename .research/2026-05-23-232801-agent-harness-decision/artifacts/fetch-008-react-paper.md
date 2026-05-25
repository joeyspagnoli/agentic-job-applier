# Fetch 008: ReAct — "Synergizing Reasoning and Acting in Language Models" (Yao et al., 2023)

**Paper URL:** https://react-lm.github.io/ (project page)
**ArXiv:** https://arxiv.org/abs/2210.03629
**Authors:** Shunyu Yao, Jeffrey Zhao, Dian Yu, Nan Du, Izhak Shafran, Karthik Narasimhan, Yuan Cao
**Conference:** ICLR 2023 (accepted; originally posted October 2022)
**Fetched:** 2026-05-23
**Method:** WebFetch (project page + arxiv abstract) + WebSearch for citation details

---

## Core thesis

> "We explore the use of LLMs to generate both reasoning traces and task-specific actions in an interleaved manner, allowing for greater synergy between the two."

The central claim: reasoning and acting are **complementary**, not alternatives. Prior approaches did one or the other:
- Chain-of-Thought (CoT): pure reasoning → hallucination, no grounding.
- Pure acting (tool use without reasoning traces): no synthesis, brittle.

ReAct combines both in one trace.

## The canonical formulation

ReAct defines an agent trace as interleaved triplets:

```
Thought: [Internal reasoning — what I know, what I need, what to do next]
Action:  [Tool call — name + arguments]
Observation: [Environment response — tool result]
Thought: [Updated reasoning in light of observation]
Action:  [Next tool call, or "finish" with final answer]
Observation: [Next result]
...
```

This is **not** just a prompting trick — it is the structural description of the agentic loop itself. The Thought step is the LLM's internal "reasoning trace"; the Action step is the tool call; the Observation step is the harness injecting the tool result back into context.

## Formal definition of the action space

ReAct extends the standard language model action space (next-token prediction) to include **task-specific discrete actions** (tool calls). The key innovation is that the model generates reasoning traces AND action calls in the same token stream, interleaved.

## Synergy mechanism

> "Reasoning traces help the model induce, track, and update action plans as well as handle exceptions."
> "Actions allow it to interface with external sources, such as knowledge bases or environments, to gather additional information."

The two capabilities are mutually reinforcing:
- Reasoning without acting → hallucination (model invents facts)
- Acting without reasoning → error propagation (model can't recover from mistakes)
- ReAct together → "overcomes issues of hallucination and error propagation"

## Empirical results

- HotpotQA (multi-hop QA): ReAct outperforms CoT-only by overcoming hallucination via Wikipedia API.
- FEVER (fact verification): Same pattern.
- ALFWorld (interactive decision-making): Outperforms imitation learning by **34% absolute success rate**.
- WebShop (e-commerce navigation): Outperforms RL baseline by **10% absolute success rate**.

Results achieved "while being prompted with only one or two in-context examples" — zero or few-shot.

## Why this paper is load-bearing for agent design

1. It is the **canonical source** for the Thought/Action/Observation pattern that every subsequent agent framework implements.
2. It proves empirically that the reasoning trace is **not decorative** — it is causally necessary for reliable multi-step task completion.
3. The "interleaved" framing directly explains the structure of the tool_use → tool_result message pairs in the Anthropic and OpenAI APIs: the API is implementing the Action → Observation turn of the ReAct loop.
4. The failure modes it identifies (hallucination from pure reasoning, error propagation from pure acting) are exactly the failure modes that production agent harnesses must guard against.

## Interpretability bonus

> "ReAct generates human-like task-solving trajectories that are more interpretable than baselines without reasoning traces."

The thought trace is observable. This is what makes agents debuggable — the reasoning is in the context, not opaque.

## Key takeaways for our research

1. ReAct = Think → Act → Observe. This is THE agentic loop. All other descriptions (Anthropic, OpenAI, HuggingFace) are restatements.
2. The Thought step is not optional fluff. It is the mechanism by which the agent avoids hallucination and recovers from errors.
3. A harness that strips out the reasoning trace (e.g., forces structured output only) loses the interpretability and error-recovery benefits of ReAct.
4. ReAct was demonstrated on browser/web tasks (WebShop) — making it directly applicable to a browser-fill agent.

---

**Sources:**
- Paper project page: https://react-lm.github.io/
- ArXiv: https://arxiv.org/abs/2210.03629
- Google Research blog: https://research.google/blog/react-synergizing-reasoning-and-acting-in-language-models/
- GitHub repo: https://github.com/ysymyth/ReAct
