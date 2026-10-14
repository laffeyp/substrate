# Sprint 317 — The checks and the report

```yaml
---
id: 317
status: open
phase: 1
pass_kind: functional
depends_on: [314, 316]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
---
```

## scope

A card's command checks run with the gate's core (`coding_flow/gate.py`) in the run's worktree; the run's own events are checked against the session vocabulary; `ChecksRun` records both; `ReportWritten` is written from the card, the checks and the run (r8 § 3.3, § 3.4).

## observation contract

On a fixture repository, a passing and a failing command each record their exit and output; an out-of-vocabulary event in a test record is caught; the report names what was asked, done, checked and left.
