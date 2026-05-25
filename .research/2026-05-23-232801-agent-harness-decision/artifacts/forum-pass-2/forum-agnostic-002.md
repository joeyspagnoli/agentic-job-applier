# Forum Signal: "Agent Framework with Playwright MCP"

Search: "agent framework with playwright mcp" + related

## Key Findings

### Playwright MCP Overview
Source: https://github.com/microsoft/playwright-mcp

First released officially as `@playwright/mcp` by Microsoft in early 2025. By mid-2025 it had become "one of the most widely adopted MCP servers for Claude in production use."

Key design: exposes browser tools over MCP using structured accessibility snapshots (not screenshots) + deterministic element refs. This is closer to Scenario D (natural-language-aware DOM actions) than raw Playwright, but via standard MCP protocol.

### Playwright Tool Proliferation Problem
Source: https://www.speakeasy.com/blog/playwright-tool-proliferation

Playwright MCP exposes 30+ tools. This is a known issue:
> "When you expose everything from Playwright MCP, the tool list overwhelms the LLM's decision-making."

Recommendation: Use tool filtering (available in ADK, OpenAI SDK, Strands, LangChain adapter 0.2.0+) to expose only the subset of tools needed.

### Playwright MCP Architecture 2026
Source: https://testquality.com/playwright-test-agents-mcp-architecture-2026/

Confirms all 6 harnesses are compatible with Playwright MCP — the MCP standard means any harness with an MCP client can consume it.

### Stagehand MCP
Source: https://www.morphllm.com/stagehand-mcp

Stagehand now exposes its natural-language DOM actions as MCP tools. This confirms Scenario D (natural-language browser primitives) is achievable through the same MCP client interface as Scenario B — no harness-specific code needed.

## Implication
The MCP standard commoditizes browser layer swapping. Any harness with first-class MCP client support can swap Playwright MCP → Stagehand MCP → browser-use MCP with zero agent code changes. The lock-in is only in harnesses that lack MCP client support.
