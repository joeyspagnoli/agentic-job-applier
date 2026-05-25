# local-gap-audit-004 — apply_handoffs migration template

**Source:** `src/database/_mixins/apply.py` lines 26-115 (the only `apply_handoffs`-related migration code path in the repo).
**Trigger:** Epic Phase D — adds `deferred_questions_json` and `finisher_diagnostics_json` columns. Check for prior `ALTER TABLE` patterns to follow.

## Discovery

**There is no `src/database/migrations/` directory.** Schema changes are not managed by a numbered-migration tool (Alembic, yoyo, sqlite-utils, etc.). All schema bootstrap happens inside `migrate_apply_schema()` and the sibling `migrate_review_schema()` / `migrate_cost_schema()` methods on the DB manager mixins.

The pattern is:
1. Each mixin has a `migrate_<thing>_schema()` method.
2. The method runs `CREATE TABLE IF NOT EXISTS ...` + `CREATE INDEX IF NOT EXISTS ...` inside a single `executescript()` call.
3. A flag (`_apply_schema_ready`, etc.) caches the "already ran" state.
4. Every query path that touches the table calls `_ensure_apply_schema_ready()` first.

There is **no `ALTER TABLE` anywhere in the codebase today** — confirmed by lack of search hits. The system assumes the `CREATE TABLE IF NOT EXISTS` runs first, and new columns are appended in-line to the CREATE statement. **For a fresh DB this works.** For an existing DB (which the user already has, since the smoke run produced real rows), the new columns will be missing until something explicitly adds them.

## Implications for the epic

Two options for adding `deferred_questions_json` + `finisher_diagnostics_json`:

**Option A (least invasive, follows the existing convention):** Add the two columns to the `CREATE TABLE IF NOT EXISTS apply_handoffs (...)` block in `migrate_apply_schema()` AND add a guarded `ALTER TABLE apply_handoffs ADD COLUMN ...` block after the create script. SQLite swallows `ADD COLUMN IF NOT EXISTS`-style only via PRAGMA pre-check, so:

```python
# After the executescript that creates tables:
existing_cols = {
    r["name"]
    for r in await conn.execute("PRAGMA table_info(apply_handoffs)")
}
if "deferred_questions_json" not in existing_cols:
    await conn.execute(
        "ALTER TABLE apply_handoffs ADD COLUMN deferred_questions_json TEXT"
    )
if "finisher_diagnostics_json" not in existing_cols:
    await conn.execute(
        "ALTER TABLE apply_handoffs ADD COLUMN finisher_diagnostics_json TEXT"
    )
await conn.commit()
```

This is idempotent and safe for both fresh and existing DBs. It also matches the codebase's "no migrations framework" reality.

**Option B (formal migration system):** Out of scope for issue #59. Would require touching every other migrate_* method. Not recommended.

## Locked decision sanity-check

The epic body says: "Persist finisher diagnostics (`deferred_questions_json`, `finisher_diagnostics_json`) on `apply_handoffs` via migration." This is fine but **needs to specify the ALTER-TABLE-with-PRAGMA-precheck pattern**, otherwise an implementer might add an unguarded `ALTER TABLE` that fails on second run (since `migrate_apply_schema()` is called every startup via `_ensure_apply_schema_ready()`).

Also: `record_apply_handoff()` at lines 420-513 has an INSERT/UPDATE statement that lists every column by name. **Both new columns need to be added to that statement, including the `ON CONFLICT(apply_run_id) DO UPDATE SET …` branch.** Easy to miss — should be called out in the Phase D acceptance criteria.

## Other migrations to follow as template

There are only three:
- `migrate_review_schema()` — review_runs table.
- `migrate_apply_schema()` — apply_runs + apply_handoffs.
- `migrate_cost_schema()` — referenced in `scripts/process_apply_jobs.py:881`. **The cost schema is the most recent migration and is the closest template for "adding a new table from scratch."** Sub-agent C (cost-tracking) is already auditing this; coordination point.
