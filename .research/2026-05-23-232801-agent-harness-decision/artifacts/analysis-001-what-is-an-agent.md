# Analysis 001: What Is an Agent — Definitive Reference

**Compiled from:** fetch-001 through fetch-008
**Purpose:** Ground the orchestrating Claude's understanding of agent vs. workflow vs. harness vs. framework before any implementation decisions are made.

---

## 1. Agent vs. Workflow vs. Chatbot vs. RAG

These four terms describe four distinct architectural categories. Conflating them is the single most common mistake in production LLM system design.

**Chatbot**: A single-turn or multi-turn LLM that answers questions and generates text. No tools. No loop. The LLM does not affect the world.

**RAG (Retrieval-Augmented Generation)**: A chatbot extended with a retrieval step. A query is embedded, relevant documents are fetched, injected into context before the LLM responds. Single-pass. No loop. The LLM does not decide to retrieve — a fixed program does. This is a workflow with one step.

**Workflow**: Anthropic's exact definition — "systems where LLMs and tools are orchestrated through predefined code paths" (fetch-001-anthropic-building-effective-agents). The control flow lives in your code. Even a complex DAG of LLM calls, retrievals, and tool invocations is a workflow if the sequence is determined by your code at design time.

**Agent**: Anthropic's exact definition — "systems where LLMs dynamically direct their own processes and tool usage, maintaining control over how they accomplish tasks" (fetch-001). The LLM decides which tool to call next. The LLM decides whether to loop again. The LLM decides when the task is done.

The sharpest single-sentence test comes from HuggingFace's agency spectrum (fetch-007-huggingface-agents-intro). A true agent sits at the level where the LLM controls iteration and program continuation:

```python
while llm_should_continue():
    execute_next_step()
```

Anything with a fixed loop count, a fixed step sequence, or code-determined branching is a workflow regardless of how many LLM calls it makes.

Anthropic's conclusion: "most production 'agentic' systems are actually workflows. Don't reach for a full autonomous agent if a chain or router solves the problem" (fetch-001).

---

## 2. The Agentic Loop

The agentic loop has been described identically across every primary source. It is the ReAct pattern (Yao et al., ICLR 2023 — fetch-008-react-paper), adopted verbatim by Anthropic, OpenAI, and HuggingFace.

```
state = initial_context(task, system_prompt, tools)

while True:
    response = llm.call(state)           # THINK: model reasons + decides

    if response.stop_reason == "end_turn":
        return response.text             # model declared done

    tool_call  = response.tool_use       # ACT: model chose a tool + args
    result     = execute(tool_call)      # harness runs the tool

    state.append(tool_call)              # OBSERVE: result injected into context
    state.append(tool_result(result))
    # loop — model sees updated state on next call
```

HuggingFace names these steps explicitly: "Agents' work is a continuous cycle of: thinking (Thought) → acting (Act) and observing (Observe) ... the agent uses a while loop: the loop continues until the objective of the agent has been fulfilled" (fetch-007).

Anthropic's seven-word formulation: "LLMs autonomously using tools in a loop" (fetch-002-anthropic-context-engineering). OpenAI: "Every orchestration approach needs the concept of a 'run', typically implemented as a loop that lets agents operate until an exit condition is reached. This concept of a while loop is central to the functioning of an agent" (fetch-005-openai-practical-guide-agents).

ReAct's critical insight: the Thought step is not decorative. Reasoning traces "help the model induce, track, and update action plans as well as handle exceptions," while without them "chain-of-thought reasoning suffers from hallucination and error propagation" (fetch-008). A harness that strips the model's reasoning (forcing structured-only output with no scratchpad) trades interpretability and reliability for parsability.

---

## 3. Tool Use Protocol

Tools are the only mechanism through which an LLM can affect the world. "LLMs are amazing models, but they can only generate text" (fetch-007). Everything else is text.

The wire protocol used by both Anthropic and OpenAI is functionally identical:

