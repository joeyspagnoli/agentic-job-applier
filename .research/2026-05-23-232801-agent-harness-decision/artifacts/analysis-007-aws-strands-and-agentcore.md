# Analysis: AWS Strands Agents SDK (+ AgentCore) as Apply-Worker Harness

**Date:** 2026-05-24  
**Use Case:** Python apply-worker, 6 browser tools, 5-25 turns/apply, $0.01-0.10/apply, "never submit" guardrail, CDP-attached Chromium, self-hosted dist/ for non-technical Windows users.  
**Repo context:** Already has google-adk==1.23.0 in production, openai==2.26.0, anthropic==0.96.0, litellm==1.82.1.

---

## CRITICAL DISTINCTION: Strands SDK (OSS) vs. AgentCore (AWS-managed)

These are two entirely separate products that share AWS branding. Conflating them is the most common mistake in evaluating this stack.

| Dimension | Strands SDK | AgentCore |
|-----------|------------|-----------|
| What | Open-source Python/TS agent harness | AWS-managed cloud service |
| Hosting | Runs **in-process** on any machine | Runs in AWS data centers |
| AWS account | Not required (if using non-Bedrock provider) | **Required** |
| License | Apache 2.0 | Proprietary AWS service |
| Cost | Free (you pay for model API) | Per-session fees for browser, runtime, etc. |
| Self-hosted | Yes — fully | No — AWS-only |
| Browser | BYO (Playwright, CDP) | AgentCore Browser (cloud-hosted Chromium) |

**Summary:** Strands SDK is a viable self-hosted harness. AgentCore is a cloud execution platform that is incompatible with the dist/ distribution model. This analysis covers both but with different verdicts.

---

## 1. Strands SDK — Loop Primitive

The Strands agent loop is the simplest of all frameworks evaluated:

```python
from strands import Agent, tool

@tool
def navigate_to(url: str) -> str:
    """Navigate the browser to a URL and return the page title."""
    return cdp_navigate(url)

agent = Agent(
    model=model,
    tools=[navigate_to, read_page, fill_field, click, screenshot, submit_form]
)

result = agent("Fill out the application at https://jobs.example.com/apply/123")
print(result)  # final response text
print(result.metrics)  # token counts, latency
```

The loop is: invoke model -> if tool_use stop reason -> execute tool -> append result -> repeat until end_turn. Context accumulates across iterations. The agent sees the full history of every tool call and result on each model invocation.

**Seven termination conditions:** end_turn (normal), tool_use (continue), cancelled (agent.cancel()), max_tokens (fatal), stop_sequence, content_filtered, guardrail_intervention.

Context overflow is managed via conversation managers:
```python
from strands.agent.conversation_manager import SlidingWindowConversationManager
agent = Agent(
    tools=[...],
    conversation_manager=SlidingWindowConversationManager(window_size=40)
)
```

---

## 2. Strands @tool Decorator

The @tool decorator converts a plain Python function into a Strands tool by:
1. Using the function name as the tool name
2. Using the docstring as the tool description (supports Google/NumPy style for parameter docs)
3. Inferring the JSON schema from Python type annotations
4. Marking parameters with defaults as optional

```python
from strands import tool

@tool
def fill_field(selector: str, value: str, clear_first: bool = True) -> bool:
    """Fill a form field with a value.
    
    Args:
        selector: CSS selector or accessible label
        value: Text to type
        clear_first: Clear existing content before typing
    
    Returns:
        True if successful
    """
    return do_fill(selector, value, clear_first)
```

The decorator is optional — plain functions with type annotations and docstrings also work. Async tools are supported natively.

---

## 3. Strands Hooks / Lifecycle — The "Never Submit" Guardrail

This is where Strands genuinely shines for our use case. The hooks system is type-safe, composable, and has first-class support for **cancelling tool calls before execution**.

### Full Lifecycle (per invocation)

BeforeInvocationEvent -> MessageAddedEvent -> BeforeModelCallEvent -> AfterModelCallEvent -> BeforeToolCallEvent -> AfterToolCallEvent -> AfterInvocationEvent

### "Never Submit" Implementation

```python
from strands import Agent
from strands.hooks import BeforeToolCallEvent

BLOCKED_TOOLS = {"submit_form", "click_submit", "final_submit"}

def block_submit_guardrail(event: BeforeToolCallEvent) -> None:
    if event.tool_use["name"] in BLOCKED_TOOLS:
        event.cancel_tool = (
            "Policy: submit actions are blocked in dry-run mode. "
            "Report what you would have submitted instead."
        )

agent = Agent(tools=[navigate_to, read_page, fill_field, click, screenshot, submit_form])
agent.add_hook(block_submit_guardrail)
```

When cancel_tool is set, the tool is **never called**. The string value is returned to the model as the tool result. The model then reasons about the blocked action — it can explain what it would have submitted, which is exactly the desired dry-run behavior.

### Other Mutable Event Properties

