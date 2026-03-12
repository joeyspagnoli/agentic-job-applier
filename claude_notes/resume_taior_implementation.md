# Phase 2 (and Resume Tailor workflow): Implementation Plan

## Scope & goals

You asked for:
1) A planning/implementation doc for an **agentic workflow for the resume tailoring portion** (using Google ADK patterns).
2) A **question list** needed to implement it correctly.
3) A check that **Phase 2 infrastructure is set up properly**, including that a **Pydantic model is passed as input** to the agentic workflow.
4) Emulate architecture from `refs/test_architect/` and follow ADK best practices from `refs/agent_examples/google adk-docs main docs/`.

This plan is intentionally split:
- **Phase 2a (Plumbing / infra):** load jobs from DB, call agent workflow per job, persist agent outputs back to DB, ensure Pydantic input.
- **Phase 2b (Resume tailoring workflow):** define the multi-agent resume tailor pipeline, schemas, and persistence strategy (artifact + DB).

## Decisions (from your answers)
- Jobs to tailor: **`QUALIFIED` only**.
- Output: **PDF** compiled from your existing **LaTeX resume**, with guardrails:
  - workflow only edits **bullet points**
  - build must succeed (`pdflatex`/`latexmk`)
  - output must still be **exactly 1 page**
- Execution environment: unattended on Ubuntu Server (systemd timer); prefer **simple, non-interactive** orchestration.

## Recommendation: resume source + storage
- **Master resume source:** use a **local file path** to your LaTeX source on the homeserver (simplest, most reliable; no App UI needed).
- **Tailored resume storage:** write PDFs to filesystem (e.g., `data/tailored_resumes/{job_hash}.pdf`) and store the path + metadata in `job_postings.agent_result`.
  - This avoids needing a persistent ADK ArtifactService; state remains small/serializable.

## Current repo state (evidence)

### Phase 1 exists
- Orchestrator: `main.py` (Phase 1 job discovery pipeline)
- DB: `src/database/schema.sql`, `src/database/db_manager.py`
- Pydantic job model: `src/models/job_posting.py`

### ADK reference architecture exists in refs
- `refs/test_architect/root_agent.py` uses `SequentialAgent`.
- `refs/test_architect/code_analyst/agent.py` uses `LoopAgent` + `before_agent_callback` to initialize state keys.
- ADK docs on state/tool/callback best practices:
  - `refs/agent_examples/google adk-docs main docs/sessions/state.md`
  - `refs/agent_examples/google adk-docs main docs/callbacks/design-patterns-and-best-practices.md`
  - `refs/agent_examples/google adk-docs main docs/agents/multi-agents.md`
  - `refs/agent_examples/google adk-docs main docs/agents/workflow-agents/sequential-agents.md`
  - `refs/agent_examples/google adk-docs main docs/agents/llm-agents.md` (input_schema/output_schema/output_key)
  - `refs/agent_examples/google adk-docs main docs/artifacts/index.md`

### Phase 2 infra status (gaps)
We need to confirm/complete these Phase 2 items in the application code (not refs):
- A `src/agents/` package does **not** exist yet in `src/`.
- `main.py` currently runs discovery only; it does **not** have `run_agent_workflow()`.
- DB needs a mechanism to track agent outputs and avoid re-processing jobs.
  - The most DB-safe approach (given the existing CHECK constraint on status) is to **keep using status** (`NEW`, `QUALIFIED`, etc.) and store Phase-2/Resume-tailor progress in **agent columns** (`agent_processed_at`, `agent_result`) and/or per-stage fields inside `agent_result` JSON.

## Design principles (from ADK docs + refs)

1) **Serializable state only** (`sessions/state.md`):
   - Use `output_key` to store small outputs.
   - Keep larger payloads (resume files, PDFs) out of state; use artifacts or filesystem + store pointers.

2) **Workflow agent for deterministic order** (`workflow-agents/sequential-agents.md`):
   - Resume tailoring is naturally a sequential pipeline.

3) **Use output_schema + output_key** (`agents/llm-agents.md`):
   - Each step should return structured Pydantic output and store it in state.

4) **Initialize state via before_agent_callback** (as in `refs/test_architect/code_analyst/agent.py`):
   - Set default containers like `state.setdefault("resume_tailor", {...})`.

5) **Avoid tool limitations pitfalls** (`tools/limitations.md`):
   - Prefer plain Python function tools unless you *must* use built-in restricted tools.

## Proposed architecture (emulating refs/test_architect)

### Runner vs App recommendation
For your non-interactive homeserver use case, use **Runner directly** (not App) for now:
- The system runs on a timer and doesn’t need an interactive developer UX.
- Runner + `InMemorySessionService` is sufficient for *per-job* invocations.
- If we later need resumability/context caching, we can migrate to the `App` pattern described in `refs/agent_examples/google adk-docs main docs/apps/index.md`.

