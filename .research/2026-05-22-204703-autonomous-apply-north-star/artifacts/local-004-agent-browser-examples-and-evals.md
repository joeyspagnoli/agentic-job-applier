# local-004 — agent-browser examples, benchmarks, and evals

- **Date:** 2026-05-22
- **Sources:**
  `reference-repos/agent-browser/examples/environments/README.md`,
  `examples/environments/lib/agent-browser-sandbox.ts`,
  `examples/environments/app/page.tsx` (referenced),
  `benchmarks/README.md`,
  `benchmarks/scenarios.ts`,
  `evals/README.md`,
  `evals/cases/command-usage.ts`,
  `evals/cases/skill-loading.ts` and `skill-selection.ts` (referenced),
  `evals/lib/{claude.ts,codex.ts,judge.ts,providers.ts,reporter.ts,types.ts}`.
- **Thesis:** The repo's "examples" are a single Vercel-sandbox screenshot/snapshot demo, not multi-step form-fill workflows. The "benchmarks" are CLI latency micro-benchmarks against a static HTML form injected via `document.write`. The "evals" do not run a real browser at all — they test whether two CLI agents (Claude Code / Codex) emit the right shell commands when prompted. **There is no end-to-end "agent fills a real screener" evaluation anywhere in this repo.**

## examples/ — one demo, very limited

```
$ ls reference-repos/agent-browser/examples/
environments

$ ls examples/environments/
app/  components/  lib/  scripts/  package.json  README.md  ...
```

There is exactly one example: `examples/environments`, a Next.js app whose only feature is "type a URL, see a screenshot or a snapshot of it, served by agent-browser running inside a Vercel sandbox microVM."

`examples/environments/README.md:1-10`:

> # agent-browser Environments
>
> A demo of agent-browser running in a Vercel Sandbox. Pick a URL, take a screenshot or accessibility snapshot, and watch each command execute in real time.

The actual work it does (`examples/environments/lib/agent-browser-sandbox.ts:173-230`):

```typescript
export async function screenshotUrl(
  url: string,
  opts: { fullPage?: boolean; onStep?: OnStep } = {},
): Promise<{ screenshot: string; title: string }> {
  // ...
  await exec(sandbox, "agent-browser", ["open", "about:blank"], ...);
  await exec(sandbox, "agent-browser", ["open", url], ...);
  // get title
  const titleResult = await exec(
    sandbox, "agent-browser", ["get", "title", "--json"], ...
  );
  // screenshot
  const screenshotArgs = ["screenshot", "--json"];
  if (opts.fullPage) screenshotArgs.push("--full");
  const ssResult = await exec(sandbox, "agent-browser", screenshotArgs, ...);
  // read file out of sandbox via base64
  const b64Result = await exec(sandbox, "base64", ["-w", "0", screenshotPath], ...);
  // ...
  await exec(sandbox, "agent-browser", ["close"], ...);
  return { screenshot, title };
}
```

The `snapshotUrl` sibling (lines 235-276) is the same shape but adds `-i` / `-c` flags. **There is no form-fill example, no multi-step navigation example, no auth example in `examples/`.**

This is the only canonical "here's how to call agent-browser from a real app" reference shipped with the repo. The user has to extrapolate from there.

## benchmarks/ — synthetic-form micro-benchmarks

`benchmarks/scenarios.ts:17-32` is the "form" being benchmarked:

```typescript
const FORM_HTML = [
  "<html><head><title>Bench</title></head><body>",
  "<h1>Benchmark Page</h1>",
  "<input id='name' type='text' placeholder='Name'>",
  "<input id='email' type='email' placeholder='Email'>",
  "<select id='color'><option value='red'>Red</option><option value='blue'>Blue</option></select>",
  "<input id='agree' type='checkbox'>",
  "<textarea id='bio' placeholder='Bio'></textarea>",
  "<button id='submit'>Submit</button>",
  ...
].join("");

const INJECT_FORM_SCRIPT = `document.open(); document.write(${JSON.stringify(FORM_HTML)}); document.close(); 'ok'`;
```

Then the scenarios (`scenarios.ts:41-105`):

