# Reference: Official Pydantic AI ModelRetry example (`data_analyst.py`)

**File:** `examples/pydantic_ai_examples/data_analyst.py`
**Repo:** https://github.com/pydantic/pydantic-ai (canonical)
**Fetched:** 2026-05-25 via `gh api`

## Pattern: ModelRetry on stale ref / invalid argument

```python
@dataclass
class AnalystAgentDeps:
    output: dict[str, pd.DataFrame] = field(default_factory=dict)

    def store(self, value: pd.DataFrame) -> str:
        """Store the output in deps and return the reference such as Out[1] to be used by the LLM."""
        ref = f'Out[{len(self.output) + 1}]'
        self.output[ref] = value
        return ref

    def get(self, ref: str) -> pd.DataFrame:
        if ref not in self.output:
            raise ModelRetry(
                f'Error: {ref} is not a valid variable reference. '
                f'Check the previous messages and try again.'
            )
        return self.output[ref]
```

**This is EXACTLY the pattern for finisher refs.** Replace `Out[1]` → `@e1` and `pd.DataFrame` →
`Locator`, and you have the finisher ref-lookup. The error message tells the model precisely how
to recover (look at previous messages = look at the latest snapshot).

## Second ModelRetry pattern — invalid argument

```python
if split not in splits:
    raise ModelRetry(
        f'{split} is not valid for dataset {path}. '
        f'Valid splits are {",".join(splits.keys())}'
    )
```

**Note the structure:** the error message ENUMERATES the valid values so the model can self-correct.
For finisher's `select(ref, value)` tool, when value is not one of the dropdown options:

```python
@finisher.tool
async def select(ctx: RunContext[FinisherDeps], ref: str, value: str) -> str:
    locator = ctx.deps.snapshot.resolve(ref)
    if locator is None:
        raise ModelRetry(f"Ref {ref} not found. Call get_snapshot() first.")
    options = await locator.locator("option").all_inner_texts()
    if value not in options:
        raise ModelRetry(
            f"'{value}' is not a valid option for {ref}. "
            f"Valid options are: {', '.join(options)}"
        )
    await locator.select_option(value)
    return f"selected {value} for {ref}"
```

## Pattern: tool returns a string with a forward-progress message

```python
def store(self, value: pd.DataFrame) -> str:
    """Store the output in deps and return the reference such as Out[1] to be used by the LLM."""
    ref = f'Out[{len(self.output) + 1}]'
    self.output[ref] = value
    return ref
```

The tool returns the new ref to the model, so the model can use it in subsequent calls. For
finisher, our `fill()` tool should return something like `"filled ref @e3 with 'Jane' — current
form state: 3/10 fields filled"`. This is the "feedback signal" we discussed.

## Anti-patterns NOT seen in the official example

- No catch-all `except Exception: raise ModelRetry(...)` — would hide real bugs.
- No retry-counter inside the tool — the framework's `retries=N` handles that.
- No `time.sleep` or `await asyncio.sleep` inside the retry path — that's anti-pattern; backoff
  is the framework's job.
