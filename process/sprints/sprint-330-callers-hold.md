# Sprint 330 — The caller holds the run

```yaml
---
id: 330
status: open
phase: 4
pass_kind: functional
depends_on: [329]
roadmap: process/planning/ROADMAP-2026-10-14-core-topologies-r3.md
---
```

## scope

r9 § 4: a run started by a session returns at once; `TopologyRunStarted` lands in the caller's record when it starts and `TopologyRunEnded` before the caller's next model step, told once; the caller can stop, pause, resume, step through and replay it; ending the caller ends its runs; the caller's `run` tool; the runs listing the app reads.

## observation contract

A scripted run returns at once, its start and end in the caller's record, the end once; stop ends it `stopped`; pause holds it and resume finishes it; step returns its events in order; replay verifies its record.
