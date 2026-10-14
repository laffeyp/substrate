# Sprint 322 — The checking role judges statements

```yaml
---
id: 322
status: closed
closed_at: 2026-10-13
phase: 3
pass_kind: functional
depends_on: [317, 318]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies-r2.md
---
```

## scope

After each turn of a driven run, a card's statement checks are judged by a model call apart from the worker (the checking role, r8 § 3.4): it reads the card and the worktree's diff since the run's base, and answers per statement whether it holds and why. The answer becomes each statement's `CheckResult` (`passed`, `note`); a failed statement fails the checks, so its reason is the worker's next message. The judging call's prompt and reply are on the run's record. Any vocabulary change lands first as a ratified version of § X.

## observation contract

A scripted worker on a card with one command and one statement: a judge that answers "holds" ends the run `done` with the reason in the report; a judge that answers "does not hold" keeps it going with the reason in the next message; a judge reply that does not parse fails the check and says so. A Review run's statement is judged.

## result

- **Vocabulary first.** v0.12.4 ratified in `process/signals/session-vocabulary.md`: `ChecksRun.judge` (`JudgeCall`: model, prompt, reply); a statement's `passed` is the judge's answer and its `note` the reason; `ChecksRun.passed` now requires every statement to hold.
- **Built.** `runs/checks.py`: `statements_of`, `worker_reply` (the worker's last words before the turn end), `worktree_diff` (since the run's base, with new files named, cut at 40,000 characters), `judge_prompt` (the card, the numbered statements, the diff, the reply; one line per statement, "holds" or "does not hold" with a reason), `read_verdicts` (a statement the reply leaves unanswered does not hold, and says so). `run_checks` takes the verdicts and the call. The driven session's checks producer judges in one call of its own when the card has statements, on `DrivenRun.judge` or else the session's own model; a judge that raises fails the statements with its error. A failed statement and its reason go into the worker's next message. Review and Build pass a judge through. The app's checks row counts checks ("1 of 2"), not commands.
- **Tests.** `tests/test_statements_judged_322.py`, 4: a statement that holds ends the run `done` with the reason in the report and the call (model, prompt with the statement and the diff, reply) on `ChecksRun`; one that does not hold keeps the run going with "does not hold (reason)" in the next message and ends `stuck`; a reply that answers nothing fails the statement; verdicts read across markdown, colon and dash forms, the last answer winning. The Review tests now give a judge, and assert the review's statement is judged. Mutation: counting only commands toward `passed` fails 2 of the 4.
