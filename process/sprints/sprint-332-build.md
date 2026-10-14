# Sprint 332 — Build

```yaml
---
id: 332
status: open
phase: 4
pass_kind: functional
depends_on: [330]
roadmap: process/planning/ROADMAP-2026-10-14-core-topologies-r3.md
---
```

## scope

r9 § 2 and § 8.1: `build(...)`, whose parameters are a sprint card's fields from the kit's template (what to do and the files are required by the schema; the files to read first and the card's other sections are optional; or the card in its full markdown form). The repository and model fill from the calling session. One run in its own worktree on branch `build/<run id>`, with the role prompt and guidance of its model class, the card as its first message. The report and branch return to the caller. Nothing runs or grades the card.

## observation contract

A scripted build ends `done` with its branch and commit; the repository's own branch does not move; a small model reads the small role; the tool's schema lists the card's fields.
