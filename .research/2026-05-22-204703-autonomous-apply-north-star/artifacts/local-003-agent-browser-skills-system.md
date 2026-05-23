# local-003 — agent-browser skills system

- **Date:** 2026-05-22
- **Sources:**
  `reference-repos/agent-browser/cli/src/skills.rs`,
  `skills/agent-browser/SKILL.md`,
  `skill-data/core/SKILL.md`,
  `skill-data/core/templates/form-automation.sh`,
  `skill-data/dogfood/SKILL.md`,
  `skill-data/dogfood/templates/dogfood-report-template.md` (referenced),
  `AGENTS.md:18-26` (the "update all 5 places" doctrine).
- **Thesis:** A "skill" in agent-browser is a hand-written Markdown file with YAML frontmatter, plus optional `references/*.md` and `templates/*.sh|md` siblings. Skills are **not programs**, they are **instructions for an LLM**. They are bundled with the CLI binary (npm package) and served back to agents via `agent-browser skills get <name>`. There is no programmatic parameterization at call-time — agents read the skill and then issue normal CLI commands.

## Two directories, one discovery model

`cli/src/skills.rs:30`:

```rust
const SKILL_DIRS: &[&str] = &["skills", "skill-data"];
```

Both directories are walked when listing/getting skills (`skills.rs:67-85`). They serve different purposes:

- **`skills/`** — discovery stubs for external installers like `npx skills add` / `skills.sh`. Marked `hidden: true` in frontmatter so they don't pollute `skills list`. Currently just one: `skills/agent-browser/SKILL.md`.
- **`skill-data/`** — runtime skill content served by the CLI. Currently 6 dirs:
  - `core` — the general usage guide (the big one)
  - `dogfood` — exploratory testing / QA playbook
  - `electron` — driving Electron desktop apps via the embedded Chromium
  - `slack` — Slack-specific helpers
  - `vercel-sandbox` — running agent-browser inside Vercel Sandbox microVMs
  - `agentcore` — AWS Bedrock AgentCore cloud browser

## What a SKILL.md actually looks like

The discovery stub at `skills/agent-browser/SKILL.md:1-7`:

```markdown
---
name: agent-browser
description: Browser automation CLI for AI agents. Use when the user needs to interact with websites, including navigating pages, filling forms, clicking buttons, taking screenshots, extracting data, testing web apps, or automating any browser task. Triggers include requests to "open a website", "fill out a form", "click a button", "take a screenshot", "scrape data from a page", "test this web app", "login to a site", "automate browser actions", or any task requiring programmatic web interaction. Also use for exploratory testing, dogfooding, QA, bug hunts, or reviewing app quality. ...
allowed-tools: Bash(agent-browser:*), Bash(npx agent-browser:*)
hidden: true
---

# agent-browser

Fast browser automation CLI for AI agents. Chrome/Chromium via CDP with
accessibility-tree snapshots and compact `@eN` element refs.
```

Three frontmatter keys are parsed (`skills.rs:88-125`):

```rust
fn parse_frontmatter(content: &str) -> Option<(String, String, bool)> {
    // ...
    while i < lines.len() {
        let line = lines[i];
        if let Some(val) = line.strip_prefix("name:") {
            name = Some(val.trim().to_string());
        } else if let Some(val) = line.strip_prefix("description:") {
            // consume YAML continuation lines (indented with spaces or tab)
            // ...
        } else if let Some(val) = line.strip_prefix("hidden:") {
            hidden = matches!(val.trim(), "true" | "yes");
        }
        i += 1;
    }
    Some((name?, description.unwrap_or_default(), hidden))
}
```

Everything else in the frontmatter (`allowed-tools`, `license`, etc.) is **ignored** by the Rust parser — it's Claude Code / Cursor / Codex that interpret those keys when the stub is shipped to them as an installable skill.

## How skills are served

`cli/src/skills.rs:258-365`:

```rust
fn run_get(skills_dirs: &[PathBuf], names: &[String], get_all: bool, full: bool, json_mode: bool) {
    // discover_skills walks SKILL_DIRS, parses every SKILL.md
    // ...
    for s in targets {
        let skill_md = s.dir.join("SKILL.md");
        if let Some(content) = read_skill_full(&skill_md) {
            print!("{}", content);   // print the whole .md verbatim
            // ...
        }
        if full {
            let supplementary = collect_supplementary_files(&s.dir);
            for (path, content) in &supplementary {
                println!("\n--- {} ---\n", path);
                print!("{}", content);
            }
        }
    }
}
```

