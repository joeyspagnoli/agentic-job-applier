# Spec Checklist

## Preflight
- [x] spec-maker bootstrap completed
- [x] inventory-preview captured and stored in run metadata
- [x] estimate-tokens plan generated
- [x] explore workers queued and launched
- [x] worker findings collected from `.aqa/runs/<latest>/workers/*/findings.md`

## Codebase Structure Analysis
- [x] Packages/modules/components identified
- [x] File organization and architectural patterns captured
- [x] Supported/unsupported languages documented
- [x] Technology stack and dependencies documented
- [x] Hierarchical Mermaid map of codebase structure created
- [x] Key interfaces/APIs/integration points identified
- [x] Design principles/patterns documented
- [x] `codebase_info.md` written

## Documentation Files
- [x] `index.md` includes explicit usage guidance for AI assistants
- [x] `index.md` contains rich metadata about each file's purpose and content
- [x] `index.md` includes a TOC with descriptive summaries for each document
- [x] `index.md` explains relationships between documentation files
- [x] `index.md` guides which files to consult for specific question types
- [x] `index.md` includes brief per-file summaries to assess relevance
- [x] `index.md` positioned as the primary AI entrypoint
- [x] `architecture.md` documents system architecture and design patterns
- [x] `architecture.md` includes Mermaid diagrams where required by the SOP
- [x] `components.md` documents major components and responsibilities
- [x] `components.md` includes Mermaid diagrams where required by the SOP
- [x] `interfaces.md` documents APIs, interfaces, and integration points
- [x] `interfaces.md` includes Mermaid diagrams where required by the SOP
- [x] `data_models.md` documents data structures and models
- [x] `data_models.md` includes Mermaid diagrams where required by the SOP
- [x] `workflows.md` documents key processes and workflows
- [x] `workflows.md` includes Mermaid diagrams where required by the SOP
- [x] `dependencies.md` documents external dependencies and their usage
- [x] `dependencies.md` includes Mermaid diagrams where required by the SOP
- [x] All diagrams use Mermaid (no ASCII art)
- [x] `spec.md` written as cohesive synthesis (exec summary first + TOC near top)

## Review
- [x] Consistency check completed (enabled)
- [x] Completeness check completed (enabled)
- [x] Language-support gaps explicitly called out
- [x] `review_notes.md` updated with gaps + recommendations

## Consolidation (Reserved)
- [x] Consolidation not requested; reserved path intentionally skipped

## Artifacts & metadata
- [x] `.aqa/spec/spec.pdf` generated from `spec.md`
- [x] `.aqa/spec/metadata.json` refreshed with current `generatedAt`
- [x] `.aqa/spec/.last_commit` recorded from current git HEAD

## Summary & Next Steps
- [x] Final summary prepared with assumptions/gaps
- [x] `index.md` usage instructions + example queries included