```typescript
{
  name: "fill",
  description: "Form field fill",
  setup: SETUP_PAGE,
  commands: [["fill", "#name", "Benchmark User"]],
},
{
  name: "agent-loop",
  description: "AI agent loop: snapshot -> click -> snapshot (typical agent cycle)",
  setup: SETUP_PAGE,
  commands: [["snapshot"], ["click", "#link"], ["snapshot"]],
},
{
  name: "full-workflow",
  description: "Realistic workflow: navigate, inject form, snapshot, click, fill, evaluate, screenshot",
  commands: [
    ["open", "about:blank"],
    ["eval", INJECT_FORM_SCRIPT],
    ["snapshot"],
    ["click", "#link"],
    ["fill", "#name", "Agent User"],
    ["eval", "document.getElementById('name').value"],
    ["screenshot"],
  ],
},
```

This is **not** a job-application form. It's an injected toy with 4 inputs and a submit button. It measures CLI-to-Chrome round-trip latency. The benchmark README (`benchmarks/README.md:69-74`) says explicitly:

> Command latency is dominated by Chrome (CDP round-trips), not the daemon. Both daemons are thin relays between the CLI and Chrome, so per-command speedups are typically small.

So the benchmarks are about the Rust-vs-Node daemon rewrite, not about end-to-end form-filling reliability.

## evals/ — the most relevant artifact for our question

`evals/README.md:73-93` lists three eval categories:

> ### skill-loading
> Tests that the agent runs `agent-browser skills get` before issuing browser commands. ...
>
> ### skill-selection
> Tests that the agent picks the correct specialized skill for the task. ...
>
> ### command-usage
> Tests that the agent produces correct agent-browser commands for common workflows: navigation + screenshot, form filling with snapshot-interact pattern, diffing, authentication, data extraction.

And the eval mechanism (`evals/README.md:85-91`):

> 1. Each eval case provides a user task prompt
> 2. The thin `skills/agent-browser/SKILL.md` is injected as context (simulating a skill installation)
> 3. The chosen provider CLI is called to get a single response
> 4. Pattern matching checks for expected/forbidden command patterns (pass/fail)
> 5. Optionally, a second Claude call judges response quality on a 1-5 scale

Critical reading: **steps 1-5 never touch a browser**. The eval drives `claude -p <prompt>` or `codex exec --json <prompt>` and regex-matches the *text* of the model's reply.

`evals/cases/command-usage.ts:46-57` (the "form filling workflow" eval):

```typescript
{
  id: "cu-02",
  name: "Form filling workflow",
  category: "command-usage",
  prompt:
    "Go to example.com/signup, fill in name as 'Jane Doe' and email as 'jane@test.com', then submit",
  context: COMMAND_CONTEXT,
  expectedPatterns: [
    "agent-browser\\s+(open|goto|navigate)",
    "agent-browser\\s+snapshot",
    "agent-browser\\s+(fill|type)",
    "agent-browser\\s+(click|press|key)",
  ],
  rubric: RUBRIC,
}
```

"Pass" means the model's text reply contained those four regexes. "Fail" means it didn't. There is no example.com/signup being hit, no real form, no verification that the actual sequence of CLI commands would succeed against a live page. This is **prompt-following evaluation, not behavior evaluation**.

The rubric (lines 3-9) shows what "5/5" looks like according to a 1-5 LLM judge call (`evals/lib/judge.ts`):

```
1 - Agent does not produce valid agent-browser commands
2 - Agent uses agent-browser but with wrong commands or missing steps
3 - Agent uses correct commands but skips the snapshot-interact workflow
4 - Agent follows the correct workflow with appropriate commands
5 - Agent follows the optimal workflow: navigate, snapshot, interact with refs, re-snapshot as needed
```

So the maintainers' bar for "good" is "the model emits the canonical snapshot-then-act sequence in text". The repo never measures what happens when those commands actually run.

The 7 command-usage cases (`cases/command-usage.ts:30-119`) are:
1. `cu-01` — open + screenshot example.com
2. `cu-02` — signup form (Name + Email + Submit, two fields)
3. `cu-03` — get interactive elements of example.com
4. `cu-04` — diff staging vs prod homepages
5. `cu-05` — log in, save state
6. `cu-06` — extract main heading text
7. `cu-07` — full-page screenshot

None resemble a multi-step screener with custom textareas, EEO multi-selects, Workday-style "Continue" pages, or visa questions. The maintainers have not validated agent-browser against anything more complex than 2-field forms.

## Walk-through of the most-relevant example: `examples/environments` UI flow

Pulling together `examples/environments/lib/agent-browser-sandbox.ts:117-167` + `examples/environments/app/page.tsx` (which the README references at lines 49-61):

