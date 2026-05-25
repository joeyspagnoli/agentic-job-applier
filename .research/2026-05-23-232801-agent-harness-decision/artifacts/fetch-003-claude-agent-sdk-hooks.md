# Claude Agent SDK — Hooks (Full Documentation)

**Source:** https://code.claude.com/docs/en/agent-sdk/hooks  
**Fetched:** 2026-05-24

---

Hooks are callback functions that run your code in response to agent events. They enable:
- Blocking dangerous operations before execution
- Logging and auditing every tool call
- Transforming inputs and outputs
- Requiring human approval for sensitive actions
- Tracking session lifecycle

---

## How Hooks Work

1. An event fires (tool about to run, tool completed, session start, stop, etc.)
2. SDK collects registered hooks for that event type
3. Matchers filter which hooks run (regex against tool name or event target)
4. Callback functions execute
5. Callback returns a decision: allow, block, modify input, or inject context

---

## Available Hooks

| Hook Event | Python | TypeScript | Trigger | Use Case |
|------------|--------|------------|---------|----------|
| `PreToolUse` | Yes | Yes | Tool call request | Block dangerous shell commands |
| `PostToolUse` | Yes | Yes | Tool execution result | Log all file changes |
| `PostToolUseFailure` | Yes | Yes | Tool execution failure | Handle tool errors |
| `PostToolBatch` | No | Yes | Full batch of tool calls resolves | Inject conventions once per batch |
| `UserPromptSubmit` | Yes | Yes | User prompt submission | Inject additional context |
| `Stop` | Yes | Yes | Agent execution stop | Save session state |
| `SubagentStart` | Yes | Yes | Subagent initialization | Track parallel task spawning |
| `SubagentStop` | Yes | Yes | Subagent completion | Aggregate parallel results |
| `PreCompact` | Yes | Yes | Conversation compaction request | Archive transcript |
| `PermissionRequest` | Yes | Yes | Permission dialog would display | Custom permission handling |
| `SessionStart` | **No** | Yes | Session initialization | Initialize logging/telemetry |
| `SessionEnd` | **No** | Yes | Session termination | Clean up resources |
| `Notification` | Yes | Yes | Agent status messages | Send to Slack/PagerDuty |
| `Setup` | No | Yes | Session setup/maintenance | Initialization tasks |
| `TeammateIdle` | No | Yes | Teammate becomes idle | Reassign work |
| `TaskCompleted` | No | Yes | Background task completes | Aggregate results |
| `ConfigChange` | No | Yes | Configuration file changes | Reload settings |
| `WorktreeCreate` | No | Yes | Git worktree created | Track workspaces |
| `WorktreeRemove` | No | Yes | Git worktree removed | Clean up workspace |

**Note:** `SessionStart` and `SessionEnd` are **not available in Python SDK callbacks** — only as shell command hooks in settings files.

---

