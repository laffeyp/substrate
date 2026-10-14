# Sprint 326 — Swarm

```yaml
---
id: 326
status: open
phase: 3
pass_kind: functional
depends_on: [321, 322]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies-r2.md
---
```

## scope

Cards that touch different files run in parallel as builds, each on its own branch (r8 § 4.4). The topology works out which cards can run together from the cards' files; shared files go first in a Wave 0 card; each wave ends in an integration card on a branch that merges the wave's branches and asserts the wave works end to end. A report per card and one for the integration. One run with several sessions.

## observation contract

Scripted workers on two disjoint cards and one that shares a file: the shared one waits for its wave; the two run at once; the integration card's checks pass on the merged branch; a merge conflict ends the integration `stuck` with the conflict in its report.