```
STEP 1 — Register tools (once, in the API call)
  {
    "name": "fill_field",
    "description": "Type a value into a named form field on the current page",
    "input_schema": {
      "type": "object",
      "properties": {
        "selector": {"type": "string", "description": "CSS selector or label text"},
        "value":    {"type": "string", "description": "Text to type into the field"}
      },
      "required": ["selector", "value"]
    }
  }

STEP 2 — Model emits tool_use block (stop_reason = "tool_use")
  {
    "type": "tool_use",
    "id":   "tu_abc123",
    "name": "fill_field",
    "input": {"selector": "#first_name", "value": "Jane"}
  }

STEP 3 — Harness executes the tool
  result = browser.fill("#first_name", "Jane")

STEP 4 — Harness injects tool_result into next API call
  {
    "role": "user",
    "content": [{
      "type": "tool_result",
      "tool_use_id": "tu_abc123",
      "content": "Field filled successfully. Next visible field: #last_name"
    }]
  }

STEP 5 — Model continues (back to STEP 2) or emits end_turn
```

Anthropic on tool quality: "Self-contained, robust to error, and extremely clear with respect to their intended use. If a human engineer can't definitively say which tool should be used in a given situation, an AI agent can't be expected to do better" (fetch-002). The JSON schema IS the tool's specification. Tool quality directly determines agent quality (fetch-007).

---

## 4. Anthropic's Five Workflow Patterns

These are the five pre-agent building blocks. Reach for an agent only when none fit. (fetch-001-anthropic-building-effective-agents)

1. **Prompt chaining** — Sequential LLM calls; each output feeds the next; programmatic gates validate intermediates. Use when task decomposes into ordered, known steps (e.g., extract → validate → format a resume section).

2. **Routing** — A classifier LLM dispatches input to one of N specialized prompts or models. Use when the input type determines which logic to apply (e.g., billing query vs. technical question vs. job application type).

3. **Parallelization** — Multiple LLM calls run simultaneously, either on independent subtasks (sectioning) or on the same task with results aggregated (voting). Use when subtasks are independent or consensus improves reliability.

4. **Orchestrator-workers** — A central LLM dynamically synthesizes subtasks at runtime and delegates to worker LLMs. Differs from routing in that subtasks are not pre-defined. Use when task decomposition cannot be predetermined.

5. **Evaluator-optimizer** — A generator LLM produces output; a critic LLM evaluates it; the generator revises. Loop until quality threshold is met. Use for tasks with clear LLM-checkable quality criteria (e.g., tailored cover letter quality, code correctness).

When none of these fit — when "steps cannot be predicted and multiple turns are needed, requiring some level of trust in [the LLM's] decision-making" — you have an agent use case (fetch-001).

---

## 5. The Three Layers: Model / SDK / Harness / Framework

```
┌─────────────────────────────────────────────────────────┐
│  FRAMEWORK                                              │
│  Harness + opinions about prompts, state, routing,      │
│  multi-agent topology, observability.                   │
│  Examples: LangChain, LlamaIndex, OpenAI Agents SDK,    │
│  smolagents, AutoGPT.                                   │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  HARNESS                                           │  │
│  │  The loop runner. Calls the SDK, inspects          │  │
│  │  stop_reason, extracts tool_use blocks, dispatches │  │
│  │  to tool implementations, formats tool_result      │  │
│  │  messages, appends to state, loops, enforces       │  │
│  │  exit conditions.                                  │  │
│  │                                                    │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │  SDK                                          │  │  │
│  │  │  HTTP client: anthropic, openai, boto3.        │  │  │
│  │  │  Handles auth, retries, streaming, message     │  │  │
│  │  │  serialization, token counting.               │  │  │
│  │  │  Does NOT run a loop.                          │  │  │
│  │  │  Does NOT execute tools.                       │  │  │
│  │  │  client.messages.create() = one HTTP call.     │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
              calls
               ↓
┌─────────────────────────────────────────────────────────┐
│  MODEL (claude-3-5-haiku-20241022, gpt-4o-mini, etc.)   │
│  Stateless token predictor. No memory. No tools.        │
│  No loop. Emits text in response to a context window.   │
└─────────────────────────────────────────────────────────┘
```

**Model**: Neural network weights behind an API endpoint. Stateless. The model never "runs" anything. It generates the next token given a context window.

**SDK**: An HTTP client library (`anthropic`, `openai`). Its job: serialize messages to JSON, POST to the endpoint, deserialize the response, surface errors, handle streaming. The SDK has no concept of tool execution or loop continuation.

