# Claude Agent SDK — Permissions (Full Documentation)

**Source:** https://code.claude.com/docs/en/agent-sdk/permissions  
**Fetched:** 2026-05-24

---

The SDK evaluates permissions in this order when Claude requests a tool:

1. **Hooks** — run first; can deny or pass through (allow from hook does NOT skip steps below)
2. **Deny rules** — `disallowed_tools` + settings.json; blocks in ALL modes including `bypassPermissions`
3. **Permission mode** — global mode applied (`bypassPermissions` approves everything here)
4. **Allow rules** — `allowed_tools` + settings.json; if matched, tool approved
5. **`canUseTool` callback** — interactive approval; skipped in `dontAsk` mode (tool denied)

---

## Allow and Deny Rules

| Option | Effect |
|--------|--------|
| `allowed_tools=["Read", "Grep"]` | Auto-approved; unlisted tools fall through to permission mode |
| `disallowed_tools=["Bash"]` | Bare name removes tool from Claude's context entirely |
| `disallowed_tools=["Bash(rm *)"]` | Scoped: tool stays visible; matching calls denied in ALL modes |

**Warning:** `allowed_tools` does NOT constrain `bypassPermissions`. Unlisted tools fall through to the mode, where `bypassPermissions` approves them. Use `disallowed_tools` if you want specific tools blocked under `bypassPermissions`.

---

## Permission Modes

| Mode | Description | Tool Behavior |
|------|-------------|---------------|
| `default` | Standard | No auto-approvals; unmatched → `canUseTool` callback |
| `dontAsk` | Deny instead of prompt | Anything not pre-approved by `allowed_tools`/rules is denied; `canUseTool` never called |
| `acceptEdits` | Auto-accept file edits | File edits + filesystem ops (`mkdir`, `rm`, `mv`, etc.) auto-approved |
| `bypassPermissions` | Bypass all | All tools run without prompts (use with caution) |
| `plan` | Planning mode | Read-only tools only; Claude analyzes without editing files |
| `auto` (TS only) | Model-classified | A model classifier approves/denies each tool call |

**Subagent inheritance:** When parent uses `bypassPermissions`, `acceptEdits`, or `auto`, all subagents inherit that mode and it cannot be overridden per subagent.

---

## Set Permission Mode at Query Time

```python
from claude_agent_sdk import query, ClaudeAgentOptions

async for message in query(
    prompt="Help me refactor this code",
    options=ClaudeAgentOptions(
        permission_mode="acceptEdits",
    ),
):
    if hasattr(message, "result"):
        print(message.result)
```

---

## Set Permission Mode Dynamically

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

async with ClaudeSDKClient(
    options=ClaudeAgentOptions(permission_mode="default")
) as client:
    await client.query("Help me refactor this code")

    # Change mode mid-session
    await client.set_permission_mode("acceptEdits")

    async for message in client.receive_response():
        if hasattr(message, "result"):
            print(message.result)
```

---

## Mode Details

### `acceptEdits`

Auto-approves:
- File edits (Edit, Write tools)
- Filesystem commands: `mkdir`, `touch`, `rm`, `rmdir`, `mv`, `cp`, `sed`

Only applies to paths inside the working directory or `additionalDirectories`. Paths outside scope still prompt.

### `dontAsk`

Converts any permission prompt into a denial. Use with `allowed_tools` to create a fixed, explicit tool surface:

```python
options = ClaudeAgentOptions(
    allowed_tools=["mcp__browser__snapshot", "mcp__browser__click", "mcp__browser__type"],
    permission_mode="dontAsk"
)
```

### `bypassPermissions`

All tools run. Hooks still execute and can block. Scoped deny rules still apply. Use only in fully controlled environments.

### `plan`

Read-only. Claude may use `AskUserQuestion` to clarify requirements. Does not edit source files.

---

## Locked-Down Agent Pattern (Your Use Case)

```python
options = ClaudeAgentOptions(
    allowed_tools=[
        "mcp__browser__snapshot",
        "mcp__browser__click",
        "mcp__browser__type",
        "mcp__browser__select",
        "mcp__browser__wait",
        "mcp__browser__goto",
    ],
    disallowed_tools=["Bash", "Write", "Edit", "Read"],  # Remove all built-ins
    permission_mode="dontAsk",  # Deny anything not in allowed_tools
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="^mcp__browser__click", hooks=[block_submit_hook])
        ]
    },
    max_turns=25,
)
```

This implements triple defense:
1. `disallowed_tools` removes dangerous built-ins from context
2. `dontAsk` + explicit `allowed_tools` hard-deny anything else
3. `PreToolUse` hook blocks submit buttons at the tool-call level

---

## Settings Files

Allow/deny rules can also be declared in `.claude/settings.json`. These load when `setting_sources` includes `"project"` (default for `query()`).

```python
options = ClaudeAgentOptions(
    setting_sources=["project"],  # Loads .claude/settings.json hooks too
)
```

---

## Related Resources

- Hooks: https://code.claude.com/docs/en/agent-sdk/hooks
- User input and approvals: https://code.claude.com/docs/en/agent-sdk/user-input
- Permission rule syntax: https://code.claude.com/docs/en/settings#permission-settings
