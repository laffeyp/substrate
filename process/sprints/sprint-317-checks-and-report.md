# Sprint 317 — The checks and the report

```yaml
---
id: 317
status: closed
closed_at: 2026-10-13
phase: 1
pass_kind: functional
depends_on: [314, 316]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
---
```

## scope

A card's command checks run with the gate's core (`coding_flow/gate.py`) in the run's worktree; the run's own events are checked against the session vocabulary; `ChecksRun` records both; `ReportWritten` is written from the card, the checks and the run (r8 § 3.3, § 3.4).

## observation contract

On a fixture repository, a passing and a failing command each record their exit and output; an out-of-vocabulary event in a test record is caught; the report names what was asked, done, checked and left.

## result

- **Built.** `topologies/runs/checks.py`: `run_checks` runs each command check in the worktree, passing when the exit equals the card's `expect_exit`, failing with a note when it times out; leaves statement checks unrun (`passed` null, "judged by a reviewer", K320); runs `check_record`; `ChecksRun.passed` when every command passed and the record has no problems. `check_record` finds kinds outside the session vocabulary and the tool loop's, `CardAccepted` not first, a `ChecksRun` with no `Returned` before it, `ReportWritten` more than once or followed by anything but `SessionEnded`. `write_report` writes `ReportWritten` from the card, the worker's last words, the last checks, and the worktree's files, branch and commits since the base.
- **The gate's core, shared.** `coding_flow.gate.run_command(command, cwd, timeout, env, label)` holds the process-group run, the timeout kill, the missing-tool case and the normalising; `run_gate` calls it with its own environment (the interpreter's scripts first on `PATH`), and a run's checks call it with the user's.
- **Tests.** `tests/test_checks_and_report_317.py`, 4, red first (the module did not exist): commands pass and fail by their expected exit (0, 1, and 2 expected and got); a 30-second command stopped at 0.5 s fails with a note; the record check finds an unknown kind and three order breaks, and passes a good record; the report names what was asked, done, the one file and one commit. 167 coding_flow and gate tests pass on the shared core; ruff, mypy --strict and lint-imports clean.
