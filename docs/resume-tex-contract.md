# Resume `.tex` contract

This file is the user-facing contract for `config/resume.tex`. The validator at
`src/agents/resume_tailor/validator.py` enforces it programmatically — every
rule below has a corresponding `CONTRACT_*` error code emitted at upload time.
The goal: every tailored PDF compiles from your own LaTeX with only bullets
rewritten, so the visual style of the output is identical to your base.

If your `.tex` does not match this contract, the upload endpoint rejects it
with a line-numbered structured error pointing at the violation and a
suggested fix.

## 1. Sections — what counts as tailorable

Headings the locator routes into the tailor LLM:

| Heading text (case-insensitive) | Kind |
|---|---|
| `Experience` | `experience` |
| `Work Experience` | `experience` |
| `Professional Experience` | `experience` |
| `Employment` | `experience` |
| `Employment History` | `experience` |
| `Work History` | `experience` |
| `Career Experience` | `experience` |
| `Projects` | `projects` |
| `Side Projects` | `projects` |
| `Personal Projects` | `projects` |
| `Open Source Projects` | `projects` |
| `Selected Projects` | `projects` |

Detection regex:

```regex
^\s*\\section\{(?:\\textbf\{)?(?P<heading>[^{}]+?)\}?\}\s*$
```

Any other `\section{...}` — Skills, Education, Summary, Awards, Hobbies — is
recorded as kind `other` and silently skipped at tailor time. The validator
accepts them; the LLM never sees them.

**No localization in v1.** German / French / Spanish headings are treated as
`other`. Add an English alias `\section{Experience}` above your localized
heading if you want tailoring.

## 2. Entry headers — what counts as a role / project

A "role" or "project" entry inside a tailorable section must open with one of
the following patterns. The matched line becomes the entry's `role_context`
(the literal header text the LLM sees), and bullets between this header line
and the next entry's header line are treated as that entry's bullets.

