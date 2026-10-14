# Sprint 334 — The handoff setting

```yaml
---
id: 334
status: closed
closed_at: 2026-10-14
phase: 4
pass_kind: functional
depends_on: [327]
roadmap: process/planning/ROADMAP-2026-10-14-core-topologies-r3.md
---
```

## scope

r9 § 9: the `handoff` control (`rare`, `normal`, `eager`) beside length and tone, on the vocabulary first; every list of controls follows the control enum; topology calls per turn read from the record (`substrate handoff <record>`).

## observation contract

As kernel sprint 324's, which this card rebuilds.

## result

- **Re-applied** kernel sprint 324's handoff setting, ratified as v0.15: `Control.HANDOFF`, `HandoffPosition`, `HANDOFF_TEXTS`, `HANDOFF_TOOLS` (from the tool names defined once), `CONTROL_DEFAULTS`; `SESSION_CHANGE_FIELDS` and the rewrite map follow `Control`; the session prompt, `SessionStarted.handoff`, the registry, delegate children (inherited) and the app server carry it; `substrate handoff <record>` counts topology calls per turn. The session and daily CI records were regenerated.
- **Tests.** `tests/test_handoff_control_334.py`, 5, with the length, tone, guidance and next-prompt tests: 30 pass. The live effect stays open, as recorded on app card 179: two models made no topology calls at either position.
