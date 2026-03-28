# Review Notes

## Critical Gaps
- **Auto-submit is not implemented**: apply worker currently records diagnostics and `NEEDS_REVIEW`; submit click path is still TODO in `src/agents/apply_worker/browser.py`.
- **No job-level APPLIED transition from apply worker**: `record_apply_success` updates only `apply_runs`; `job_postings.status` is not moved to `APPLIED` by current apply pipeline.
- **Operational visibility gap**: `scripts/status.py` does not summarize `tailor_runs`, `review_runs`, or `apply_runs`; operators must inspect SQLite directly.

## Deployment/Runtime Risks
- **Chrome profile dependency**: apply worker expects a real Chrome profile with Simplify extension installed/authenticated.
- **Headless display dependency**: Linux service requires Xvfb/`DISPLAY` and Chrome CDP health.
- **Env template drift**: `.env.example` does not currently include `APPLY_*` or `CHROME_CDP_URL` settings used by apply worker.
- **Service docs drift**: `deploy/README.md` and `QUICKSTART.md` do not yet document enabling `job-apply-chrome.service` and `job-apply-worker.service`.
- **Credential surface**: gate/tailor/review/apply all depend on stable external credentials/tooling (`OPENAI_API_KEY`, optional `APIFY_API_TOKEN`, pi command, TeX/poppler, Chrome).

## Behavior/Quality Risks
- **Simplify detection is heuristic**: DOM-marker detection may miss extension activation on some pages.
- **Confidence model is deterministic but limited**: current checks are generic and do not guarantee form completeness for all ATS variants.
- **Retry tuning sensitivity**: conservative backoff can delay retries; aggressive settings can thrash.

## Follow-ups
- Implement explicit submit path gated by confidence + hard-blocker checks.
- Add persisted handoff state for human-review-required applications (beyond raw artifacts).
- Add status CLI coverage for tailor/review/apply run tables.
- Extend deployment docs with apply-stage prerequisites and service enable steps.
- Add an operator command for requeue/reset across all run tables.