**Harness**: The code that runs the loop. This is the agent runtime. A minimal harness is ~50 lines of Python. OpenAI calls this the "run" — the while loop that keeps invoking the model until an exit condition is reached (fetch-005). This is the most important layer to get right.

**Framework**: A harness with opinions baked in. Reduces boilerplate; adds abstraction, lock-in, and debugging opacity. A framework is only beneficial when its opinions align with your use case AND you understand the underlying loop well enough to have written it yourself.

---

## 6. Required Machinery Around the Loop for Production

A toy harness loops until the model says done. A production harness for any real deployment needs:

| Concern | What it means | Consequence of absence |
|---|---|---|
| **Tool registry** | Typed map of name → callable implementation | Wrong dispatch; KeyError at runtime |
| **Pre/post tool hooks** | Intercept every tool call before and after execution | Cannot log, validate, or abort risky actions |
| **State management** | Append-only, serializable message list | Loop restarts from scratch on any crash |
| **Abort / timeout** | Max-turns and wall-clock circuit breaker | Infinite loop; runaway cost |
| **Retries** | Classify retryable (5xx, network timeout) vs terminal errors | One transient failure kills the run |
| **Structured output** | JSON mode or tool-as-output for final answer | Free-text response breaks downstream parsing |
| **Observability** | Per-step trace: model input, output, tool call, result, latency, tokens | "Agents make dynamic, non-deterministic decisions" — impossible to debug without traces (fetch-003-anthropic-multi-agent-research-system) |
| **Cost tracking** | Input + output tokens per step, per run | No budget control; surprise bills |
| **Guardrails** | Input and output filters; pre-tool approval hooks | Model submits application with wrong data |
| **Context management** | Window monitoring; compaction at limit | "Context rot" degrades decisions at high turn counts (fetch-002); 400 error kills run at limit |

Anthropic on production reliability: "Agents maintain state across many tool calls. Without effective mitigations, minor system failures can be catastrophic for agents." Required: durable execution, error classification, resumption from checkpoints (fetch-003).

---

## 7. Why "Browser-Fill Agent" Is a Textbook Augmented-LLM-in-a-Loop

A browser-fill agent maps cleanly and completely onto the canonical agent architecture:

```
TOOLS   = browser primitives
            navigate(url)
            fill_field(selector, value)
            click(selector)
            screenshot() → base64 image or DOM summary
            get_page_state() → visible fields, current URL, errors

STATE   = page state accumulated across turns
            Each tool_result injects: current URL, filled fields,
            visible errors, confirmation messages.

LOOP    = ReAct
  Thought:     "I need to fill the email field. I can see #email in the DOM."
  Action:      fill_field("#email", "jane@example.com")
  Observation: "Field filled. Next required field: #phone_number"
  Thought:     "Phone number field now visible."
  Action:      fill_field("#phone_number", "555-123-4567")
  ...
  Thought:     "All required fields filled. Submit button is visible."
  Action:      click("#submit-btn")
  Observation: "Confirmation page loaded: 'Application received.'"
  Final answer: SUBMITTED

STOP CONDITIONS
  end_turn after confirmation  → success
  NEEDS_REVIEW tool call        → ambiguity/CAPTCHA/unexpected state
  max_turns exceeded            → abort, flag for human review
  page error after 3 retries   → terminal failure, surface to operator
```

This is precisely Anthropic's augmented LLM: "an LLM enhanced with augmentations such as retrieval, tools, and memory" (fetch-001). Tools are browser primitives. Memory is the page-state observations accumulated in context. The loop is ReAct. NEEDS_REVIEW is the guardrail.

ReAct was empirically validated on WebShop — an e-commerce browsing and form-filling benchmark — outperforming RL baselines by 10% absolute (fetch-008). Browser-fill is not a novel application of ReAct; it is one of ReAct's original validated domains.

---

## 8. Anthropic's "Don't Use a Framework" Guidance

Verbatim, from Anthropic's "Building Effective Agents" (fetch-001):

> "Rather than complex frameworks, successful implementations use simple, composable patterns. Start with direct API calls; frameworks can obscure underlying prompts and create unnecessary complexity."

Anthropic's stated reasons:

