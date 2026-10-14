# Sprint 327 — Vocabulary v0.14: topology runs

```yaml
---
id: 327
status: closed
closed_at: 2026-10-14
phase: 4
pass_kind: vocabulary
depends_on: []
roadmap: process/planning/ROADMAP-2026-10-14-core-topologies-r3.md
---
```

## scope

Propose and ratify the events of research r9 § 7 against the session vocabulary: `TopologyRunStarted` and `TopologyRunEnded` in the caller's record; `ReportWritten` in a run's record; `RunOutcome` (`done`, `failed`, `stopped`); the run's session as a payload part; `SessionEndReason.caller_stop`. As types in `vocabulary.py`, with the exact-set guards updated.

## observation contract

The kinds encode and decode; the guards list them; the document carries v0.14 and its rationale.

## result

- **Ratified** v0.14 § Z in `process/signals/session-vocabulary.md`. Pause and resume are not proposed: a run here is one turn, so there is no point between turns to pause at; they come with the autonomous build, which has many. The run's first message uses the session's existing first-message path, marked `slash_source` `run`.
- **Types.** `vocabulary.py`: `TOPOLOGY_RUN_STARTED`, `TOPOLOGY_RUN_ENDED`, `REPORT_WRITTEN`, `RunOutcome`, `RunRole`, `RunSession`, `SessionEndReason.CALLER_STOP`, `PRODUCER_KIND_REPORT`, `TRIGGER_ID_REPORT_ON_RETURNED`, `RUN_SESSION_TRIGGER_IDS`, `RUN_SLASH_SOURCE`. `session/__init__.py`: `ReportWritten`, `TopologyRunStarted`, `TopologyRunEnded`.
- **Tests.** `tests/test_run_vocabulary_327.py`, 2; the exact-set guards (session kinds, end reasons, producer kinds, trigger ids, registered triggers) list the new members.
