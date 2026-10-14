# Sprint 335 — Vocabulary v0.16: composed topologies

```yaml
---
id: 335
status: closed
closed_at: 2026-10-14
phase: 4
pass_kind: vocabulary
depends_on: []
roadmap: process/planning/ROADMAP-2026-10-14-create-topology.md
---
```

## scope

Research create-topology § 3–§ 5. Session vocabulary § AA: the plan (name, steps, end, max_minutes) and its step fields; the parts `model`, `agent` (as `plain`, `build`, `review`), `command`, `collect`, `split` and each part's event payload; a step's event kind named from its id; the ends `first`, `after`, `quiet` joined by `or`; the `if` tests `is`, `is not`, `has`, `has no`; the plan in a composed run's `RunStarted` baseline (`plan`); the composed run's result on `TopologyRunEnded`; the nine finding codes, each with its fix, and the two strengths, `certain` and `dry_run`; the three tool names, and the four tools they retire. Types in `topologies/compose/vocabulary.py` and `session/`, the exact-set guards updated.

## observation contract

The types encode and decode; the guards list the new members; the document carries v0.16 and its rationale.

## result

- **Ratified** v0.16 § AA in `process/signals/session-vocabulary.md`: the plan and its step fields with their defaults; the five parts and each part's event; the kind named from the step id, and the ids refused (not a word, repeated, `input`, a session or `substrate.` kind); the ends; the plan and input in `RunStarted.baseline`; `TopologyRunEnded.result` (`ComposedResult`) for a composed run, and its outcomes; agent steps as § Z runs of their own; the nine findings and the two strengths; the three tools and the four they retire. Two defaults were added while building K336 and ratified here before commit: a step between a `split` and its `collect` runs up to 50 times, and a `collect` after a split waits for every item (`n all`).
- **Types.** `topologies/compose/vocabulary.py`: `Part`, `AgentAs`, `TestOp`, `EndWhen`, `Finding`, `Strength`, `Test`, `Step` (wire names `with`, `if`, `as`), `End`, `Plan`, `PART_PAYLOAD`, `MAIN_FIELDS`, `INPUT`, the defaults, `kind_of`. `session/`: `ComposedResult` and `TopologyRunEnded.result` (optional, so § Z ends written before v0.16 still decode). `tool_loop/tools.py`: `TOOL_NAME_TOPOLOGY_HELP`, `_PLAN`, `_RUN`.
- **Tests.** `tests/test_compose_vocabulary_335.py`, 4: the closed sets, the kind from the id, the plan's wire names and round trip, a composed end and an old § Z end decoding.
