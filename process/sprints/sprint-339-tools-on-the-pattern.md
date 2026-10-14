# Sprint 339 — The built tools on the pattern

```yaml
---
id: 339
status: closed
closed_at: 2026-10-14
phase: 4
pass_kind: functional
depends_on: [338]
roadmap: process/planning/ROADMAP-2026-10-14-create-topology.md
---
```

## scope

Research § 7. `build`'s and `review`'s results say the report arrives when the run ends and how to watch or stop it; the end notice of a build names the diff command, `review(target=<branch>)` and the merge command; a review's ends with what to do with a finding; `run`'s description says what each action returns, an unknown run id lists the session's run ids, and `events` says how to read the next page; `delegate`'s description says when a child session suits better than `build`.

## observation contract

Each tool's result and notice carry their next moves as the card states; an unknown run id's error lists the ids.

## result

- **Built.** `build` and `review` return `next` with their results: the report comes to the caller once, when the run finishes; `run(…, 'events')` shows progress and `run(…, 'stop')` stops it (`runs/build.py` `started_next`, which names each run when there are several). A build's end notice names its branch's moves: `git diff HEAD...<branch>`, `review(target=<branch>)`, `git merge <branch>`; a review's tells the caller what to do with each finding. `run`'s description says what `stop`, `events` and `replay` return; an unknown run id's error lists the session's run ids; `events` that fill their `limit` say the `from_seq` of the next page. `delegate`'s description says to use `build` for a change wanted on its own branch.
- **Vocabulary v0.16.1, § AA.4:** an agent step's run is the caller's own build or review, so its `topology` is `build` or `review`, not `<plan>/<step>` as v0.16 said.
- **Tests.** `tests/test_tools_on_the_pattern_339.py`, 4: the start texts for one build and two reviewers; a build's and a review's end notice, and none for a failed run; the run tool's description and its miss listing; delegate's line. The K330–K332 tests that pinned the old result shapes and refusal text now assert the new ones. 32 run, build, review, delegate and compose tests pass; the app's 42 run and tool tests pass.
