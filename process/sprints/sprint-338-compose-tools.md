# Sprint 338 — The three tools

```yaml
---
id: 338
status: open
phase: 4
pass_kind: functional
depends_on: [337, 330]
roadmap: process/planning/ROADMAP-2026-10-14-create-topology.md
---
```

## scope

Research § 5, § 6. `topology_help(topic?)` generated from the part table and the shipped plans; `topology_plan(plan | lines | from)` returning `plan_id`, the lines, the wiring, the dry run, the findings, `fixed_plan_id` and `next`; `topology_run(plan_id | name, input?, save?)` starting a run the caller holds (K330's table), its end told once with the end's event, each step's count and the record. Agent steps start through the caller's run table. `save` writes `.substrate/topologies/<name>.json` in the workspace. The shipped plans (build, review, best of n, map and reduce, draft and critique) and the code topologies run by name. The daemon binds the tools to the calling session. `run_topology`, `run_topology_poll`, `list_topologies` and `list_applications` are removed with their daemon routes.

## observation contract

A session with a scripted model plans the draft-and-critique plan, gets the `never_ends` finding, runs the fixed plan by id, and its next step reads the end once; `save` then `topology_run(name)` runs it again; help lists the parts, the shipped plans and the code topologies; the removed tools are gone from the session's tool list.

## result
