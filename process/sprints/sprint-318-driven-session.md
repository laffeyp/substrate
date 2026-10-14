# Sprint 318 — The driven session

```yaml
---
id: 318
status: open
phase: 1
pass_kind: architecture
depends_on: [314, 316, 317]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
---
```

## scope

Composed onto the one session topology (Decision 2026-10-13): a driven session's turn end runs the checks and then writes the next `UserMessage` or the report, and the run finalises on the report (r8 § 3.5).

## observation contract

A scripted worker whose checks pass ends `done`; one whose checks never pass ends `stuck` within its limits; a failing worker ends `failed`; an undriven session is unchanged (its tests pass as before).