1. User types a URL in the demo UI.
2. The Next.js server (running in Vercel) hits the `examples/environments/app/api/browse/route.ts` SSE endpoint.
3. The route calls `screenshotUrl(url, { fullPage, onStep })` from `agent-browser-sandbox.ts`.
4. `createSandbox()` either boots from a pre-built Vercel Sandbox snapshot (sub-second) or installs agent-browser + Chromium from scratch (~30s, `bootstrapSandbox` at lines 100-115):

```typescript
async function bootstrapSandbox(sandbox, onStep) {
  await runStep("Installing system dependencies", async () => {
    await sandbox.runCommand("sh", ["-c",
      `sudo dnf clean all && sudo dnf install -y --skip-broken ${CHROMIUM_SYSTEM_DEPS.join(" ")} ...`,
    ]);
  }, onStep);
  await runStep("Installing agent-browser", async () => {
    await sandbox.runCommand("npm", ["install", "-g", "agent-browser"]);
    await sandbox.runCommand("npx", ["agent-browser", "install"]);
  }, onStep);
}
```

5. The sandbox runs three sequential `agent-browser` commands: `open about:blank`, `open <url>`, `get title --json`.
6. The screenshot is taken with `screenshot --json`, the path is extracted from the JSON response (`ssData?.path`), then a separate `base64 -w 0 <path>` exec reads the file out of the microVM.
7. `agent-browser close` cleans up, then `sandbox.stop()`.

This is the entire example. It shows three things:

- The right pattern for parsing `--json` responses (use the `data.path` field for screenshot results).
- That agent-browser inside an ephemeral Linux microVM works (no native deps in the host process).
- That the cold-start cost without a sandbox snapshot is real (~30s).

It does **not** show:
- How to handle multi-page navigation.
- How to handle a dynamic form where field labels change.
- How to upload a file.
- How to wait for and pierce shadow DOM.
- How to recover when a click is intercepted.
- How to gate a destructive action.

## Highest-signal eval, walked through

`evals/cases/command-usage.ts:46-57` (`cu-02`, form filling). The full execution path:

1. `evals/run.ts` (referenced in `README.md:23-49`) loads the case, picks the provider (default: `claude -p`), and assembles the prompt.
2. The system context is the thin `skills/agent-browser/SKILL.md` stub plus the case's `COMMAND_CONTEXT` (a 15-line cheat-sheet of common commands).
3. The user prompt is `"Go to example.com/signup, fill in name as 'Jane Doe' and email as 'jane@test.com', then submit"`.
4. The provider CLI is invoked: `claude -p "<system+user>"` (`evals/lib/claude.ts`) or `codex exec --json` (`evals/lib/codex.ts`). API key: `AI_GATEWAY_API_KEY` via the Vercel AI Gateway (no direct Anthropic/OpenAI calls).
5. The model returns text. The eval doesn't execute the text — it `match`es it against:
   ```
   ["agent-browser\\s+(open|goto|navigate)",
    "agent-browser\\s+snapshot",
    "agent-browser\\s+(fill|type)",
    "agent-browser\\s+(click|press|key)"]
   ```
6. Pass = all four regexes match. Fail = any one missing.
7. With `--judge`, a separate `anthropic/claude-opus-4.6` call scores the reply 1-5 against the rubric.

Result format (`evals/README.md:117-127`):

```
skill-loading
----------------------------------------------------------------------
  ✓ Loads skill before opening a page                      PASS  3200ms
  ✗ Loads skill before form interaction                    FAIL  2800ms
    ✗ Expected pattern not found: agent-browser skills get
```

What this eval **does** test: "Does the chosen LLM, when given the thin SKILL.md as context, know to emit the snapshot-then-act pattern?" That is genuinely useful — it validates the prompt-engineering of the skill files.

What it **does not** test: anything about agent-browser as a piece of software. Correctness, reliability, real-page behavior, error recovery, all unmeasured.

## Implication for our use case

We will need to **build our own end-to-end evals** if we want confidence that agent-browser + an LLM can finish a screener page. The maintainers haven't done that work and there is no test fixture in the repo for a Workday- or Greenhouse-shaped form. The benchmarks/, examples/, and evals/ directories will not bootstrap us — they are about the CLI surface, not about complete tasks.

The good news: the `core` skill itself (analyzed in `local-003`) is high-quality, version-locked, and ~477 lines of detailed how-to. So if we shell out to `agent-browser` from our Python worker and provide an LLM with `agent-browser skills get core --full` as context, we'd be using the same prompt-engineering surface the maintainers use for their evals. The gap is between "LLM emits good commands" (evaluated) and "those commands succeed on a real recruiting site" (not evaluated, on us).
