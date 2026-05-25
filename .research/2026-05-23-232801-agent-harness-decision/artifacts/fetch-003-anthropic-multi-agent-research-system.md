# Fetch 003: Anthropic — "How We Built Our Multi-Agent Research System"

**URL:** https://www.anthropic.com/engineering/built-multi-agent-research-system
**Published:** June 13, 2025

---

## Architecture: orchestrator-worker

The Anthropic Research feature uses a **lead agent** (Claude Opus 4) that spawns **subagents** (Claude Sonnet 4) in parallel.

Workflow:
1. Lead agent receives the query, develops a strategy, saves the plan to memory.
2. Lead agent spawns specialized subagents, each with a specific research subtask.
3. Each subagent independently does web searches, evaluates results, returns findings.
4. Lead agent synthesizes results; may spawn additional subagents if gaps remain.
5. A separate **CitationAgent** processes the assembled document to attach citations to specific source passages.
6. Final cited result returned to user.

Each subagent acts as "an intelligent filter by iteratively using search tools" before returning to the lead.

## Headline result

> "We found that a multi-agent system with Claude Opus 4 as the lead agent and Claude Sonnet 4 subagents outperformed single-agent Claude Opus 4 by 90.2% on our internal research eval."

Token usage explains 80% of performance variance. Three factors together explain 95%.

## Eight prompt-engineering principles for orchestrating subagents

1. **Think like your agent** — Simulate to find failure modes.
2. **Teach orchestration explicitly** — Subagent task descriptions must include objectives, output formats, boundaries.
3. **Scale effort to query complexity** — Embed explicit rules. Simple queries: 1 agent, 3–10 tool calls. Complex research: 10+ subagents.
4. **Tool design matters critically** — Match tools to intent; distinct purposes; clear descriptions.
5. **Let agents improve themselves** — Claude can diagnose its own failures and rewrite its prompts.
6. **Start wide, narrow down** — Broad searches first, then focused.
7. **Guide thinking with extended thinking** — Use it as a controllable scratchpad for planning.
8. **Parallel tool calling** — Execute 3+ tools simultaneously; spin up 3–5 subagents in parallel.

## Token economics — crucial for our cost-sensitive decision

> Multi-agent systems use "about 15× more tokens than chats."

These systems "excel at valuable tasks that involve heavy parallelization, information that exceeds single context windows, and interfacing with numerous complex tools."

**Implication:** if your task has low marginal value per run, multi-agent is likely the wrong shape. A single-agent loop with good tools is dramatically cheaper.

## Evaluation: LLM-as-judge

A single prompt scores agent outputs on:
- Factual accuracy
- Citation accuracy
- Completeness
- Source quality
- Tool efficiency

Plus human evaluation for edge cases and bias detection.

## Production reliability — the hardest part

Direct quote on what kills multi-agent systems in prod:

> "Agents maintain state across many tool calls. Without effective mitigations, minor system failures can be catastrophic for agents."

Required mitigations:
- **Durable execution** — survive process crashes; resume mid-loop.
- **Error handling** — retry with backoff; classify retryable vs terminal.
- **Resumption** — checkpoint state; pick up where you left off.

### Debugging

> "Agents make dynamic, non-deterministic decisions."

Solution: "full production tracing" that monitors "agent decision patterns and interaction structures."

### Deployment

> Use "rainbow deployments" — gradually shift traffic between versions to avoid disrupting running agents.

### Synchronous bottlenecks

Current lead agents execute subagents synchronously. This is a known bottleneck. Async would unlock more parallelism but adds coordination complexity and state-consistency hazards.

## Additional production patterns

- **End-state evaluation** — Score the final answer, not every step. Agents may take alternative valid paths.
- **Long-horizon conversation management** — Summarize and store externally BEFORE hitting context limits.
- **Filesystem output patterns** — Subagents write results to disk independently; prevents information loss in multi-stage pipelines.

## Implications for harness selection

For a single-user, single-task autonomous loop (like a browser-fill agent), the multi-agent overhead is almost certainly the wrong choice. The relevant lessons from this essay are the production-reliability ones:

- Need durable state / resumption.
- Need tracing.
- Need explicit error classification.
- Need filesystem-based result storage.
- Need to bound parallel subagents (token cost).

Multi-agent is for queries where the value per run is high and the surface area exceeds one context window.
