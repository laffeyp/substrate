# Sprint 318 — The driven session

```yaml
---
id: 318
status: closed
closed_at: 2026-10-13
phase: 1
pass_kind: architecture
depends_on: [314, 316, 317]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
---
```

## scope

Composed onto the one session topology (Decision 2026-10-13): a driven session's turn end runs the checks and then writes the next `UserMessage` or the report, and the run finalises on the report (r8 § 3.5).

## observation contract

A scripted worker whose checks pass ends `done`; one whose checks never pass ends `stuck` within its limits; a failing worker ends `failed`; an undriven session is unchanged (its tests pass as before).

## result

- **Built.** `topologies/runs/driven.py`: `DrivenRun` (the card, the worktree, the base commit, the checks' time limit, the first message), the `driven_checks` view, and `compose_driven`, which registers `card`, `checks`, `continue` and `report` with their triggers on the session topology's builder. `session_topology(driven=...)` composes it and finalises on `ReportWritten` or `SessionEnded` instead of pausing on `Returned`; a driven session refuses a caller's first message. Every decision is read from the record: the latest checks, the commit at each, the latest turn end's reason. The run ends `done` when the checks pass, `stuck` at `max_stops` turn ends or after `stall_stops` in a row with the same commit and checks, `failed` on a model error (with the error), `stopped` on an interrupt.
- **Vocabulary v0.12.2.** `ChecksRun.head`, so a stall is a function of the record; the trigger `card-on-session-prompt` (every session has a session prompt since K299, so the card waits for it as `first_message` does); § X.6 restated: `CardAccepted` precedes the first `UserMessage`, since the session prompt's fragments come first.
- **Tests.** `tests/test_driven_session_318.py`, 4, red first, on a real git worktree with the session's own `write_file` and `bash` tools, scripted: a worker that writes and commits `b.txt` ends `done` after one check, with one file and one commit; a worker that does nothing ends `stuck` after two checks on a stall, its continuation naming the failing command; with no stall limit it ends `stuck` at three turns; a model that raises ends `failed` with the error. The registered-triggers guard now builds a driven session too: the two sessions together register every declared trigger. 460 kernel session, delegate, language, topology and vocabulary tests pass; ruff, mypy --strict and lint-imports clean.