`collect_supplementary_files` (`skills.rs:184-212`) walks the `references/` and `templates/` subdirs in order and concatenates them. No template substitution, no Mustache-style variables, no execution — it's literally `cat`.

So the contract is: agent runs `agent-browser skills get core`, the CLI prints the contents of `skill-data/core/SKILL.md` to stdout, the agent reads it as context, then issues normal `agent-browser <cmd>` calls.

`--json` mode (`skills.rs:315-340`) just wraps each file in an object:

```json
{
  "success": true,
  "data": [
    {
      "name": "core",
      "content": "<full SKILL.md text>",
      "files": [
        { "path": "references/authentication.md", "content": "..." },
        { "path": "templates/form-automation.sh", "content": "..." }
      ]
    }
  ]
}
```

## Concrete skill #1: the `core` skill (477 lines)

`skill-data/core/SKILL.md` is the main usage guide (frontmatter:1-5):

```markdown
---
name: core
description: Core agent-browser usage guide. Read this before running any agent-browser commands. Covers the snapshot-and-ref workflow, navigating pages, interacting with elements (click, fill, type, select), extracting text and data, taking screenshots, managing tabs, handling forms and auth, waiting for content, running multiple browser sessions in parallel, and troubleshooting common failures. ...
allowed-tools: Bash(agent-browser:*), Bash(npx agent-browser:*)
---
```

The 477 lines of body are pure instructions for the LLM — "the core loop" (snapshot → click → re-snapshot), "waiting (read this)" because "agents fail more often from bad waits than from bad selectors" (skill-data/core/SKILL.md:144-167), worked examples for login, extraction, screenshots, multi-session, etc.

It has 8 reference files in `references/`:
```
authentication.md      profiling.md         snapshot-refs.md     trust-boundaries.md
commands.md            proxy-support.md     session-management.md video-recording.md
```

And 3 templates in `templates/`:
```
authenticated-session.sh   capture-workflow.sh   form-automation.sh
```

The "skill" is **the prose plus the templates**. It contains zero executable program logic — `templates/form-automation.sh` is a 63-line bash skeleton the agent is expected to copy and edit (it has comments like "Customize: Update the refs (@e1, @e2, etc.) based on your form's snapshot output").

`templates/form-automation.sh:30-46`:

```bash
# Step 3: Fill form fields (customize these refs based on snapshot output)
#
# Common field types:
#   agent-browser fill @e1 "John Doe"           # Text input
#   agent-browser fill @e2 "user@example.com"   # Email input
#   ...
#   agent-browser upload @e8 /path/to/file.pdf  # File upload
#
# Uncomment and modify:
# agent-browser fill @e1 "Test User"
# agent-browser fill @e2 "test@example.com"
# agent-browser click @e3  # Submit button
```

It's a worked example with `agent-browser` invocations the LLM is expected to adapt. No parameter binding. No call-site abstraction.

## Concrete skill #2: the `dogfood` skill

`skill-data/dogfood/SKILL.md:1-5`:

```markdown
---
name: dogfood
description: Systematically explore and test a web application to find bugs, UX issues, and other problems. Use when asked to "dogfood", "QA", "exploratory test", "find issues", "bug hunt", "test this app/site/platform", or review the quality of a web application. ...
allowed-tools: Bash(agent-browser:*), Bash(npx agent-browser:*)
---
```

The 221-line body is a step-by-step QA playbook with sections "Initialize", "Authenticate", "Orient", "Explore", "Document Issues (Repro-First)", "Wrap Up". It tells the agent verbatim what shell commands to run, e.g. `dogfood/SKILL.md:40-55`:

```bash
mkdir -p {OUTPUT_DIR}/screenshots {OUTPUT_DIR}/videos
cp {SKILL_DIR}/templates/dogfood-report-template.md {OUTPUT_DIR}/report.md

agent-browser --session {SESSION} open {TARGET_URL}
agent-browser --session {SESSION} wait --load networkidle
```

Note the **`{OUTPUT_DIR}`, `{SESSION}`, `{TARGET_URL}` placeholders** — those are not interpolated by anything in agent-browser. They are read by the LLM and replaced with values from the user's request. The "parameterization" is "the model substitutes literals while reading the skill". There is no `agent-browser skills get dogfood --session foo --target https://...` invocation that does substitution.

