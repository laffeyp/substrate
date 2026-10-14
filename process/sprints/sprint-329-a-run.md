# Sprint 329 — A run

```yaml
---
id: 329
status: closed
closed_at: 2026-10-14
phase: 4
pass_kind: functional
depends_on: [327, 328]
roadmap: process/planning/ROADMAP-2026-10-14-core-topologies-r3.md
---
```

## scope

A run session (r9 § 3): the topology writes its first message; when its turn ends it writes `ReportWritten` (what the worker said, the files changed, the branch, the commits; outcome `done`, or `failed` on a model error, or `stopped` on an interrupt) and ends. Composed onto the one session topology.

## observation contract

A scripted worker that writes and commits a file ends with a report naming the file, the branch and the commit; a model error ends `failed`; an interrupt ends `stopped`.

## result

- **Built.** `topologies/runs/run.py`: `RunSpec` (worktree, base, first message); `session_topology(run=...)` writes the first message through the session's first-message path with `slash_source` `run`, registers the `report` producer on `report-on-returned`, and finalises on `ReportWritten` or `SessionEnded` instead of pausing for a person. `write_report`: the last reply, the files and commits since the base, the branch (none when detached), and the outcome from the turn's end (replied: done; model error: failed; interrupted: stopped).
- **Tests.** `tests/test_run_session_329.py`, 3: a scripted worker's run ends with one message, its report after `Returned` naming `b.txt`, the branch, one commit and the reply; a failing model ends `failed`; an interrupted turn reports `stopped`, and a detached worktree no branch. The trigger guard builds a run session and finds exactly `report-on-returned` added.
