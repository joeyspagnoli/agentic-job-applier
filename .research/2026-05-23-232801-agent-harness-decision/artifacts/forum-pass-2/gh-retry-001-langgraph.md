# gh-retry-001-langgraph.md
# Command: gh search issues "tool retry" --repo langchain-ai/langgraph --sort=comments --limit 5
# Date: 2026-05-24

## Results

| Title | URL | State | Comments |
|-------|-----|-------|----------|
| ToolNode: surface model output metadata in tool error messages to enable self-correction | https://github.com/langchain-ai/langgraph/issues/7138 | open | 9 |

**Note:** Only 1 result matched "tool retry" directly. Broader retry search (see forum-retry-001) found:
- Issue #6486: Tool node error handling disabled by default after 1.0.1
- Issue #6027: Node Retry Policies not respected for Pydantic ValidationError

The low direct hit count for "tool retry" on langgraph is notable — the framework calls it "RetryPolicy" at the node level, not "tool retry", suggesting the abstraction is at the wrong granularity for users seeking per-tool retry semantics.
