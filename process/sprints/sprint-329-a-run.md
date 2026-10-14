# Sprint 329 — A run

```yaml
---
id: 329
status: open
phase: 4
pass_kind: functional
depends_on: [327, 328]
roadmap: process/planning/ROADMAP-2026-10-14-core-topologies-r3.md
---
```

## scope

A run session (r9 § 3): the topology writes its first message; when its turn ends it writes `ReportWritten` (what the worker said, the files changed, the branch, the commits; outcome `done`, or `failed` on a model error, or `stopped` on an interrupt) and ends. Composed onto the one session topology.

## observation contract

A scripted worker that writes and commits a file ends with a report naming the file, the branch and the commit; a model error ends `failed`; an interrupt ends `stopped`.
