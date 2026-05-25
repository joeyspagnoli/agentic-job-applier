# gh-retry-004-pydantic.md
# Command: gh search issues "ModelRetry OR retry" --repo pydantic/pydantic-ai --sort=comments --limit 8
# Date: 2026-05-24

## Results

The search returned 0 direct results.

## Interpretation

Two possible explanations:
1. ModelRetry works so well that users don't file bugs about it — it "just works"
2. Users search for it under different terms

## Cross-referenced findings from broader search

**Issue #677 — "Add ability to customise model request retry behaviour"**
URL: https://github.com/pydantic/pydantic-ai/issues/677
Feature request to add HTTP-level retry configuration (for transient API failures, not tool ModelRetry). This is an enhancement request, not a bug report — meaning the core ModelRetry tool mechanic is not broken.

**Issue #3267 — "FallbackModel and Provider/Client SDK Retry Behavior might be conflicting"**
URL: https://github.com/pydantic/pydantic-ai/issues/3267
This is about HTTP-level provider retry conflicting with FallbackModel — again infrastructure layer, not tool retry layer. ModelRetry itself is not involved.

## Assessment

The absence of ModelRetry bugs is strong positive evidence. The most commented retry-adjacent issues are about HTTP transport retry (separate concern), not the tool retry mechanism. ModelRetry is the most "battle-tested" retry primitive in this comparison set.
