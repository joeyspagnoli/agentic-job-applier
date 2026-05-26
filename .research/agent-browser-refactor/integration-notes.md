# Integration notes — agent-browser refactor

## Things verified against live CLI help

**`snapshot -i -c -s <selector>`** — all flags confirmed. `-i` (interactive only), `-c` (compact), `-s` (CSS selector scope). Comma-joined selectors like `"#application-form, #application_form"` are passed through to `document.querySelector` semantics; this matches what the design doc flagged as a risk — smoke-test it on a real form.

**`find role combobox click --name <label>`** — confirmed syntax from `find --help`. The `--name` flag filters by accessible name. This is the combobox-open step in `select_option`.

**`find text <value> click --exact`** — confirmed syntax. `--exact` requires exact text match. Used as the option-pick step in `select_option`.

**`find role radio click --name <option_value>`** — confirmed. `find role` accepts any ARIA role string; `radio` is valid. `--name` filters by accessible name. No scoping to a parent group is available via a single command, so `select_radio` tries this first then falls back to `find text ... click --exact`.

**`find role group click --name <group_label>`** — confirmed the syntax is valid (same `find role` pattern). However `click` on a `group` role may be a no-op on most ATSes since `radiogroup` containers aren't usually interactive. The fallback in `select_radio` proceeds to `find text` regardless of whether the group click succeeds — this is intentional.

**`wait --text <text>`** — confirmed. Used in `wait_for(text=...)`.
**`wait --url <pattern>`** — confirmed glob pattern support.
**`wait --load networkidle`** — confirmed valid load states: `load`, `domcontentloaded`, `networkidle`.
**`wait <ms>`** — confirmed integer ms mode.

**`press <key>`** — confirmed. Valid keys: `Enter`, `Tab`, `Escape`, and modifier chords like `Control+a`.

**`upload <sel> <files...>`** — confirmed. Accepts `@eN` refs. Single file path only needed for cover letter use case.

**`scrollintoview <sel>`** — confirmed (alias: `scrollinto`). Accepts `@eN` refs and CSS selectors.

**`screenshot [path]`** — confirmed. Path arg is optional (auto-names to temp dir when omitted); the tool always passes an explicit path for traceability.

## Decisions made

**`ModelRetry` consistently, not error dicts.** Every CLI failure raises `ModelRetry` with a helpful message. This keeps tool return types clean (always `str`) and lets the agent retry immediately without needing to parse an error shape. `FINISHER_AGENT_RETRIES = 2` in agent.py means each tool gets two retry slots.

**`asyncio.create_subprocess_exec` not `asyncio.to_thread(subprocess.run)`** — the user's prompt spec says async. `create_subprocess_exec` is natively async, no thread-pool overhead.

**`--json` not used for snapshot** — agent-browser's `--json` wraps the snapshot YAML inside a JSON object. The model consumes the raw YAML text directly; stripping the JSON envelope adds noise. JSON is used in `_ab_json` helper but the current tool set doesn't need it (kept as a helper for future use).

**`last_snapshot_names` parsed from snapshot text** — the forbidden-click guard needs to look up an element's name by ref. Rather than a separate CLI call (`agent-browser get attr aria-label @eN`), `get_snapshot` populates `ctx.deps.last_snapshot_names: dict[str, str]` by parsing lines of the form `@e5 [button] "Submit"`. This is best-effort; the guard fires only when a name is positively forbidden. False negatives (stale map) are acceptable because the system-prompt rule is the primary defense.

**`FinisherDeps` needs two new fields** — `form_root_css: str` (replaces `form_root_selector`, same values, same semantics) and `last_snapshot_names: dict[str, str]` (initialized to `{}`). The `page: "Page"` field should become `Optional["Page"] = None` in a transitional commit, then removed when the Playwright tools are fully gone.

**`select_radio` group-click fallback** — `find role group click` may not work on every ATS (some use `role=radiogroup` not `role=group`; some don't expose the container at all). The fallback to `find text <option_value> click --exact` is the reliable path; the group focus is just a courtesy hint to the accessibility tree. If it fails, we log at DEBUG and move on.

**`_COMBOBOX_SETTLE_MS = 250`** — empirical from hands-on session. The listbox needs a tick to render after the combobox opens; 250ms is conservative but cheap. Tune down to 150ms if form fill speed matters.

## Things the implementer must do before shipping

1. Update `FinisherDeps` in `schemas.py`: add `form_root_css: str`, add `last_snapshot_names: dict[str, str] = field(default_factory=dict)`, make `page` optional.
2. Update `runner.py`: pass `apply_url` instead of `page`; add pre-flight URL check; construct `FinisherDeps` without `page`.
3. Update `browser.py` call site: `run_finisher(apply_url=playwright_page.url, ...)`.
4. Smoke-test `#application-form, #application_form` comma selector with `-s` on a live Greenhouse form.
5. Smoke-test `select_option("Phone Country Flag", "United States (+1)")` on the `intl-tel-input` widget — fall back to `.iti__selected-flag` CSS if the accessible name doesn't match.
6. Replace `AsyncMock(Page)` in existing tests with `monkeypatch.setattr` on `tools._ab`.
