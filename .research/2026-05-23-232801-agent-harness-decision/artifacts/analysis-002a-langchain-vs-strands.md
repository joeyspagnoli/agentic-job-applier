# Head-to-Head: LangGraph vs. AWS Strands (vs. What We Already Have)

**Date:** 2026-05-24  
**Question:** Does either LangGraph or Strands displace ADK or OpenAI Agents SDK for our 6-tool, single-loop apply-worker?

---

## Both Are "Yet Another General-Purpose Python Loop Runner"

LangGraph and Strands both solve the same problem: take an LLM, give it tools, run a loop. Neither offers a capability that the frameworks already in the repo (google-adk, openai Agents SDK) cannot match for this use case.

| Dimension | LangGraph | Strands | Google ADK | OpenAI Agents SDK |
|-----------|-----------|---------|-----------|-------------------|
| Loop primitive | create_react_agent (StateGraph) | Agent(model, tools) | LlmAgent + AgentRunner | Runner + Agent |
| "Never submit" guardrail | Tool wrapper or conditional edge (awkward) | event.cancel_tool in BeforeToolCallEvent (clean) | before_tool_call_callback (clean) | on_tool_start hook (clean) |
| Self-hosted | Yes | Yes (boto3 bundled) | Yes | Yes |
| No mandatory cloud | Yes | Yes (if not using Bedrock) | Yes | Yes |
| Already in repo | No | No | Yes (production) | Yes |
| Boilerplate for 6-tool loop | High (graph construction) | Low | Low | Low |
| Dep conflict risk | High (langchain version floors) | Medium (openai version, boto3) | None (already installed) | None (already installed) |
| Maturity | High (1.x, 40K stars) | Low-medium (2025 launch, 6.5K stars) | Medium (1.23.0) | High |
| License | MIT | Apache 2.0 | Apache 2.0 | MIT |

---

## Head-to-Head: LangGraph vs. Strands

**Winner: Strands** — for our specific use case only.

Strands has a cleaner guardrail primitive (event.cancel_tool cancels without executing), lower boilerplate, and equivalent provider portability. LangGraph's graph abstraction adds complexity that pays off only at multi-agent orchestration scale, which we are not at.

However, neither beats what is already installed:

---

## Does Either Displace ADK or OpenAI Agents SDK?

**No.** Neither LangGraph nor Strands offers a capability that justifies displacing the existing stack:

- **ADK is already in production** at src/agents/root_apply_decider/. Its before_tool_call_callback provides the same clean guardrail as Strands' BeforeToolCallEvent. The apply-worker loop built with ADK would look nearly identical to one built with Strands — same tool decorator pattern, same provider portability via litellm, same async support.

- **OpenAI Agents SDK** is already pinned and provides a simpler, purpose-built loop for OpenAI models.

- **Adding Strands** means a third harness, new boto3/botocore deps, potential openai version conflicts, and team onboarding to a 1-year-old framework — all for a marginally cleaner event name on one hook.

- **Adding LangGraph** is the most over-engineered path: 3x boilerplate, dep conflict risk, no hook-based guardrail, and the graph abstraction adds zero value to a 2-node loop.

---

## Recommendation

Extend ADK for the apply-worker. If ADK's loop model proves limiting (e.g., poor streaming, missing async patterns), migrate to OpenAI Agents SDK before considering either new harness. Strands is the better of the two newcomers but does not clear the bar for displacing an already-working system.
