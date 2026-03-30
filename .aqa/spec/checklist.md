# Spec Checklist

## Incremental Update Preflight
- [x] Existing spec read from .aqa/spec/index.md before any rewrite planning begins.
- [x] Linked spec docs from index.md inspected to understand current structure and prior coverage.
- [x] spec-maker bootstrap completed for update mode.
- [x] checklist.md confirmed reset to the canonical incremental-update template before synthesis.
- [x] spec-maker collect_update_context completed.
- [x] update strategy inspected and recorded (incremental / metadata_refresh / full_regen).
- [x] history source recorded (gh when authenticated and useful, otherwise git fallback).
- [x] baseline commit from .aqa/spec/.last_commit validated against current HEAD.

## Change Scope
- [x] Changed commits summarized from the stored .last_commit baseline to current HEAD.
- [x] Changed files collected from repo history for the selected update strategy.
- [x] Related PR metadata captured when gh compare/commit lookups succeeded.
- [x] Fallback warnings noted when gh auth, remote detection, or PR lookups were unavailable.
- [x] inventory-preview run with include_paths for the exact changed files when incremental mode is valid.
- [x] estimate-tokens run with include_paths so worker planning stays scoped to changed code only.
- [x] Worker scopes limited to changed files or changed areas rather than broad repo regeneration.
- [x] Impacted spec docs identified from existing citations, path mentions, or explicit file references.
- [x] Unmapped changed files called out for follow-up if no existing doc clearly covers them.

## Deterministic Artifacts
- [x] checklist.md reset for update mode by bootstrap and treated as fresh state for this run.
- [x] metadata.json refreshed with the new generation timestamp once the update completes.
- [x] .last_commit refreshed to the final HEAD used for the update.
- [x] Prior review_notes.md read before regeneration so still-relevant notes can be preserved.

## Impacted Documentation
- [x] index.md kept as the AI entrypoint and updated only if routing guidance or TOC accuracy changed.
- [x] architecture.md updated only if system design, patterns, or boundaries changed in the touched code.
- [x] components.md updated only if component responsibilities, ownership, or package structure changed.
- [x] interfaces.md updated only if APIs, contracts, or integration points changed.
- [x] data_models.md updated only if persisted shapes, schemas, or core structures changed.
- [x] workflows.md updated only if runtime flows, control paths, or operator procedures changed.
- [x] dependencies.md updated only if libraries, external services, or dependency usage changed.
- [x] codebase_info.md updated only if repo layout, supported tech, or high-level structure changed.
- [x] review_notes.md regenerated with still-relevant prior notes carried forward and resolved notes removed.
- [x] Untouched spec docs verified byte-identical after the incremental rewrite pass (no untouched core spec docs remained in this run).

## Review
- [x] Changed docs cross-checked against worker findings and collected repo history before finalizing.
- [x] Consistency follow-up recorded if enabled.
- [x] Completeness follow-up recorded if enabled.
- [x] Fallback warnings, PR lookup gaps, or unmapped drift recorded in review_notes.md.
- [x] Incremental update confirmed to avoid accidental full-spec rewrites unless full_regen was required.

## Summary & Next Steps
- [x] Incremental update summary provided.
- [x] Changed commits, changed files, and updated docs listed in the final summary.
- [x] Any docs intentionally left untouched are called out when that matters for operator context.
- [x] Manual follow-up areas listed if history gaps, unmapped files, or blocked review work remain.
