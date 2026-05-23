# OSS Launch Prep — Resume Doc

If this conversation gets compacted mid-work, read this file first.

## Status (as of latest checkpoint)

### Done & committed (4 commits ahead of `origin/main`)

1. `a6f0f3e feat: narrow onboarding to OpenAI BYOK only` — Codex/Anthropic/Gemini/OpenRouter stripped from UI + backend; `src/providers/factory.py` preserved.
2. `0fa379c feat: surface missing OPENAI_API_KEY across workers and dashboard` — tailor/review workers idle on missing key (mirrors gate); `GET /api/system/health` + `MissingKeyBanner` mounted in `App.tsx`.
3. `c3c7925 feat: hard-disable auto-submit and document the safety policy` — `dry_run = True` hardcoded; README alpha banner + Status & Safety section; SECURITY.md auto-submit policy; `.env.example` trimmed.
4. `41e2b0e fix: treat .env.example placeholders as unconfigured key` — banner now respects `ENV_KEY_PLACEHOLDER_VALUES` so `your_openai_api_key_here` triggers the warning.

### In flight (background sub-agent)

- **mypy fix agent** (`agentId: ade38d2d01944e2c4`) — fixing 82 CI mypy errors across 17 files (fetchers, scripts, tests). 17 files currently in working tree as `M`. Agent still running as of last check. Will need a 5th commit when it finishes.

### Verified manually

- Banner: `curl /api/system/health` returns `{"ok":true,"openai_key_configured":false}` even with placeholder `your_openai_api_key_here` in `.env`.
- Dashboard: rebuilt + opened in playwright. Banner renders at top with link to `/settings`.
- Onboarding: wizard renders all 6 steps; Step 5 button labeled "AI Provider".

### Known blocker for full E2E

- Agent B (Codex strip) overwrote `.env` line 14 with the placeholder during manual curl verification. The user needs to paste their real `OPENAI_API_KEY` back before LLM-side E2E (gate/tailor/review) can run.

## GitHub state

- Issue #35 opened: "Wider BYOK provider support — extend tailor + review workers beyond OpenAI" (referenced from README, SECURITY.md, onboarding step 5 description).
- Branch `main` ahead by 4 commits, not yet pushed (intentionally — waiting for mypy fix to land before push so CI greens).
- CI workflow: `Frontend (Node 22)` passes; `Backend (Python 3.11)` fails on `uv run mypy` with 82 type errors. The mypy fix agent is addressing this.

## Civil engineer persona for E2E (per user request)

When `OPENAI_API_KEY` is restored, run E2E with:

- **Name**: Marcus Chen
- **Email**: marcus.chen.test@example.com
- **School**: Georgia Tech
- **Major**: BS Civil Engineering, sophomore
- **Skills**: AutoCAD, Civil 3D, Revit, MATLAB, basic structural analysis, Python
- **Search terms**: "civil engineering intern", "structural intern", "construction intern", "civil engineer student", "structural engineering intern"
- **Location**: Atlanta, GA

Steps:
1. Move `config/candidate_profile.yaml` aside.
2. Reset `data/jobs.db*`.
3. `docker compose --profile full up -d` (or local uvicorn + worker scripts).
4. Open dashboard, walk through onboarding for Marcus.
5. Wait for discovery + gate to flow jobs to QUALIFIED.
6. Confirm tailor + review pick them up; jobs reach PENDING_REVIEW.
7. Confirm dashboard timeline updates correctly.

## Locked decisions (from /grill-me)

1. **Q1 — A**: OpenAI BYOK only.
2. **Q2 — C**: Strip Codex auth UI + backend; keep provider factory.
3. **Q3 — A+A**: Workers mirror gate startup-check pattern; banner uses `/api/system/health`.
4. **Q4 — a+a**: Surgical hardcode `dry_run = True`; apply stays in `--profile full`.
5. **Q5 — a+b+d**: Top README banner + Status & Safety section + SECURITY.md update + alpha tagline.
6. **Q6 — i+i+plan**: Detailed BYOK issue (#35); keep `StepProvider.tsx` as a wizard step; sequential-by-phase, parallel-within-phase execution.

## Loop status

- Original `/loop` command: "you are to /improve-codebase-architecture using /coding-standards until you deem this repo in a better shape..." — currently in /loop dynamic mode.
- Next action: wait for mypy fix agent → commit fetcher fixes → push 5 commits → ask user to restore OPENAI_API_KEY for full LLM E2E.
- Fallback heartbeat scheduled.