## Concrete skill #3: the bootstrap stub

`skills/agent-browser/SKILL.md:18-39`:

```markdown
This file is a discovery stub, not the usage guide. Before running any
`agent-browser` command, load the actual workflow content from the CLI:

```bash
agent-browser skills get core             # start here — workflows, common patterns, troubleshooting
agent-browser skills get core --full      # include full command reference and templates
```

The CLI serves skill content that always matches the installed version,
so instructions never go stale. The content in this stub cannot change
between releases, which is why it just points at `skills get core`.

## Specialized skills

Load a specialized skill when the task falls outside browser web pages:

```bash
agent-browser skills get electron          # Electron desktop apps (VS Code, Slack, Discord, Figma, ...)
agent-browser skills get slack             # Slack workspace automation
agent-browser skills get dogfood           # Exploratory testing / QA / bug hunts
agent-browser skills get vercel-sandbox    # agent-browser inside Vercel Sandbox microVMs
agent-browser skills get agentcore         # AWS Bedrock AgentCore cloud browsers
```
```

The stub exists only to redirect agents who installed agent-browser via the Claude Code / Cursor / Codex skill mechanism. It is `hidden: true` so it doesn't appear in `skills list` or `skills get --all` (`skills.rs:217-218`).

## Are skills hand-authored, LLM-generated, or recorded?

Hand-authored, by humans. The `AGENTS.md` "Documentation" doctrine (lines 16-26) requires that every behavior change be reflected in **all five** of:

1. `cli/src/output.rs` (`--help` output)
2. `README.md`
3. `skill-data/core/SKILL.md` and its `references/`
4. `docs/src/app/` (the Next.js docs site)
5. Inline doc comments in the source

This is the same "treat skills as living docs" pattern Anthropic uses internally. There is **no** trace recording, **no** generation pipeline, **no** demonstration-to-skill compiler in this repo. `cli/src/native/recording.rs` exists but it's video recording (webm output), not action recording.

## Parameterization at call-time? No.

`run_get` (`skills.rs:258`) takes only `(names, get_all, full, json_mode)`. There is no `--var key=value`, no template engine, no Jinja, no MCP-style argument schema. The skill is text. Substitution happens in the LLM's head.

The closest thing to a "callable" skill is a `template` file. `core/templates/form-automation.sh` takes `$1` (the form URL) as a real shell argument:

```bash
FORM_URL="${1:?Usage: $0 <form-url>}"
agent-browser open "$FORM_URL"
agent-browser wait --load networkidle
agent-browser snapshot -i
# ... rest is comments the LLM is expected to fill in
```

So you could `bash $(agent-browser skills path core)/templates/form-automation.sh https://example.com/signup` — but you'd still need an LLM in the loop to fill in the `fill @e1 ...` lines based on the snapshot output. The template doesn't run end-to-end.

## Why this design

Quote from `skills/agent-browser/SKILL.md:25-27`:

> The CLI serves skill content that always matches the installed version, so instructions never go stale. The content in this stub cannot change between releases, which is why it just points at `skills get core`.

The pattern is: shipped CLI binary contains its own LLM-readable docs, served on demand. This means a 3-month-old skill installation in Cursor doesn't drift from the live CLI capabilities — the agent always re-pulls the current docs at task time.

This also means: **the skills system is not extensible at runtime by the caller**. Skills are baked into the npm package via `package.json:11-16`:

```json
"files": [
  "bin",
  "scripts",
  "skill-data",
  "skills"
]
```

You can override the search path with `AGENT_BROWSER_SKILLS_DIR` env var (`skills.rs:69-74`) to load your own skill directory, but that's a single-directory replacement, not a merge.

## Bottom line for our use case

If we want our worker to "know how to finish a Workday application", the agent-browser path would be:

1. Author a `skill-data/job-application/SKILL.md` describing the workflow (which we'd ship outside the agent-browser package — via `AGENT_BROWSER_SKILLS_DIR` or just by passing the markdown as a system prompt directly).
2. The LLM reads it and emits a sequence of `agent-browser` CLI calls.
3. We execute those calls (or let `agent-browser chat` execute them — see `local-005`).

There is no "register a function called `apply_to_job(url, resume_pdf)`" — agent-browser's skill system is **not function-registration**, it's **prompt-engineering-via-versioned-markdown**.
