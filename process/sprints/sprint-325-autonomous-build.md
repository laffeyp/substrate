# Sprint 325 — Autonomous build

```yaml
---
id: 325
status: open
phase: 3
pass_kind: functional
depends_on: [321, 322]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies-r2.md
---
```

## scope

The 2026-09-24 note's 11 points as r8 § 4.2 sets them: a roadmap and its cards run card after card by one builder session in a worktree; every time the builder would return to a person a fixed reply is written instead (resolve and record); every n-th return goes to a standing reviewer, whose report returns to the builder with "analyze, verify, apply"; it ends when the last card closes or progress stops by a measure; SDD kit 3 is in the builder's and reviewer's prompts; it runs from a session or on its own. Composed onto the session topology. Its sessions are view-only.

## observation contract

A scripted builder and reviewer on a roadmap of three cards: each card's checks pass in order; the fixed reply appears at each return but the n-th, where the reviewer's report does; the run ends `done` with a report per card; a builder that makes no progress ends `stuck` by the measure.
