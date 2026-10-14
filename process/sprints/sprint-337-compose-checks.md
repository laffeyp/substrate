# Sprint 337 — The plan's checks

```yaml
---
id: 337
status: open
phase: 4
pass_kind: functional
depends_on: [336]
roadmap: process/planning/ROADMAP-2026-10-14-create-topology.md
---
```

## scope

Research § 5. `check.py`: the static findings (`bad_id`, `unknown_part`, `unknown_field` with the nearest field, `missing_role`, `never_starts`, `no_limit`, `unread`, `never_ends` when the end names a kind no step emits) from the plan and `TopologyBuilder.build()`; the dry run, a real `Runtime` on a temporary record with stand-in answers, once as written and once more with every `if` failing when the plan has one, giving numbered lines and how it ended (`never_ends`, `ends_early`); each finding names the step, the problem, the fix and its strength; a plan whose findings all have certain fixes gets the fixed plan, checked again.

## observation contract

A plan built to cause each finding code gets that finding and its fix; the draft-and-critique plan of research § 4 without `or quiet` gets `never_ends` on the failing pass and the fixed plan, which comes back with no findings; the dry run's lines name each step in the order it ran.

## result
