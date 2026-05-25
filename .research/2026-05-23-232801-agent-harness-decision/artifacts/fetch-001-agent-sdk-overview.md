# Claude Agent SDK Overview (Full Documentation)

**Source:** https://code.claude.com/docs/en/agent-sdk/overview

Build AI agents that autonomously read files, run commands, search the web, edit code, and more. The Agent SDK gives you the same tools, agent loop, and context management that power Claude Code, programmable in Python and TypeScript.

Key capabilities:
- Built-in tools: Read, Write, Edit, Bash, Monitor, Glob, Grep, WebSearch, WebFetch, AskUserQuestion
- Hooks for PreToolUse, PostToolUse, Stop, SessionStart, SessionEnd, UserPromptSubmit
- Subagents with specialized instructions and tool restrictions
- MCP (Model Context Protocol) integration
- Permissions system with allowed/disallowed tool controls
- Sessions with resume, continue, and fork capabilities
- Full Claude Code feature support (skills, commands, memory)

## Loop Primitive

Python:
```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def main():
    async for message in query(
        prompt="Find and fix the bug in auth.py",
        options=ClaudeAgentOptions(allowed_tools=["Read", "Edit", "Bash"]),
    ):
        print(message)

asyncio.run(main())
```

TypeScript:
```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

for await (const message of query({
  prompt: "Find and fix the bug in auth.ts",
  options: { allowedTools: ["Read", "Edit", "Bash"] }
})) {
  console.log(message);
}
```

The Agent SDK includes built-in tools; Claude handles tool execution autonomously vs. the bare Client SDK where you implement the tool loop manually.

## Key Distinguishing Features

1. **Agent SDK vs Client SDK**: Agent SDK is a full autonomous agent loop with built-in tools. Client SDK requires you to implement tool execution yourself.
2. **Agent SDK vs Claude Code CLI**: Same capabilities, different interface. CLI for interactive dev, SDK for CI/CD, custom apps, production.
3. **Agent SDK vs Managed Agents**: Agent SDK runs in your process on your infrastructure. Managed Agents is hosted REST API (Anthropic-managed).
4. **Provider lock-in**: Claude-only (Anthropic models). Not pluggable to other providers.
5. **License**: Governed by Anthropic Commercial Terms of Service.

## Installation

Python: `pip install claude-agent-sdk`
TypeScript: `npm install @anthropic-ai/claude-agent-sdk`

API key via `ANTHROPIC_API_KEY` environment variable or cloud provider auth (Bedrock, Vertex, Azure, etc.).