| Event | Property | Effect |
|-------|----------|--------|
| BeforeToolCallEvent | cancel_tool | Cancel tool execution entirely |
| BeforeToolCallEvent | tool_use["input"] | Mutate arguments before execution |
| BeforeToolCallEvent | selected_tool | Replace the tool function |
| AfterToolCallEvent | result | Modify tool result seen by model |
| AfterToolCallEvent | retry | Retry the tool call |
| AfterInvocationEvent | resume | Trigger follow-up invocation |

### Plugin Pattern (for reusable guardrails)

```python
from strands.plugins import Plugin, hook
from strands.hooks import BeforeToolCallEvent

class NeverSubmitPlugin(Plugin):
    name = "never-submit"
    
    @hook
    def guard(self, event: BeforeToolCallEvent) -> None:
        if "submit" in event.tool_use["name"].lower():
            event.cancel_tool = "Submit blocked by policy."

agent = Agent(tools=[...], plugins=[NeverSubmitPlugin()])
```

This is **the cleanest "never submit" implementation of any framework evaluated**. It is a separate policy object, decoupled from tool definitions, applied at the hook layer.

---

## 4. Self-Hosted + OpenAI Provider — Viable?

**Yes, with a caveat about boto3.**

Strands supports OpenAI and many other providers without any AWS dependency at runtime:

```python
from strands.models.openai import OpenAIModel

model = OpenAIModel(
    client_args={"api_key": "sk-..."},
    model_id="gpt-4o",
)
agent = Agent(model=model, tools=[...])
```

Or via LiteLLM (compatible with our existing litellm==1.82.1):

```python
from strands.models.litellm import LiteLLMModel
model = LiteLLMModel(model_id="openai/gpt-4o")
```

**The caveat:** `boto3` and `botocore` are **core dependencies of strands-agents**, not optional extras. They are pulled in even if you never use Bedrock. This adds ~8 MB to the install and means AWS SDK code is bundled into the dist/ package. For non-technical Windows users this is invisible at runtime but is overhead in the bundle.

**OpenAI version conflict risk:** `strands-agents[openai]` uses the `openai` Python SDK. Our pinned `openai==2.26.0` may conflict with Strands' requirements. The LiteLLM provider route sidesteps this by routing through the already-pinned `litellm==1.82.1`.

**Net assessment:** Strands is self-hosted viable. The LiteLLM model provider is the lowest-friction integration path given existing pins.

---

## 5. AgentCore Browser Tool — NOT a Fit

AgentCore Browser is a **cloud-hosted, AWS-managed Chromium service**. It requires:
- An active AWS account with IAM permissions
- Bedrock AgentCore service enabled in a supported region
- Per-session fees (cloud container runtime)
- WebSocket API calls that traverse the internet for every browser interaction

**This is incompatible with the self-hosted dist/ model in every dimension:**

1. Non-technical Windows users cannot create AWS accounts or configure IAM
2. Per-session cost is unbounded and conflicts with the $0.01-0.10/apply budget
3. Each browser interaction adds internet round-trip latency vs. loopback CDP
4. User data (form content, credentials) would transit AWS infrastructure
5. The app already has locally attached CDP Chromium — AgentCore Browser adds nothing

AgentCore Browser is **firmly rejected** for this use case. The only future scenario where it would be relevant is a cloud-hosted SaaS version of the product where AWS manages the infrastructure on behalf of users.

---

## 6. License and Maturity

**License:** Apache 2.0 (confirmed, SDK repo)
**Origin:** Open-sourced by Amazon from "production systems inside Amazon" in 2025
**GitHub stars:** 6,500+ (growing rapidly post-launch)
**Language:** Python and TypeScript
**Status:** Active development; v0.1.x in 2025, accelerating toward 1.0

**Maturity concerns:**
- Newer than LangGraph, Google ADK, or OpenAI Agents SDK by 1-2 years
- API may still have breaking changes before 1.0
- Smaller community and fewer third-party tutorials/examples
- AWS backing provides sustainability assurance but also introduces corporate priorities that may not align with OSS users

---

## 7. Verdict

### Strands SDK: ACCEPTABLE (but not a clear win over ADK)

**Genuine strengths for our use case:**
- Cleanest hook-based "never submit" guardrail of any framework evaluated
- Minimal loop API (Agent + @tool) — close to ADK in simplicity
- Provider-agnostic (LiteLLM route avoids version conflicts)
- Apache 2.0, self-hosted, no mandatory cloud account
- Async support, streaming, conversation managers

**Weaknesses:**
- boto3/botocore in core deps even without Bedrock usage
- Newer/less mature than ADK (1-2 years younger)
- Would be a third harness alongside ADK and OpenAI Agents SDK
- The hooks system, while excellent, is not meaningfully better than ADK's before_tool_call_callback for a single-guardrail use case
- OpenAI provider version conflict risk

**The bar for adding a third harness is high.** Strands does the "never submit" guardrail slightly more elegantly than ADK (event.cancel_tool vs. callback function returning stop signal), but that marginal improvement does not justify adding a new dependency and training the team on a second framework.

### AgentCore: REJECTED

Cloud-managed, requires AWS account, per-session cost, data leaves user's machine. Incompatible with self-hosted dist/ distribution model.
