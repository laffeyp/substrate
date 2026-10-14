# Sprint 337 — The plan's checks

```yaml
---
id: 337
status: closed
closed_at: 2026-10-14
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

- **Built.** `compose/check.py`: `check(plan)` returns the plan as lines, one wiring line per kind (what writes it, what it starts, what reads it, whether it ends the run), the dry run, the findings and a fixed plan. The static findings come from the wiring (`missing_role`, also for a command with no command; `never_starts`; `unknown_field` for a kind read by `with`, `if` or a placeholder that no step writes; `no_limit` for a step on a loop with `max` 1; `never_ends` for an end on a kind nobody writes; `unread` when a plan ends on a kind and another kind is read by nothing) and from `TopologyBuilder.build()`. The dry run runs the real kernel on stand-in answers: a model step says `<step> answer <n>`, or a text made to pass the `if` tests on its kind; commands are replaced by `echo`, never run; an agent reports done. A plan with an `if` runs a second time with every test failing. It finds `never_ends` (the run went idle with its end unmet) and `ends_early` (a step that ran on neither pass). When every finding's fix is certain (a loop's `max 3`, `or quiet`, a dropped field), the fixed plan is checked again and returned only if it is clean.
- **Lines.** `input` inside an `on` list is the run's input when it comes first or no quoted text follows it, so `on input "role"` reads as written.
- **Tests.** `tests/test_compose_checks_337.py`, 17: each of the nine codes on a plan built to cause it, with its step and fix; the draft-and-critique plan's two passes, its `never_ends` and its checked fixed plan; a loop's fixed `max 3` running three times; no fixed plan where a fix is not certain; a clean plan whose command did not run.
