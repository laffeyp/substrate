# Sprint 321 — Build

```yaml
---
id: 321
status: open
phase: 2
pass_kind: functional
depends_on: [315, 316, 317, 318, 319]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
---
```

## scope

One card worked in its own worktree by a driven session until its checks pass or it cannot close; its report and branch returned to the caller; the build never merges (r8 § 4.1).

## observation contract

A deterministic build on a fixture repository ends `done` with its branch, commits and report; a card whose check cannot pass ends `stuck`.