1. **Frameworks obscure the underlying prompts**. When something goes wrong, you need to see exactly what tokens the model received. Abstraction layers hide this.
2. **Unnecessary abstraction layers make debugging harder**. A 5-level call stack to send one API message makes the message content invisible during debugging.
3. **Opinionated patterns may not fit your use case**. A framework built for RAG pipelines (LlamaIndex) or general-purpose chaining (LangChain) will resist a browser-automation use case.

**When this guidance changes**: Use a framework when you (a) understand the primitive loop from the inside — you could write the harness yourself — and (b) the framework's opinions align with your use case, and (c) the boilerplate reduction outweighs the debugging cost of abstraction.

OpenAI states the same criterion directly: "Use OpenAI client libraries for straightforward model requests without orchestration needs. Use Agents SDK when your application owns orchestration, tool execution, approvals, and state management" (fetch-005). Reach for the SDK only when you actually need the features it provides and cannot implement them more directly.

For a browser-fill agent: a ~200-line custom harness wrapping the `anthropic` SDK directly is more debuggable, more auditable, and more aligned with the task than importing LangChain.

---

## 9. What "Cheap + Long-Running + Autonomous" Means for Harness Choice

A browser-fill agent running N applications per day has a distinct cost-and-reliability profile:

**Cheap model** → Use Claude Haiku or equivalent, not Opus. The task is execution-intensive, not reasoning-intensive: fill known fields from a known resume. A cheap, fast model with tight tool definitions outperforms an expensive model used carelessly. Model selection is a harness configuration (`model="claude-3-5-haiku-20241022"`), not a framework feature.

**Long-running** → Each application run is 10–60 turns. Context grows monotonically. "An agent running in a loop generates more and more data that could be relevant for the next turn of inference" (fetch-002). Without context management, later turns degrade ("context rot" — fetch-002) and eventually fail with a context-limit error. The harness must monitor token counts and compact or summarize before the limit.

**Autonomous** (no human per step) → Every tool call is potentially irreversible. The harness must: (a) enforce max_turns to prevent infinite loops; (b) classify errors as retryable vs terminal; (c) emit structured per-step traces so failures are diagnosable without re-running; (d) implement a NEEDS_REVIEW escape hatch so the agent halts and requests human judgment rather than guessing through ambiguity.

**Per-step cost circuit breaker** → The cost of a runaway agent (submitting wrong data, looping on a broken page) exceeds the cost of a stopped agent. Abort on: max_turns, wall-clock timeout, per-run cost threshold, or NEEDS_REVIEW.

**Observable cost** → "Multi-agent systems use about 15× more tokens than chats" (fetch-003). Even single-agent browser-fill at 30 turns × haiku pricing accumulates at scale. The harness must surface `input_tokens + output_tokens` per step and total per run.

**Mapping to concrete harness requirements:**

```
Cheap model        →  model= param in SDK call. No framework needed.

Tight token budget →  Harness tracks running token count from usage fields.
                      Triggers compaction (summarize history) at 80% of limit.

Per-step circuit   →  max_turns: int (e.g. 50).
breaker               wall_clock_timeout: seconds (e.g. 600).
                      NEEDS_REVIEW tool call = clean stop, return to operator.

Observable cost    →  Accumulate usage.input_tokens + usage.output_tokens.
                      Write per-run cost dict to structured log.

Guardrails         →  pre_tool_hook: validate every tool_use before execution.
                      post_tool_hook: log every tool_result.
                      final_state_eval: check confirmation page before marking SUBMITTED.
```

None of these requirements need a framework. They are all implementable in a custom harness under 300 lines wrapping the `anthropic` SDK — exactly what Anthropic recommends starting with.

---

## Summary

An agent is an augmented LLM (model + tools + memory) running a ReAct loop (Think → Act → Observe) where the LLM — not your code — decides which tool to call and when to stop. Everything else is a workflow, a chatbot, or a RAG pipeline.

The **model** generates tokens. The **SDK** is an HTTP client. The **harness** runs the loop. The **framework** is the harness plus opinions. For a browser-fill agent, write the harness; skip the framework until you understand the loop well enough to have written it yourself.

The nine production requirements (abort, tracing, cost tracking, context management, guardrails, retries, state, structured output, tool registry) are all harness-level concerns implementable in ~300 lines of Python backed by the `anthropic` SDK directly.

---

*Sources: fetch-001 through fetch-008*