| # | Pattern | Template family | Args |
|---|---|---|---|
| 1 | `\resumeSubheading{title}{dates}{org}{location}` | Jake's, sb2nov | 4 |
| 2 | `\cventry[opts]{a}{b}{c}{d}{e}{f}` | ModernCV (6-arg form) | 6 |
| 3 | `\cvitem{dates}{role at company}` | ModernCV terse | 2 |
| 4 | `\cvevent{title}{holder}{location}{description}` | AltaCV | 4 |
| 5 | `\runsubsection{company} \descript{| role} \location{dates}` | Deedy | 3 |
| 6 | `\item {\textbf{Role}} \hfill {\textbf{Dates}}` | Generic-bold (Jake's family without macro) | n/a |

Plus two **fallback** patterns, used only when none of the six above match a
given line in an experience/projects section:

- **Fallback A:** `\textbf{Role at Company}` on a line by itself.
- **Fallback B:** `\textbf{Role}\hfill Dates` on a line by itself. Dates must
  start with an uppercase letter or digit.

All regex `{}` arg captures use `[^{}]*` — nested braces inside a macro arg
break the match. If your entry header contains macros (`\textbf{...}` etc.)
in its body, the entry is currently skipped; the planned v2 TexSoup
cross-check will support it.

## 3. Bullets — what gets rewritten

A bullet is one of:

1. **`\resumeItem{body}`** — Jake's / sb2nov / many forks. Balanced-brace body
   extraction (nested `\textbf{...}` etc. inside the body are preserved).
2. **`\cvline{label}{body}`** — Awesome-CV / ModernCV variant. Body = the
   second arg.
3. **`\item ...`** — only when inside an `itemize`-like block that lives
   under a recognized entry header. Body runs from the `\item` token to the
   next `\item`, `\end{itemize}`, `\resumeItemListEnd`, `\resumeSubHeadingListEnd`,
   `\resumeItem`, or `\cvline`.

The locator emits `(byte_start, byte_end)` of the **body only** (not the
wrapping macro). The patcher splices replacement text into that exact span,
which is why duplicate bullet bodies never confuse the patcher — byte offsets
disambiguate.

## 4. Structural rules — what the validator rejects

The validator runs these checks in order and **halts on the first failure**
so you see one targeted error at a time:

| Error code | When it fires | Suggested fix |
|---|---|---|
| `CONTRACT_COMPILE_FAILED` | Tectonic non-zero exit | Fix the LaTeX error from the log; run `tectonic -X compile <file>.tex` locally to iterate. |
| `CONTRACT_NO_TAILORABLE_SECTION` | Zero `\section{...}` headings match the allowlist in §1 | Add or rename a section heading (e.g. `\section{Experience}`). |
| `CONTRACT_UNKNOWN_ENTRY_HEADER` | A tailorable section has bullets but no recognized entry header | Wrap each role / project in `\resumeSubheading{...}{...}{...}{...}` (or another pattern from §2). |
| `CONTRACT_ORPHAN_BULLET` | A `\resumeItem` / `\cvline` / `\item` appears before any entry header in its section | Move the bullet under a recognized entry header, or add one above it. |
| `CONTRACT_UNBALANCED_BULLET` | A `\resumeItem{...}` or `\cvline{...}{...}` body has unbalanced `{` / `}` | Escape literal braces as `\{` / `\}`, or close the missing brace. |

Compile-check note: `\input{glyphtounicode}` and similar are allowed —
Tectonic resolves them. The validator does not recurse into `\input` targets.

## 5. Curated 10-template audit results

`scripts/audit_resume_templates.py` runs the validator + locator against
every fixture in `tests/fixtures/resumes/` and prints this table. Re-run it
after any contract change.

| # | Fixture | Verdict | Bullets | Notes |
|---|---|---|---|---|
| 1 | `synthetic_minimal.tex` | PASS | 4 | handwritten — Jake's-family minimal |
| 2 | `dogfood_user.tex` | PASS | 15 | this repo's own resume (generic-bold pattern #6) |
| 3 | `external/deedy_resume.tex` | PASS | 8 | Deedy `\runsubsection` (pattern #5) |
| 4 | `external/fallback_b_textbf_hfill.tex` | PASS | 4 | handwritten — Fallback B exemplar |
| 5 | `external/jakes_resume.tex` | FAIL | — | Projects section uses `\resumeProjectHeading` (2-arg variant not in §2); rewrap as `\resumeSubheading` to pass |
| 6 | `external/sb2nov_resume.tex` | FAIL | — | Projects section uses `\resumeSubItem` (label+body bullets); rewrap as `\resumeSubheading` + `\resumeItem` to pass |
| 7 | `external/altacv_sample.tex` | FAIL | — | uses `\cvsection{}` (not in §1); rename headings to `\section{}` |
| 8 | `external/posquit0_awesome_cv.tex` | FAIL | — | uses `\input{resume/*.tex}` fan-out + `\cvsection{}`; rename section macros and resolve includes |
| 9 | `external/mcdowell_cv.tex` | FAIL | — | uses `\begin{cvsection}{...}` environment form (not in §1) |
| 10 | `external/moderncv_template.tex` | FAIL | — | `\cventry` 6th arg contains nested `\begin{itemize}` — the `[^{}]` regex can't span the body; needs TexSoup cross-check (planned for v2) |
| 11 | `external/yaac_cv.tex` | FAIL | — | uses `\input{section_*.tex}` fan-out — content lives in files we don't vendor |

**Current pass rate: 4 / 11 = 36%.** Below the plan §11 Abort threshold of
60% — flagged for user decision. Two paths forward:

- **(a) Loosen the contract** to recognize `\cvsection{...}`, `\begin{cvsection}{...}`,
  `\resumeProjectHeading{...}{...}`, and `\resumeSubItem{...}{...}`. This
  would unlock 5 more templates but expands the regex surface.
- **(b) Document the failing templates as "needs minor modification"** and
  ship the strict contract.

Pick at Phase 1 planning; Phase 0 ships the strict version.

## 6. Migration for non-conforming templates

If your template falls in the "needs minor modification" bucket, the
cheapest fix is usually to add a wrapper macro at the top of your
preamble:

```latex
% Make \resumeProjectHeading look like \resumeSubheading to the validator.
\renewcommand{\resumeProjectHeading}[2]{\resumeSubheading{#1}{#2}{}{}}
```

```latex
% Or, for Awesome-CV: alias \cvsection back to \section.
\let\cvsection\section
```

The PDF compiles to the same output because the wrapper expands to your
template's original macros at LaTeX time; the validator just needs a
recognizable surface form.
