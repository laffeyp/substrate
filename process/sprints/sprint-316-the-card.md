# Sprint 316 — The card

```yaml
---
id: 316
status: closed
closed_at: 2026-10-13
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

## result

- **Built.** `topologies/runs/card.py`: `read_card` (a person's fields: what, where, commands, statements) and `read_sdd_card` (the kit's sprint-card markdown: scope; context, created and modified files; command exit codes; content assertions; the observation contract's expected items) return a `CardAccepted`; `CardRefused` names each of what to do, where, and how to tell it is done that a card lacks. The limits are the caller's to give; the build's form sets them (K321). The kernel working agreement's canonical-home registry gains `topologies/workspace.py` and `topologies/runs/`.
- **Vocabulary v0.12.1.** The kit's own example card 003 expects a command to return 2 and another 1; `CardCheck` had no field for it. `CardCheck.expect_exit` (0 unless the card names another), a `PAYLOAD_FIELD_PROPOSED`, additive.
- **Tests.** `tests/test_card_316.py`, 6, red first (the module did not exist), with the kit's example cards 002 and 003 copied as fixtures: a plain card reads and round-trips; each missing part is refused by name; the kit's cards read, with their commands and expected codes (0, 2, 1); an SDD card without a scope is refused. ruff, mypy --strict and lint-imports clean.
