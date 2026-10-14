# Sprint 336 — Parts and plans

```yaml
---
id: 336
status: withdrawn
closed_at: 2026-10-14
phase: 4
pass_kind: functional
depends_on: [335]
roadmap: process/planning/ROADMAP-2026-10-14-create-topology.md
---
```

## scope

Research § 3, § 4, § 6. `topologies/compose/`: `plan.py` reads a plan from JSON or from lines, fills every default (`on` the step before, `max` 1, ends `quiet`, `max_minutes` 30, the kind from the id) and writes it back as lines; `parts.py` holds the five parts (fields, payload struct, producer); `wire.py` turns a plan into `TopologyBuilder` calls with event classes made from the step ids. Model steps call a `Responder` the caller supplies; agent steps call a starter the caller supplies (the daemon binds the run table in K338); command steps run in a directory the caller supplies.

## observation contract

A plan in JSON and the same plan in lines build the same topology; every default shows in the lines read back; each part runs in a real `Runtime` with stand-in model and agent starters and emits its payload; a model step reads its role and its input laid out from `with`.

## result

- **Built.** `compose/plan.py`: `read` takes JSON, lines or a mapping, fills every default (the first step on `input`, each later step on the kind before it, `max` 1, the fan-out defaults, a step with no part is a model step) and reports what it cannot read as findings with fixes; a field a part does not take is reported and dropped; `lines` writes the plan back, the quoted text being a model or agent step's role and a command step's command. `compose/parts.py`: the five producers over a `Deps` (a model per name, an agent starter, a directory). `compose/wire.py`: one producer kind per step, one trigger per kind waited on, `max` counted from `TriggerFired` (exact, because the kernel drains each firing before the next event's cycle), `if` tested on the starting event or the latest of its kind, inputs laid out from `with` and the placeholders, collects gathered in order, the plan and input into `RunStarted.baseline`.
- **Found.** The kernel consults termination with a cycle's last event, which is a `TriggerFired` whenever a trigger waits on the terminal kind, so `finalise_on(K)` misses `K` there; its docstring says it finalises "when the event just appended is of kind". `first K` is therefore `threshold_count(K, 1)`. The kernel recipe is unchanged.
- **Tests.** `tests/test_compose_parts_plans_336.py`, 7: JSON and lines are one plan and register the same topology, with every default in the lines; a model step reads its role and its input with `with`; an `if` that fails stops the loop and `quiet` ends the run; placeholders; split, command and collect `all`; a failing command; an agent step through its starter.

- **Withdrawn (2026-10-14).** The Architect: "undo all those changes and zero them out." Everything this card built is removed from the code; the kernel's `src/` and `tests/` match `a76adace` but for K339. See `process/planning/POSTMORTEM-2026-10-14-create-topology-without-substrate-r2.md`.
