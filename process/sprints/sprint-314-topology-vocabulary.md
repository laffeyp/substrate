# Sprint 314 — Vocabulary v0.12: topology runs

```yaml
---
id: 314
status: closed
closed_at: 2026-10-13
phase: 1
pass_kind: architecture
asked: 2026-10-13 (Architect, on round 8: "sounds good, approved. go")
research: process/planning/RESEARCH-2026-10-13-core-topologies-r8.md
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
vocabulary: process/signals/session-vocabulary.md § X
---
```

## scope

The vocabulary session for the topology layer (r8 § 3.9, § 6 card 1): § X of the session vocabulary names the events of a run in its caller's record and in its own, their payloads, the producers and triggers of a driven session, the ordering rules, and the binding of the report; the candidates considered and not adopted, with reasons. Then § X as types in `vocabulary.py` and the session package, with tests written first.

## observation contract

The new kinds, enums, producer kinds and trigger ids are in the vocabulary's sets and `__all__`; every new event encodes and decodes; the exact-set guards fail until the new members are listed, then pass; ruff, mypy --strict and lint-imports are clean.

## result

- **Built.** Session vocabulary v0.12 § X (`process/signals/session-vocabulary.md`): `TopologyRunStarted` and `TopologyRunEnded` in the caller's record; `CardAccepted`, `ChecksRun` and `ReportWritten` in a run session's; the enums `RunOutcome`, `RunRole`, `CardForm`, `CheckKind`; the producers `card`, `checks`, `continue`, `report`; the triggers `checks-on-returned`, `continue-on-checks`, `report-on-checks`, grouped as `DRIVEN_SESSION_TRIGGER_IDS`; the message source `driven`; the end reason `caller_stop`; the order rules; the report's mapping onto the kit's Signal Report; the candidates not adopted, with reasons (§ X.8). In code: the constants, enums, sets and payload parts (`RunSession`, `RunLimits`, `CardCheck`, `CheckResult`) in `vocabulary.py`; the five event Structs in the session package.
- **Tests.** `tests/test_topology_vocabulary_314.py`, 3, red first (the types did not import): the names and their sets; the caller's events and a run's events encode and decode. The exact-set guards failed until the new members were listed: `SessionEndReason` values, the producer kinds, the 23 trigger ids. The event-Struct guard now leaves out Structs defined in the vocabulary module, which holds payload parts and no events. The registered-triggers guard compares an undriven session with the declared triggers less the driven set; K318 extends it to a driven session. 325 kernel session, delegate and language tests pass; ruff, mypy --strict and lint-imports clean; the app's generated kinds are unchanged and its staleness test passes.
