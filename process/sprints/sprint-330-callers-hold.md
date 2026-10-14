# Sprint 330 — The caller holds the run

```yaml
---
id: 330
status: closed
closed_at: 2026-10-14
phase: 4
pass_kind: functional
depends_on: [329]
roadmap: process/planning/ROADMAP-2026-10-14-core-topologies-r3.md
---
```

## scope

r9 § 4: a run started by a session returns at once; `TopologyRunStarted` lands in the caller's record when it starts and `TopologyRunEnded` before the caller's next model step, told once; the caller can stop, step through and replay it; ending the caller ends its runs; the caller's `run` tool; the runs listing the app reads.

## observation contract

A scripted run returns at once, its start and end in the caller's record, the end once; stop ends it `stopped`; step returns its events in order; replay verifies its record.

## result

- **Built.** `topologies/runs/hold.py` (from kernel sprints 319 and 319b, without pause, resume or checks): `RunTable` starts a run on its own loop in a worker thread and returns at once, posting `TopologyRunStarted` into the caller's record at the `ToolCall` that started it; `drain_ended` gives each ended run once, read from its record (its report, or `stopped` when its caller stopped it, else `failed`); `stop` asks the run's session to end `caller_stop`; `stop_owner`; `events` from a seq; `replay` (the kernel's level-2 check); `listing` for the app. The caller's model step writes `TopologyRunEnded` and tells the model its reply, up to 4,000 characters. The registry ends a session's runs with it. `run(run_id, action=stop|events|replay)` is the caller's tool. Tool names `TOOL_NAME_RUN`, `TOOL_NAME_REVIEW`, `TOOL_NAME_BUILD` are defined once in `tool_loop/tools.py`. The session and daily CI records were regenerated for the model step's new schema; the other 16 were restored.
- **Tests.** `tests/test_callers_hold_330.py`, 4: a run returns at once and its end is told once, with the notice; the caller stops a run (`caller_stop`) and ending the caller stops its runs; stepping, replay, the listing, and refusals of another session's run and of `pause`; a caller session records the start at its tool call and the end at its next step, once.