### New package layout (to add)

```
src/
  agents/
    __init__.py
    models.py                 # central model(s) / env load (like refs/test_architect/models.py)
    root_agent.py             # top-level sequential pipeline for resume-tailor
    resume_tailor/
      __init__.py
      schemas.py              # Pydantic schemas for outputs
      prompts.py              # prompt strings
      agent.py                # defines ResumeTailor pipeline agents
      tools.py                # optional: file/artifact helpers (plain functions)
```

### Phase 2 orchestration (in application main)

- Extend `main.py` with:
  - `run_job_discovery()` (keep as-is)
  - `run_agent_workflow()` (new):
    - chooses jobs to process (typically `QUALIFIED` for resume tailoring)
    - converts DB rows → `JobPosting` Pydantic model
    - builds a `ResumeTailorRequest` Pydantic model (job + resume inputs + prefs)
    - calls ADK runner with JSON string (`request.model_dump_json()`)
    - stores agent output JSON in DB via `update_job_agent_result()`

### Ensuring “Pydantic model is being passed as input”

Use ADK `input_schema`:
- Define `ResumeTailorRequest(BaseModel)` in `src/agents/resume_tailor/schemas.py`.
- Configure the main resume-tailor LLM agent with `input_schema=ResumeTailorRequest`.
- In `run_agent_workflow`, pass `user_input = request.model_dump_json()`.

Per ADK docs: `input_schema` requires the message content passed to agent be a JSON string conforming to the schema (`agents/llm-agents.md`, section “Structuring Data”).

## Resume tailoring workflow (agentic pipeline)

### LaTeX-specific tailoring strategy (bullet-only)
Guardrails and mechanics:
- Treat your resume LaTeX as a **template** and only allow edits within specific bullet-list regions.
- Implementation options:
  1) **Sentinel markers (Recommended)**: you add comment markers around editable regions, e.g.
     - `% AI_BULLETS_START:experience:company_x`
     - `% AI_BULLETS_END`
     The agent outputs replacements only for those regions.
  2) **AST/regex constrained editing**: parse `\item` blocks inside a known environment. Higher risk of breaking formatting.

Validation steps after editing:
- Compile via `latexmk -pdf`.
- Enforce 1-page constraint:
  - Parse PDF page count (e.g., `pdfinfo` or `qpdf --show-npages`) and require == 1.
- If compilation succeeds but page count != 1:
  - Iterate the bullet-tightening loop (bounded by a configured `max_iterations`).

The agent never edits preamble, margins, font sizes, spacing macros, or section headings.

### Pipeline stages (SequentialAgent)

1) **Requirements Extractor**
   - Input: `ResumeTailorRequest.job` (JobPosting)
   - Output schema: `JobRequirements`
   - Stores: `output_key="job_requirements"`

2) **Resume Parser (Inventory builder)**
   - Input: base resume (text or artifact reference)
   - Output schema: `ResumeInventory`
   - Stores: `output_key="resume_inventory"`

3) **Tailoring Planner**
   - Input: `job_requirements` + `resume_inventory` + constraints
   - Output schema: `TailoringPlan`
   - Stores: `output_key="tailoring_plan"`

4) **Resume Writer**
   - Input: `tailoring_plan` + base resume
   - Output schema: `TailoredResumeDraft`
   - Stores: `output_key="tailored_resume_draft"`

5) **QA / Consistency Checker (optional but recommended)**
   - Purpose: enforce “no hallucinated claims”
   - Output schema: `TailoringQaReport` with `pass: bool`, `issues[]`

6) **Renderer + Persist**
   - If output is text-only: store in DB + optionally write file.
   - If output is PDF/DOCX: store as ADK artifact or filesystem.
   - Output schema: `TailoredResumeArtifactRef` (filename/path/version)

### Looping for refinement (optional)

If you want iterative improvement, wrap stages 4–5 in a `LoopAgent` with `max_iterations=N` (mirroring `refs/test_architect/code_analyst/agent.py`). The loop condition can be based on `state["resume_qa"]["pass"]`.

## Database strategy for resume tailoring

Constraints: `job_postings.status` has a CHECK constraint (NEW/FILTERED/QUALIFIED/APPLIED/REJECTED). Adding new statuses like TAILORED requires altering that constraint.

Recommended approach:
- Keep `status` semantics for job selection (`QUALIFIED` jobs get resume-tailored).
- Use `agent_result` JSON to store:
  - `stage`: "resume_tailor"
  - `tailoring_version`: integer
  - `tailored_resume_artifact`: {path/filename/version}
  - `qa`: {pass, issues}
  - `timestamp`

If you later want multiple agent stages (qualify vs tailor vs apply), we can add a separate table like `job_agent_runs` keyed by `job_hash` + `stage` + timestamps.

## Verification plan (how we’ll know Phase 2 is “good”)

