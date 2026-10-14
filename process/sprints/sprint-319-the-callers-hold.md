# Sprint 319 — The caller's hold

```yaml
---
id: 319
status: closed
closed_at: 2026-10-13
phase: 1
pass_kind: functional
depends_on: [314, 318]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
---
```

## scope

A run started by a session returns at once; its start is written to the caller's record when it starts, and its end before the caller's next model step, told to the model once, as `BackgroundTaskEnded` is; the caller can stop a run it started; ending the caller stops its runs (r8 § 3.6). Pause, resume, step, replay and the caller's tool are split into K319b under the sprint sweet spot.

## observation contract

A scripted run started from a session returns at once and writes its start into the caller's record; its end is written at the caller's next model step, once; stopping it ends it `stopped` with `SessionEnded` `caller_stop` in its record; ending the caller stops it.

## result

- **Built.** `topologies/runs/hold.py`: `RunTable` holds each session's runs. `start` runs a run on its own event loop in a worker thread and returns at once; from inside the caller's tool it posts `TopologyRunStarted` into the caller's record then, with the seq of the `ToolCall` that started it (the tool's call id from `_BASH_PROGRESS_CTX`, as tool progress does). `stop` injects `SessionEndRequested` with source `caller_stop` into the run, whose `end-on-end-request` now maps that source to the reason `caller_stop`. `stop_owner` stops a session's runs; the registry calls it when a session ends, beside the background tasks. `drain_ended` gives each ended run once, as a `TopologyRunEnded` read from its record: its report and outcome, `stopped` when its caller stopped it, `failed` otherwise. The caller's model step writes it and tells the model (`run_notice`), as it does `BackgroundTaskEnded`; the model producer's schemas list it. A run id is held once; a second start with it is refused.
- **Split.** Pause, resume, step, replay and the caller's tool are K319b (`process/sprints/sprint-319b-pause-step-replay.md`), under the sprint sweet spot.
- **The committed CI records** for `session` and `daily` are regenerated: their `RunStarted` lists the model producer's schemas, which now include `TopologyRunEnded`. The script rewrote all 18 bundled records; the other 16 were restored, and all 44 record tests pass.
- **Tests.** `tests/test_callers_hold_319.py`, 5, red first: a run returns in under 2 s, ends `done` with its report, and is told once; the caller stops a run mid-command (`sleep 30`) and it ends `stopped`, with `SessionEnded` `caller_stop` in its record and no `sleep` left running; ending the caller stops its run; a caller session's record holds the run's start at its `ToolCall`'s seq and its end after the next message, once; a run id is held once. 515 kernel session, delegate, language, topology, vocabulary, background and record tests pass; ruff, mypy --strict and lint-imports clean.
