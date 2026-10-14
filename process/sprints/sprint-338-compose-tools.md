# Sprint 338 — The three tools

```yaml
---
id: 338
status: closed
closed_at: 2026-10-14
phase: 4
pass_kind: functional
depends_on: [337, 330]
roadmap: process/planning/ROADMAP-2026-10-14-create-topology.md
---
```

## scope

Research § 5, § 6. `topology_help(topic?)` generated from the part table and the shipped plans; `topology_plan(plan | lines | from)` returning `plan_id`, the lines, the wiring, the dry run, the findings, `fixed_plan_id` and `next`; `topology_run(plan_id | name, input?, save?)` starting a run the caller holds (K330's table), its end told once with the end's event, each step's count and the record. Agent steps start through the caller's run table. `save` writes `.substrate/topologies/<name>.json` in the workspace. The shipped plans (build, review, best of n, map and reduce, draft and critique). A composed run's stop is a `RunStopRequested` in its record (v0.16.1), from its caller or when `max_minutes` passes. The daemon binds the tools to the calling session; `run_topology`, `run_topology_poll`, `list_topologies` and `list_applications` leave the app's session tools and stay in the kernel for the CLI.

## observation contract

A session with a scripted model plans the draft-and-critique plan, gets the `never_ends` finding, runs the fixed plan by id, and its next step reads the end once; `save` then `topology_run(name)` runs it again; help lists the parts and the shipped and saved plans; a stopped run ends `stopped`; the four older tools are gone from an app session's tools.

## result

- **Built.** `compose/tools.py`: `topology_help(topic?)`, generated from the part table, the field list and the plans there are, or one part or plan; `topology_plan(lines | plan | from, input?)`, returning the plan id (a hash of the plan, so the same plan has the same id), the lines, the wiring, the dry run, the findings as lines, a `fixed_plan_id` with its lines when there is one, and `next`; `from` lays changed lines over a named plan, a step with the same id replacing its own; `topology_run(plan_id | name, input?, save?)`, `save` writing `.substrate/topologies/<name>.json` in the workspace. Six shipped plans in `compose/plans/`: `build`, `review`, `build_and_review`, `best_of_n`, `map_reduce`, `draft_and_critique`, each with no findings. `compose/run.py`: `start_composed` starts the run through the caller's run table and stops it when `max_minutes` passes; `agent_starter` starts an agent step as a build or a review the caller holds, waits on it (`RunTable.wait`) and returns its report. `runs/hold.py`: a held run carries its plan; stopping a composed run injects `RunStopRequested`; its end reads which end held, its event (the last step's when it went quiet) and each step's count, and its notice says so in a line. A collect's items read as a numbered list in a prompt.
- **Daemon** (`substrate-ui/server.py`): the three tools join every session's tools, bound to the session; model steps run on the session's model or the step's; agent steps start the session's own builds and reviews (`_start_build` and `_start_review` take an optional model); `run_topology`, `run_topology_poll`, `list_topologies` and `list_applications` leave a session's tools and stay in the kernel for the CLI (vocabulary v0.16.1).
- **Found and fixed.** A stopped run left its running command alive: cancelling the step did not end the child process. A command now runs in its own process group, killed on a stop or a time-out; the test reads the command's pid and checks it is gone, and fails with the kill removed.
- **Tests.** `tests/test_compose_tools_338.py`, 5: a scripted caller session plans the draft-and-critique plan, gets `never_ends` and the fixed plan id, runs it, and its next step is told the end once (ended on `Fix`, each step's count); `save` then a run by name, with help listing the parts, the shipped plans and the saved one; `from` a named plan with a changed end; a stopped run ends `stopped` and its command is gone; an agent step builds on a real branch, the repository's own branch unmoved. App: `tests/test_session_tool_suite_composition_228.py` asserts the three in and the four out. The run-table, build, review and vocabulary tests pass (58).