### A) Static checks
- `src/agents/...` exists and imports correctly.
- `main.py` includes a `run_agent_workflow()` that:
  - loads jobs from DB
  - constructs `ResumeTailorRequest` Pydantic model
  - passes `request.model_dump_json()` to runner

### B) DB migration
- On startup of agent workflow: call `db.create_tables()` and `db.migrate_agent_schema()`.

### C) Smoke test
- Run discovery once.
- Mark a small number of jobs as `QUALIFIED` (manual DB update or future qualifier step).
- Run resume-tailor workflow on 1–3 jobs with `AGENT_BATCH_SIZE=3`.
- Confirm:
  - `agent_processed_at` is set
  - `agent_result` contains JSON with stage=resume_tailor

### D) Contract tests
- Validate that the agent accepts input adhering to `input_schema=ResumeTailorRequest`.

## Questions to answer before implementing (full list)

### LaTeX constraints
1) Resume TeX is **not yet committed**: we’ll implement the workflow behind a path-based interface and you’ll add the TeX later.
2) Build tool: **latexmk**.
3) Markers: **Yes** — we’ll use LaTeX comment markers as sentinels (safe; comments are ignored by LaTeX).
4) Are there multiple sections allowed to change (Experience bullets only? Projects too?)
5) Do you have hard limits besides 1 page (e.g., “max 5 bullets per role”, “no bullet > 2 lines”)?

### Evidence / hallucination guardrails
6) Should the agent be constrained to only rephrase existing bullets, or can it add bullets derived from your resume inventory (but not present verbatim)?
7) Do you want an explicit “evidence map” output: each tailored bullet references source bullet(s) from the master resume?

### PDF verification
8) Which page-count tool is available/preferred: `pdfinfo`, `qpdf`, or other?
9) If the result is 2 pages, should the agent attempt an automatic retry (tighten bullets), or mark as failed and require manual intervention?

### Output location
10) Where should tailored outputs be written (directory structure, naming)?

---

(Original general questions below are still applicable, but the above are the critical ones for your LaTeX/PDF pipeline.)

### Resume source of truth
1) Where is your “master resume” stored today (markdown, docx, pdf, json, other)?
2) Do you maintain multiple master resumes (general SWE vs ML vs Infra)?
3) Do you want the system to maintain a structured “resume inventory” DB, or parse the resume every time?

### Tailoring policy / safety
4) Should the agent be allowed to *rewrite* accomplishments, or only select/reorder and lightly edit?
5) Strict “no hallucinations” policy: must every claim be directly traceable to your master resume text?
6) Are there red-line constraints (don’t mention certain companies, don’t mention dates, etc.)?

### Output format & delivery
7) Output formats required: markdown, PDF, DOCX, LaTeX?
8) Do you have an existing template (LaTeX, DOCX, Google Docs) that must be filled?
9) Do you want a “diff” output (what changed vs master resume) for review?
10) Do you want the agent to also generate a short recruiter summary / email blurb?

### Job targeting
11) Which jobs should be fed into resume tailoring?
   - all `NEW` jobs?
   - only `QUALIFIED` jobs?
12) Any caps per run (e.g., max 5 tailored resumes/day)?

### Candidate preferences
13) What role families are in-scope (backend, infra, ML, data, fullstack)?
14) Location constraints (remote only / hybrid ok)?
15) Compensation constraints: should resume tailoring consider salary bands at all?

### Evaluation criteria
16) What constitutes a “good” tailored resume?
   - keyword coverage threshold?
   - must include specific experiences?
   - must fit 1 page?
17) Should we optimize for ATS keyword matching vs human readability?

### Persistence & privacy
18) Where should tailored resumes be stored?
   - filesystem under `data/`?
   - ADK artifacts (requires artifact service configured in runner)?
   - cloud storage later?
19) Do you want the system to store job descriptions long-term (already in DB) and also store tailored resume text (sensitive) long-term?

### Human-in-the-loop
20) Do you want an approval step before writing the final PDF/DOCX?
21) Should the agent output a checklist of “missing evidence” (skills required but not in resume)?

## Phase 2 infra completion checklist (what we still need to implement)

1) Create the `src/agents/` package and define:
   - `src/agents/models.py`
   - `src/agents/root_agent.py` (wiring like `refs/test_architect/root_agent.py`)
   - `src/agents/resume_tailor/*` (schemas/prompts/agent)
2) Extend application `main.py`:
   - add `run_agent_workflow()` (post-discovery)
   - ensure it uses a Pydantic input model (ResumeTailorRequest) and passes JSON
   - ensure DB migration is called before processing
3) Add a minimal test proving:
   - JSON input validates against Pydantic schema
   - DB writeback to `agent_result`

---

## Notes on plan-mode constraints
This plan is designed to be executed with minimal disruption to Phase 1.
