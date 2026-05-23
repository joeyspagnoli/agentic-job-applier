# Improve Codebase Architecture — Resume Doc

## Mission
User invoked `/loop` (dynamic mode) to:
1. Improve codebase architecture per /coding-standards
2. Fix the 7 failing tests (listed below)
3. Break up `api/main.py` (4340 lines) into FastAPI routers
4. Audit architecture overall — split or polish based on findings
5. Polish OSS presentation (badges, README, GitHub features)
6. Clear local DB and re-run E2E once before declaring done
7. User is going to sleep — they want it to look great when they unveil it as OSS in the morning
8. Keep it pragmatic — this is a pet project, don't over-engineer
9. **No co-author trailers in commits** (memory: feedback_no_coauthor.md)

## Constraints
- Branch: `main` (already merged from `idk` prior session). All work goes here.
- Pin deps with `==`, never `>=` (memory: feedback_dependency_pinning.md)
- Use `kindly-web-search-cli` for web research, not Explore-with-WebSearch (memory)
- App distributed via `dist/` to non-technical Windows users (memory: project_dist_onboarding.md) — actually `dist/` was deleted; canonical is now root docker-compose.yml
- Behavior must NOT regress — refactors are pure restructuring
- Remember: The /loop is dynamic — call ScheduleWakeup at end of each turn until done

## 7 Failing Tests (as of session start)
1. `tests/test_agent_worker_resilience.py::test_main_loop_continues_after_process_cycle_exception`
2. `tests/test_agent_worker_resilience.py::test_main_once_flag_overrides_loop_mode`
3. `tests/test_hygiene_hardening.py::test_apply_decider_tests_use_structural_prompt_assertions`
4. `tests/test_orchestrator_accounting_integrity.py::test_workday_start_crawl_failure_does_not_abort_other_companies`
5. `tests/test_resume_tailor_cli_integration.py::test_resume_tailor_tools_command_chain_supports_snapshot_and_recovery`
6. `tests/test_resume_tailor_tools_and_renderer.py::test_renderer_skips_disabled_listings`
7. `tests/test_resume_tailor_tools_and_renderer.py::test_locked_section_snapshot_rejects_education_mutation`

Run command: `uv run --no-dev pytest <path>::<name> -xvs 2>&1 | tail -80`

## Monolith Targets (lines)
- `api/main.py` — 4340  [PRIMARY TARGET]
- `src/database/db_manager.py` — 2841
- `main.py` — 1706
- `dashboard/src/pages/SettingsPage.tsx` — 3513
- `dashboard/src/pages/OnboardingPage.tsx` — 1999
- `dashboard/src/pages/OnboardingPage.test.ts` — 1837

## Current Task State
See `TaskList` in tools. Tasks #51-56 are tracked there.

## Sub-Agents Launched (live; check `Agent` SendMessage for results)
- Test diagnostician (returns root cause + fix strategy per failing test) — DONE
- API refactor planner (proposes router layout) — DONE
- DB + orchestrator refactor planner (split db_manager.py + main.py) — DONE
- Dashboard pages refactor planner (SettingsPage + OnboardingPage) — DONE
- OSS polish researcher (badges, README structure, CI workflows) — DONE
- a5587050091611111 — Test fixes (DONE, committed a99958d)
- a70d7e045a2868f91 — API Phase 1 config+errors+schemas (DONE, committed 1bee715)
- ac8002a219c16a5ea — API Phase 2 services (DONE, committed 60aa9ac)
- a693858a72b055ae9 — Dashboard SettingsPage refactor (DONE, committed 6575f5e)
- a9edea51436563acb — Dashboard OnboardingPage refactor (DONE, committed 3de611a)
- a9a3d7b1daa89a5f6 — DB manager refactor (DONE, committed 4f3ddc4)
- ad2a405fd620c0c35 — API Phase 3 routers (RUNNING — api/main.py 2724→718 so far)
- a88c40d28457aa630 — Orchestrator main.py refactor (DONE, committed f3e972b)

## Commits Landed
- a99958d test: fix 7 pre-existing pytest failures
- c8036de chore: add .editorconfig and dependabot config
- 1bee715 refactor(api): extract config, errors, schemas from api/main.py
- 4f3ddc4 refactor(database): split db_manager.py into per-concern mixins
- 60aa9ac refactor(api): extract service helpers from api/main.py
- 3de611a refactor(dashboard): split OnboardingPage.tsx into per-step modules
- 6575f5e refactor(dashboard): split SettingsPage.tsx into per-tab modules
- f3e972b refactor(orchestrator): split main.py into discovery + fetcher modules

## Plan Skeleton (will fill in as agents return)

### Phase 1: Triage (now)
- [x] Audit codebase, identify failing tests
- [ ] Get all 5 sub-agent reports back
- [ ] Pick implementation order based on risk/value

### Phase 2: Tests Green
- Fix the 7 failing tests (delegate to sub-agent once diagnoses are in)
- Verify with `uv run --no-dev pytest -q`

### Phase 3: API Refactor (biggest impact)
- Sub-agent extracts routers from `api/main.py` per the plan
- Verify imports + run tests + start server + curl smoke

### Phase 4: Other Monoliths (only if low risk)
- db_manager.py — likely defer if risky
- SettingsPage.tsx — extract per-tab
- OnboardingPage.tsx — extract per-step
- main.py orchestrator — extract helpers

### Phase 5: OSS Polish
- Apply badges to README
- Add CI workflows if missing
- Add `.editorconfig`, dependabot if missing
- Demo gif/screenshot placeholder

### Phase 6: Final E2E (multi-persona)
User explicitly asked for **5 persona E2E runs**:
1. Nurse
2. Finance bro
3. Law student
4. CS major
5. Environmental science

Plan: simulate each persona's onboarding via playwright-cli (or maybe API + DB seed for speed), then check dashboard for realistic-looking jobs. Clear DB between runs.

Use playwright-cli (via the project's .claude/skills/playwright-cli skill) to drive the wizard. Resume PDFs may need to be different per persona — could just text-fill the manual entry path instead of uploading a real resume.

### Phase 7: Post-mortem issue
User wants a GitHub issue documenting EVERYTHING done so they can read in the morning. Use:
```
gh issue create --title "post-mortem: codebase architecture overhaul YYYY-MM-DD" --body "..."
```
Match the style of issues #10, #11, #14, #17 (they use `feat:`/`research:`/etc. prefixes). Use `chore:` or `docs:` for this one.

Past issues to reference for tone: #10 (dependency pinning), #18 (resume tailor research)

## Key File Paths
- E2E PDF: `dashboard/Resume - Martin Yu.pdf` or in `temp-resume/`
- DB: `/Users/jspags/Projects/agentic-job-applier/data/jobs.db`
- Resume location for playwright (must be inside project root): `.playwright-cli/resume_jspagnoli.pdf`
- Dist folder: deleted last session; canonical is repo root

## Memory Pointers
- Use existing memory: `feedback_no_coauthor`, `feedback_dependency_pinning`, `feedback_use_kindly_search`, `project_dist_onboarding`

## Next Action After Compaction
1. `cat .research/improve-codebase/RESUME.md` (this file)
2. `TaskList` to see open tasks
3. Read this file's "Current Task State" + check sub-agent statuses (read most recent assistant messages for IDs, or just relaunch if needed)
4. Continue from Phase whose tasks are still open

## Branch / Commit Strategy
- Each phase = 1 commit (no co-author)
- Use imperative mood, terse subjects: `refactor: split api/main.py into routers` etc.
- Push to main only after all phases complete + tests pass + E2E verified
