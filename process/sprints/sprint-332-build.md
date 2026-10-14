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

r9 § 2 and § 8.1: `build(...)`. Only the task is required: a sentence like "build this thing" works. The sprint card's fields (the files it touches, the files to read first, the card's other sections, or the card in its full markdown form) are optional parameters, and the tool's description tells the calling model in a few sentences what good input looks like and how much a model of each size can take. Whatever arrives is formatted into the card the worker reads. The repository and model fill from the calling session. One run in its own worktree on branch `build/<run id>`, with the role prompt and guidance of its model class, the card as its first message. The report and branch return to the caller. Nothing runs or grades the card.

## observation contract

A scripted build ends `done` with its branch and commit; the repository's own branch does not move; a small model reads the small role; the tool's schema lists the card's fields.