## Configure Hooks (Python)

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [HookMatcher(matcher="Write|Edit", hooks=[my_callback])]
    }
)
```

---

## Callback Inputs

Every hook callback receives three arguments:
1. **Input data:** typed object with event details
   - All share: `session_id`, `cwd`, `hook_event_name`
   - `PreToolUse` / `PostToolUse` also have: `tool_name`, `tool_input`, `agent_id`, `agent_type`
2. **Tool use ID:** correlates `PreToolUse` ↔ `PostToolUse` for same call
3. **Context:** in TypeScript, contains `signal` (AbortSignal); in Python, reserved for future use

---

## Callback Outputs

Return object with two categories:
- **Top-level fields:**
  - `systemMessage`: message shown to the user
  - `continue` (`continue_` in Python): whether agent keeps running
- **`hookSpecificOutput`** (controls the current operation):
  - For `PreToolUse`: `permissionDecision` (`"allow"`, `"deny"`, `"ask"`, `"defer"`), `permissionDecisionReason`, `updatedInput`
  - For `PostToolUse`: `additionalContext`, `updatedToolOutput`

Return `{}` to allow without changes.

**Priority:** deny > defer > ask > allow (most restrictive wins when multiple hooks fire)

---

## Block Submit Button (Your Use Case)

```python
async def block_submit(input_data, tool_use_id, context):
    if input_data["tool_name"] == "mcp__browser__click":
        selector = input_data["tool_input"].get("selector", "").lower()
        text = input_data["tool_input"].get("text", "").lower()
        aria_label = input_data["tool_input"].get("aria_label", "").lower()
        
        if any("submit" in s for s in [selector, text, aria_label]):
            return {
                "hookSpecificOutput": {
                    "hookEventName": input_data["hook_event_name"],
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Submit buttons are forbidden by policy",
                }
            }
    return {}

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="^mcp__browser__", hooks=[block_submit])
        ]
    }
)
```

---

## Protect .env Files Example

```python
async def protect_env_files(input_data, tool_use_id, context):
    file_path = input_data["tool_input"].get("file_path", "")
    file_name = file_path.split("/")[-1]

    if file_name == ".env":
        return {
            "hookSpecificOutput": {
                "hookEventName": input_data["hook_event_name"],
                "permissionDecision": "deny",
                "permissionDecisionReason": "Cannot modify .env files",
            }
        }
    return {}

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [HookMatcher(matcher="Write|Edit", hooks=[protect_env_files])]
    }
)
```

---

## Modify Tool Input

```python
async def redirect_to_sandbox(input_data, tool_use_id, context):
    if input_data["tool_name"] == "Write":
        original_path = input_data["tool_input"].get("file_path", "")
        return {
            "hookSpecificOutput": {
                "hookEventName": input_data["hook_event_name"],
                "permissionDecision": "allow",
                "updatedInput": {
                    **input_data["tool_input"],
                    "file_path": f"/sandbox{original_path}",
                },
            }
        }
    return {}
```

Note: when using `updatedInput`, must also include `permissionDecision: "allow"` or `"ask"`.

---

## Multiple Hooks (Run in Parallel)

```python
options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(hooks=[authorization_check]),
            HookMatcher(hooks=[input_validator]),
            HookMatcher(hooks=[audit_logger]),
        ]
    }
)
```

All matching hooks run in parallel. Most restrictive result wins.

---

## Regex Matchers

```python
options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="Write|Edit|Delete", hooks=[file_security_hook]),
            HookMatcher(matcher="^mcp__", hooks=[mcp_audit_hook]),  # All MCP tools
            HookMatcher(hooks=[global_logger]),  # No matcher = all tools
        ]
    }
)
```

Matchers match **tool names only** (not file paths or other args). Filter by path inside callback.

---

## Async Side-Effect Hooks (Fire and Forget)

```python
async def async_hook(input_data, tool_use_id, context):
    asyncio.create_task(send_to_logging_service(input_data))
    return {"async_": True, "asyncTimeout": 30000}
```

Async outputs cannot block, modify, or inject context — use only for side effects.

---

## Matcher Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `matcher` | `string` | `undefined` | Regex pattern against tool name; omit to match all |
| `hooks` | `HookCallback[]` | required | Array of callback functions |
| `timeout` | `number` | `60` | Timeout in seconds |

---

## Troubleshooting

- **Hook not firing:** check event name is case-sensitive (`PreToolUse` not `pretooluse`); hooks may not fire when agent hits `max_turns` limit
- **Matcher not filtering:** matchers match tool names only — filter by file path inside callback
- **Modified input not applied:** `updatedInput` must be inside `hookSpecificOutput`, must include `permissionDecision`, must include `hookEventName`
- **SessionStart/End not in Python:** use shell command hooks in settings files, or use first `receive_response()` message as trigger

---

## Related Resources

- Permissions: https://code.claude.com/docs/en/agent-sdk/permissions
- Custom tools: https://code.claude.com/docs/en/agent-sdk/custom-tools
- TypeScript SDK reference: https://code.claude.com/docs/en/agent-sdk/typescript
- Python SDK reference: https://code.claude.com/docs/en/agent-sdk/python
