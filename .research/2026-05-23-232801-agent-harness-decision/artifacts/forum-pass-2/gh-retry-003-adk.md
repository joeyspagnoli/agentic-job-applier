# gh-retry-003-adk.md
# Command: gh search issues "retry" --repo google/adk-python --sort=comments --limit 5
# Date: 2026-05-24

## Results

| Title | URL | State | Comments |
|-------|-----|-------|----------|
| ADK Roadmap 2025 Q3 | https://github.com/google/adk-python/issues/2133 | closed | 47 |
| Tool Call has been called multiple times by ADK | https://github.com/google/adk-python/issues/3940 | open | 31 |
| Random "MALFORMED_FUNCTION_CALL" Error from Gemini Agent | https://github.com/google/adk-python/issues/1521 | closed | 29 |
| opentelemetry ValueError with ParallelAgent and LlmAgent | https://github.com/google/adk-python/issues/860 | closed | 27 |
| Tool use with function calling is unsupported | https://github.com/google/adk-python/issues/53 | closed | 24 |

## Key Findings

**Issue #3940 (Tool called multiple times, 31 comments, OPEN):** The model is calling the same tool repeatedly — which is the flip side of retry: the framework doesn't have built-in loop detection. The Reflect and Retry plugin handles retry UP but not runaway DOWN.

**Issue #1521 (MALFORMED_FUNCTION_CALL, 29 comments, closed):** Random Gemini model errors producing malformed tool calls. The Reflect and Retry plugin helps but the root cause is a Gemini model serialization bug for complex parameters. Not fully resolved.

**ADK Roadmap Q3 2025 (47 comments, closed):** Reflect and Retry plugin was shipped as part of the Q3 roadmap delivery in ADK 1.16 October 2025. Significant community investment.

## Assessment

ADK has more retry-related issues than other frameworks but also more invested solutions (the Reflect and Retry plugin is a first-class feature, not a community workaround).
