# Fetch 007: HuggingFace — "Introduction to Agents" (Agents Course, Unit 1)

**URL:** https://huggingface.co/learn/agents-course/unit1/introduction
**Sub-pages fetched:**
- https://huggingface.co/learn/agents-course/unit1/what-are-agents
- https://huggingface.co/learn/agents-course/unit1/agent-steps-and-structure
**Fetched:** 2026-05-23
**Method:** WebFetch

---

## Formal definition

> "An Agent is a system that leverages an AI model to interact with its environment in order to achieve a user-defined objective. It combines reasoning, planning, and the execution of actions (often via external tools) to fulfill tasks."

Two-part anatomy:
1. **The Brain (AI Model)** — "handles reasoning and planning. It decides which Actions to take based on the situation."
2. **The Body (Capabilities and Tools)** — "everything the Agent is equipped to do." The scope of possible actions depends entirely on what tools have been provided.

## The agency spectrum

HuggingFace's smolagents conceptual guide defines a formal **spectrum of agency** (quoted table):

| Agency Level | Description | Pattern |
|---|---|---|
| ☆☆☆ | Agent output has no impact on program flow | `process_llm_output(llm_response)` |
| ★☆☆ | Agent output determines basic control flow | `if llm_decision(): path_a() else: path_b()` |
| ★★☆ | Agent output determines function execution | `run_function(llm_chosen_tool, llm_chosen_args)` |
| ★★★ | Agent output controls iteration and program continuation | `while llm_should_continue(): execute_next_step()` |
| ★★★ | One agentic workflow can start another agentic workflow | `if llm_trigger(): execute_agent()` |

This is the clearest formalization of "degrees of agency" in any source. A true agent is at minimum the third row (★★★) — the LLM controls the while loop continuation condition.

## The Think-Act-Observe cycle (verbatim)

> "Agents' work is a continuous cycle of: thinking (Thought) → acting (Act) and observing (Observe)."

Steps:
1. **Thought**: "The LLM part of the Agent decides what the next step should be."
2. **Action**: "The agent takes an action by calling the tools with the associated arguments."
3. **Observation**: "The model reflects on the response from the tool."

> "To use an analogy from programming, the agent uses a while loop: the loop continues until the objective of the agent has been fulfilled."

## The ReAct connection

> "This showcases the core concept behind the ReAct cycle: the interplay of Thought, Action, and Observation empowers AI agents to solve complex tasks iteratively."

HuggingFace explicitly links their Think-Act-Observe cycle to the ReAct paper (Yao et al., 2023), identifying them as the same pattern under different names.

## Alfred weather agent — annotated example

The tool call emitted by the agent:

```json
{
  "action": "get_weather",
  "action_input": {
    "location": "New York"
  }
}
```

The observation returned: `"Current weather in New York: partly cloudy, 15°C, 60% humidity."`

Then the agent generates a final response: `"Final answer: The current weather in New York is partly cloudy with a temperature of 15°C and 60% humidity."`

Key properties demonstrated:
- **Iterative**: if observation had indicated an error, Alfred re-enters the cycle.
- **Tool integration**: calls beyond static knowledge to retrieve real-time data.
- **Dynamic adaptation**: each cycle incorporates fresh information into reasoning.

## Tool as the extension of action space

> "LLMs are amazing models, but they can only generate text."

Tools are what break this limitation:
> "The developers of HuggingChat, ChatGPT and similar apps implemented additional functionality (called Tools), that the LLM can use to create images."

> "The design of the Tools is very important and has a great impact on the quality of your Agent. Some tasks will require very specific Tools to be crafted, while others may be solved with general-purpose tools like 'web_search'."

Note: "Actions are not the same as Tools. An Action, for instance, can involve the use of multiple Tools to complete."

## Framework used in course

HuggingFace uses `smolagents` as the teaching framework. The course shows building the same agent from scratch first (to understand the loop), then with `smolagents` (to understand the abstraction).

## Key takeaways for our research

1. HuggingFace's agency spectrum is the clearest definition of what makes something a "true agent" vs. a workflow: the LLM controls the while-loop continuation.
2. Think-Act-Observe = ReAct = the same pattern described consistently across all sources.
3. Tools are the only mechanism through which an LLM can affect the world. Tool design quality directly determines agent quality.
4. The course structure (raw loop first, then framework) mirrors Anthropic's recommendation: understand the primitive before reaching for abstraction.
