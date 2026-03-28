# Review Notes

## Review execution flags

- **Consistency check:** completed.
- **Completeness check:** completed.
- Consolidation was not requested for this run and remains reserved in AQA.

## Consistency findings

1. **Model-name documentation drift (minor).**
   - README says `OPENAI_API_KEY` is required for a `gpt-5-mini` gate (`README.md:50`), while the decider is pinned to `openai/gpt-5.1-codex-mini` (`src/agents/root_apply_decider/agent.py:19`).
   - Recommendation: align README wording with the current pinned model string.

2. **Deployment README stage coverage lag (minor).**
   - Deployment runtime model lists handoff queues up to `review_runs` (`deploy/README.md:5-10`), but apply-stage tables (`apply_runs`, `apply_handoffs`) are now part of schema/runtime (`src/database/schema.sql:150-225`, `src/database/db_manager.py:1745-1835`).
   - Recommendation: update deployment README runtime model bullets.

3. **Apply-stage behavior vs. aspirational submit language (moderate).**
   - Apply flow currently returns `NEEDS_REVIEW` even when `dry_run=False` (future auto-submit marked TODO) (`src/agents/apply_worker/browser.py:327-335`).
   - Recommendation: keep docs explicit that v1 is review-first unless auto-submit branch is implemented.

## Completeness findings

1. **Alerting asymmetry across systemd workers (moderate).**
   - Gate worker has `OnFailure=job-agent-alert@%n.service` (`deploy/job-agent-worker.service:5`), but tailor/review/apply units do not declare equivalent failure hooks (`deploy/job-tailor-worker.service:1-37`, `deploy/job-review-worker.service:1-37`, `deploy/job-apply-worker.service:1-38`).
   - Recommendation: add consistent OnFailure alerts or document intentional differences.

2. **Preflight-notification asymmetry in scripts (moderate).**
   - Tailor/review send ntfy on preflight failure (`scripts/process_qualified_jobs.py:627-632`, `scripts/process_reviewed_resumes.py:719-724`), while apply preflight logs and exits without notification (`scripts/process_apply_jobs.py:655-667`).
   - Recommendation: unify preflight failure signaling policy.

3. **Deployment templates require manual replacement (operational gap).**
   - Unit files contain placeholders (`YOUR_USERNAME`, `/path/to/agentic-job-applier`) (`deploy/job-discovery.service:8-13`, `deploy/job-agent-worker.service:9-13`, `deploy/job-tailor-worker.service:8-13`, `deploy/job-review-worker.service:8-13`, `deploy/job-apply-worker.service:9-16`).
   - Recommendation: provide a templating script or documented checklist to reduce setup errors.

## Language/support limitations and evidence gaps

- The implementation is Python-first; systemd/bash/sql/yaml behavior is covered as config/runtime artifacts, not as fully executable typed modules (`main.py:7-26`, `deploy/start-chrome-cdp.sh:1-38`, `src/database/schema.sql:1-225`).
- This spec run focused on active code paths and did not treat non-runtime note/reference directories as first-class architecture surfaces.

## Recommended follow-up tasks

1. Update README/deploy docs for model string and apply-stage queue additions.
2. Normalize failure alerting across all worker services/scripts.
3. Decide and document whether auto-submit in apply worker is in-scope for next milestone.
4. Add a deployment bootstrap helper to render unit files from environment-aware templates.
