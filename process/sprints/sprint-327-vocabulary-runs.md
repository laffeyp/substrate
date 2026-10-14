# Sprint 327 — Vocabulary v0.14: topology runs

```yaml
---
id: 327
status: open
phase: 4
pass_kind: vocabulary
depends_on: []
roadmap: process/planning/ROADMAP-2026-10-14-core-topologies-r3.md
---
```

## scope

Propose and ratify the events of research r9 § 7 against the session vocabulary: `TopologyRunStarted` and `TopologyRunEnded` in the caller's record; `ReportWritten`, `RunPaused` and `RunResumed` in a run's record; `RunOutcome` (`done`, `failed`, `stopped`); the run's session as a payload part; `SessionEndReason.caller_stop`. As types in `vocabulary.py`, with the exact-set guards updated.

## observation contract

The kinds encode and decode; the guards list them; the document carries v0.14 and its rationale.
