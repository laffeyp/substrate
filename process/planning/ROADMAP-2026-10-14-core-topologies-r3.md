# ROADMAP: the core topologies, round 3 (the rebuild)

*2026-10-14. From `RESEARCH-2026-10-14-core-topologies-r9.md`. The code of rounds 1 and 2 (kernel K314–K324, app U176–U179) is reverted; their cards and roadmaps stay on disk. A topology takes its input, does the work and reports back; nothing grades it. Kernel cards in `process/sprints/`, app cards in `substrate-ui/process/sprints/`.*

| Card | What | Closes when |
|---|---|---|
| K327 | Vocabulary v0.14: topology runs | the run events of r9 § 7 are ratified with a rationale: run started and ended in the caller's record; the report, pause and resume in the run's; the outcomes done, failed, stopped |
| K328 | Every workspace a repository; worktrees | a session opened on a plain folder finds a repository with one commit; a run gets its own worktree and branch |
| K329 | A run | a session whose first message the topology writes and whose turn's end writes the report (what it said, files, branch, commits) and ends it |
| K330 | The caller holds the run | a run returns at once; its start and end reach the caller's record, the end told once; stop, pause, resume, step and replay; ending the caller ends its runs; the `run` tool |
| K331 | Review | `review(target, styles, focus)`: one read-only reviewer per style in a worktree at the target, one turn, the review back |
| K332 | Build | `build(...)` with a sprint card's fields as its parameters; one session in its own worktree and branch, the card as its first message, the report and branch back |
| K333 | Delegate as a session child | every delegate child a registry session on the caller's model, with the caller as parent |
| K334 | The handoff setting | the `handoff` control beside length and tone, and topology calls per turn read from the record |
| U182 | Panes for runs | a run's start opens its pane beside the caller, view-only; the caller's `/run stop` stops it |
| U183 | Delegate's pane | a delegate child opens an interactive pane beside its caller |
| U184 | The handoff setting in the app | `/handoff` and the bar line |
| U185 | Real observation | a real model in the installed app delegates, reviews a branch and builds a card; the reports return and the panes show the runs |

Then the autonomous build and the swarm (r9 § 8.2, § 8.4).
