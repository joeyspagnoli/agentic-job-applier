# Test seam sketch

## The new boundary

All five browser tools ultimately call `tools._ab(args: list[str]) -> str`.
Tests mock `_ab`, not `subprocess.run` directly, for cleaner granularity.

```python
# src/agents/apply_finisher/tools.py

import asyncio
import subprocess

async def _ab(args: list[str]) -> str:
    """Run an agent-browser CLI command and return stdout.
    
    Raises ModelRetry on non-zero returncode.
    """
    result = await asyncio.to_thread(
        subprocess.run,
        ["agent-browser"] + args,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ModelRetry(
            f"agent-browser {' '.join(args)} failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()
```

## Unit test pattern

```python
# tests/agents/apply_finisher/test_tools.py

import pytest
from unittest.mock import AsyncMock, patch

GREENHOUSE_SNAPSHOT = """\
Page: Software Engineer - Apply
URL: https://job-boards.greenhouse.io/acme/jobs/123

@e1 [heading] "Apply for Software Engineer"
@e2 [form]
  @e3 [textbox] "First Name" (required)
  @e4 [textbox] "Last Name" (required)
  @e5 [textbox] "Email" (required)
  @e6 [combobox] "Country" (required)
  @e7 [button type="submit"] "Submit Application"
"""

@pytest.fixture
def ab_responses():
    """Map of CLI args tuple → stdout string for snapshot, fill, click, etc."""
    return {
        ("snapshot", "-i", "-c", "-s", "#application-form, #application_form"): GREENHOUSE_SNAPSHOT,
        ("fill", "@e3", "Jane"): "filled @e3 with 'Jane'",
        ("find", "role", "combobox", "click", "--name", "Country"): "clicked combobox 'Country'",
        ("find", "text", "United States", "click", "--exact"): "clicked 'United States'",
    }

@pytest.fixture
def mock_ab(ab_responses, monkeypatch):
    async def fake_ab(args):
        key = tuple(args)
        if key in ab_responses:
            return ab_responses[key]
        raise AssertionError(f"Unexpected agent-browser call: {args}")
    monkeypatch.setattr("src.agents.apply_finisher.tools._ab", fake_ab)
    return fake_ab

async def test_get_snapshot_returns_tree(mock_ab, greenhouse_deps):
    from src.agents.apply_finisher.tools import get_snapshot
    ctx = make_ctx(greenhouse_deps)
    result = await get_snapshot(ctx)
    assert "@e3" in result.return_value
    assert "@e7" in result.return_value  # submit button visible in snapshot

async def test_click_blocks_submit_ref(mock_ab, greenhouse_deps):
    from src.agents.apply_finisher.tools import click
    # Simulate snapshot was already taken; @e7 is "Submit Application"
    greenhouse_deps.last_snapshot_names["@e7"] = "Submit Application"
    ctx = make_ctx(greenhouse_deps)
    with pytest.raises(ModelRetry, match="submit"):
        await click(ctx, ref="@e7")

async def test_click_semantic_combobox(mock_ab, greenhouse_deps):
    from src.agents.apply_finisher.tools import click
    ctx = make_ctx(greenhouse_deps)
    result = await click(ctx, label="Country")
    assert "combobox" in result

async def test_select_option_picks_value(mock_ab, greenhouse_deps):
    from src.agents.apply_finisher.tools import select_option
    ctx = make_ctx(greenhouse_deps)
    result = await select_option(ctx, label="Country", value="United States")
    assert "United States" in result
```

## Snapshot fixture files

```
tests/fixtures/snapshots/
  greenhouse_form_initial.txt     # the form before any fills
  greenhouse_form_combobox_open.txt  # after Country combobox is opened
  ashby_form_initial.txt
  ashby_eeo_fieldset.txt
```

Generated once with:
```bash
AGENT_BROWSER_CDP_URL=http://localhost:9222 \
  agent-browser snapshot -i -c -s "#application-form" \
  > tests/fixtures/snapshots/greenhouse_form_initial.txt
```

## What existing tests need to change

`tests/test_apply_loop_safe_mode.py` and `tests/test_user_triggered_apply.py`:
- Remove `page=AsyncMock(spec=Page)` from `run_finisher` calls.
- Add `apply_url="https://job-boards.greenhouse.io/acme/jobs/123"`.
- Add `mock_ab` fixture at the session level with a canned full-form interaction sequence.

`runner.py` tests:
- The pre-flight URL check calls `_ab(["get", "url"])` — add this to `ab_responses`.

## Smoke test (live, safe_mode=True)

```bash
# Run against a real Greenhouse form in safe_mode (no submit)
SAFE_MODE=1 python -m scripts.process_apply_jobs \
  --job-url "https://job-boards.greenhouse.io/cloudflare/jobs/..." \
  --dry-run
```

Expected: finisher outcome=COMPLETE, fields_filled >= 4 (up from current ~4 with GAVE_UP), combobox fields filled (country, phone code, work auth Yes/No).
