# Sprint 319b — The caller's hold: pause, resume, step, replay

```yaml
---
id: 319b
status: closed
closed_at: 2026-10-13
phase: 1
pass_kind: functional
depends_on: [319]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
---
```

## scope

Split from K319 under the sprint sweet spot (hard rule 6). The caller pauses a driven run (it takes no next turn until resumed; a pause takes effect when the current turn ends, and a stop ends it at once), resumes it, steps through its events in order, and replays a finished run. A pause has to be a fact on the run's record that its `continue-on-checks` trigger reads, so it comes with a vocabulary proposal (§ X.8 left this open "until K319 shows otherwise"). The caller's model reaches these, and K319's stop, through one tool.

## observation contract

A paused run takes no next turn and resumes on request; stepping returns its events in order from a seq; replay of a finished run passes; the tool refuses a run its caller did not start.

## result

- **Built.** Vocabulary v0.12.3: `RunPaused` and `RunResumed` (`by`), and the trigger `continue-on-resumed`. A pause is a fact on the run's record because K319 showed the kernel fails an idle run whose termination says continue (`stuck_quiescent`): with more `RunPaused` than `RunResumed`, `continue-on-checks` holds back, and the driven termination pauses the run when it goes quiet (`pause_await_input`, resumed by `RunResumed`); a run whose checks end it still reports. In `runs/hold.py`: every run is persistent; a run that returns `paused` is held, not reported; `pause`, `resume` (refused unless paused; on a fresh worker thread), `events` (in order from a seq), `replay` (the kernel's level-2 check); and `make_run_tool(owner)`, the caller's `run` tool with `stop`, `pause`, `resume`, `events`, `replay`, which refuses a run another session started.
- **Tests.** `tests/test_pause_step_replay_319b.py`, 4: a run paused at once stops at a `ChecksRun` with no message after it, is held paused and unreported, and on resume runs to its limit of 6 checks and ends `stuck`; resuming a finished run is refused; stepping returns seqs 3–7 from seq 3 and the whole record ends `substrate.RunFinalised`; replay is complete with no mismatches and decisions verified; the tool refuses another session's run and an unknown action, stops its own run, and steps it. Mutation: without the paused guard on `continue-on-checks` the run never pauses and the pause test fails. 527 kernel session-related and record tests pass; ruff, mypy --strict and lint-imports clean.
