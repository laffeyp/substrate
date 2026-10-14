# Sprint 331 — Review

```yaml
---
id: 331
status: open
phase: 4
pass_kind: functional
depends_on: [330]
roadmap: process/planning/ROADMAP-2026-10-14-core-topologies-r3.md
---
```

## scope

r9 § 8.3: `review(target, styles, focus)`. One reviewer per style (defects, design, security; the style texts and their sources from round 1 are reused), each a run in a worktree detached at the target, read-only tools, one turn, its reply the review.

## observation contract

Two styles give two runs, each with its review in its report and its worktree at the target; the caller's record holds both ends.
