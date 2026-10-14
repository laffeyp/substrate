# Sprint 316 — The card

```yaml
---
id: 316
status: open
phase: 1
pass_kind: functional
depends_on: [314]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
---
```

## scope

A card in plain form (what to do, where, how to tell it is done) or the full SDD sprint-card form is read into a `CardAccepted` event; a card lacking any of the three is refused, naming what is missing (r8 § 3.2).

## observation contract

The kit's example cards (`sdd-kit-3/example/sprints/`) and a three-line plain card both read; each missing part is refused by name; the event round-trips.
