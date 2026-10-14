# Sprint 332 — Build

```yaml
---
id: 332
status: closed
closed_at: 2026-10-14
phase: 4
pass_kind: functional
depends_on: [330]
roadmap: process/planning/ROADMAP-2026-10-14-core-topologies-r3.md
---
```

## scope

r9 § 2 and § 8.1: `build(...)`. Only the task is required: a sentence like "build this thing" works. The sprint card's fields (the files it touches, the files to read first, the card's other sections, or the card in its full markdown form) are optional parameters, and the tool's description tells the calling model in a few sentences what good input looks like and how much a model of each size can take. Whatever arrives is formatted into the card the worker reads. The repository and model fill from the calling session. One run in its own worktree on branch `build/<run id>`, with the role prompt and guidance of its model class, the card as its first message. The report and branch return to the caller. Nothing runs or grades the card. The Architect's picture: the tool is a stone shape that directs water; a full card fills every channel, a bare task runs through the main one, and the build works either way.

## observation contract

A scripted build ends `done` with its branch and commit; the repository's own branch does not move; a small model reads the small role; the tool's schema lists the card's fields.

## result

- **Built.** `topologies/runs/build.py`: `build(task, files?, read_first?, notes?, card?, card_file?)`; only `task` is required, a bare string is the task, and `card_file` reads a whole card from the workspace (refused outside it). The tool's description is written to the calling model: give the task in a sentence or two, name the files and the files to read first when known, keep it to what one builder can do (one or two files for a small model). The tool fills in the repository, model and branch. `start_build` makes a worktree on `build/<run id>` and starts one run session (K329) held by the caller (K330), with the role prompt and guidance of its model class, no memory or parent context, and the card laid out as its first message from whatever was given. The report and branch return; nothing merges, refuses for size, runs or grades the card.
- **Tests.** `tests/test_build_332.py`, 3: a bare task builds on its branch, reports `b.txt`, the branch and one commit, leaves the repository unmoved, reads the `default` role and no memory index although one exists; every field given reaches the builder, and a small model reads `default-small`; the tool takes a task alone, a bare string or a card file, and requires only `task`.
