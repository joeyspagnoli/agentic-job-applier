## Summary

<!-- One or two sentences describing what this PR does and why. -->

## Type of change

<!-- Check all that apply. -->

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that changes existing behavior)
- [ ] Refactor (no behavior change)
- [ ] Documentation only
- [ ] Tests / CI / tooling
- [ ] Chore / maintenance

## How to test

<!--
Steps a reviewer can follow locally to verify the change. Include exact commands
where possible (e.g. `uv run pytest tests/test_foo.py -q`,
`npm --prefix dashboard run test`).
-->

1.
2.
3.

## Risks / impact

<!--
Anything reviewers should pay extra attention to: data migrations, config
changes, performance, security, backwards compatibility, secrets, third-party
APIs, etc. Write "none" if there are no notable risks.
-->

## Checklist

- [ ] Tests pass locally (`uv run pytest -q`)
- [ ] Types pass locally (`uv run mypy`)
- [ ] Frontend lint/typecheck/tests pass if dashboard changed (`npm --prefix dashboard run lint && npm --prefix dashboard run typecheck && npm --prefix dashboard test`)
- [ ] New/changed behavior is covered by tests
- [ ] Docs and config examples updated where relevant
- [ ] No secrets, API keys, or personal data included in commits
- [ ] Linked to a tracking issue (if applicable)

## Related issues

<!-- e.g. Closes #123, Refs #456 -->
