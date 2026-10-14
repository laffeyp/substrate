# Sprint 319 — The caller's hold

```yaml
---
id: 319
status: open
phase: 1
pass_kind: functional
depends_on: [314, 318]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
---
```

## scope

A run started by a session returns at once; its start and end are written to the caller's record, the end told to the model once, as `BackgroundTaskEnded` is; ending or interrupting the caller ends its runs; the caller's model can stop, pause, resume, step through and replay a run it started (r8 § 3.6).

## observation contract

A session starts a scripted run, takes another turn while it runs, and is told of its end once; stopping it ends it `stopped`; a paused run resumes; stepping returns its events in order; replay of the finished run passes.
