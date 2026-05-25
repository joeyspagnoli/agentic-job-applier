# Anthropic Computer Use Tool (Full Documentation)

**Source:** https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool  
**Fetched:** 2026-05-24

---

Claude can interact with computer environments through the computer use tool, which provides screenshot capabilities and mouse/keyboard control for autonomous desktop interaction.

**Status:** Beta — requires a beta header.

Beta headers:
- `"computer-use-2025-11-24"` — Claude Opus 4.7, Opus 4.6, Sonnet 4.6, Opus 4.5
- `"computer-use-2025-01-24"` — Claude Sonnet 4.5, Haiku 4.5, Opus 4.1, Sonnet 4 (deprecated), Opus 4 (deprecated)

---

## Overview

Computer use capabilities:
- **Screenshot capture:** See what's currently displayed on screen
- **Mouse control:** Click, drag, move cursor
- **Keyboard input:** Type text and use keyboard shortcuts
- **Desktop automation:** Interact with any application or interface

Not limited to browsers — works on any desktop application.

---

## Security Considerations

Unique risks vs standard API:

1. Use a dedicated virtual machine or container with minimal privileges
2. Avoid giving model access to sensitive data (account logins, credentials)
3. Limit internet access to allowlist of domains
4. Ask humans to confirm decisions with real-world consequences

Claude may follow commands found in page content even if they conflict with user instructions (prompt injection). Anthropic trains resistance to this and adds classifier defense for screenshots — when potential prompt injections are detected, model is steered to ask for user confirmation before proceeding.

---

## Quick Start (Python)

```python
import anthropic

client = anthropic.Anthropic()

response = client.beta.messages.create(
    model="claude-opus-4-7",
    max_tokens=1024,
    tools=[
        {
            "type": "computer_20251124",
            "name": "computer",
            "display_width_px": 1024,
            "display_height_px": 768,
            "display_number": 1,
        },
        {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"},
        {"type": "bash_20250124", "name": "bash"},
    ],
    messages=[{"role": "user", "content": "Save a picture of a cat to my desktop."}],
    betas=["computer-use-2025-11-24"],
)
print(response)
```

Reference implementation: https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo

---

## Why Computer Use Does NOT Fit This Use Case

### 1. Does Not Attach to Existing CDP Chrome

Computer use operates on whatever is displayed on screen via X11/display server. It does NOT:
- Connect to a running Chrome instance via Chrome DevTools Protocol (CDP)
- Inject JavaScript
- Read DOM directly
- Access browser extension state

If you already have a CDP-attached Chromium with the Simplify Copilot extension pre-loaded, computer use ignores that session entirely.

### 2. Token Cost is Prohibitive

Each action cycle:
1. Claude requests a screenshot
2. Screenshot is transmitted as image tokens (~1,400–2,000 tokens per 1024×768 screenshot)
3. Claude decides next action

For a 25-turn apply session:
- 25 screenshots × 1,500 tokens = **37,500 tokens** in image tokens alone
- Plus reasoning tokens per turn
- At $15/1M tokens (Opus 4.7): ~**$0.56 per apply** — 5-10x over budget

Your target: $0.01–$0.10 per apply. Computer use costs $0.40–$0.60 per apply minimum.

### 3. No Extension Support

Computer use sees pixel output only. It cannot:
- Interact with Simplify Copilot extension's pre-filled data
- Read extension-injected DOM modifications
- Benefit from Simplify's job field mapping

### 4. Slower Loop Latency

Screenshot → upload → model → action → screenshot cycle is slower than CDP direct command execution.

---

## When Computer Use IS the Right Choice

- No existing Chrome/browser automation setup
- Need to interact with non-web desktop apps
- Cost is not the primary constraint
- Don't need a specific Chrome profile or extension state
- Working in a controlled VM environment (Anthropic's reference demo)

---

## Verdict for This Project

Computer use is **not viable** for the CDP-based apply-worker:

| Criterion | Computer Use | CDP + Custom Tools |
|-----------|-------------|-------------------|
| Attaches to existing Chrome | No | Yes |
| Uses Simplify extension | No | Yes |
| Cost per apply | ~$0.50+ | ~$0.01-0.05 |
| Token cost type | Image (expensive) | Text (cheap) |
| Simplify pre-fill leverage | No | Yes |
| Beta stability | Beta | Stable via MCP |

Use the bare `anthropic` SDK with computer use only if scrapping the entire CDP + Simplify setup.
