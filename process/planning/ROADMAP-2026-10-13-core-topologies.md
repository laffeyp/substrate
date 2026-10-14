# ROADMAP: the core topologies

*2026-10-13. From `process/planning/RESEARCH-2026-10-13-core-topologies-r8.md` (approved by the Architect, 2026-10-13: "sounds good, approved. go"), § 6. Kernel cards K314–K321 in `process/sprints/`; app cards U176–U177 in `substrate-ui/process/sprints/`. Each card closes against its own checks.*

| Card | What | Closes when |
|---|---|---|
| K314 | Vocabulary v0.12 § X: topology runs | § X ratified with its rationale; the kinds, enums, producers and triggers exist as types; the events encode and decode; the vocabulary's exact-set guards list them |
| K315 | Every workspace a repository; worktrees from the kernel | a session opened on a plain folder finds a repository with one commit; a run gets its own worktree and branch from the registry |
| K316 | The card | a card in plain form or the full SDD form is read into `CardAccepted`; a card lacking what to do, where, or how to tell it is done is refused naming the gap |
| K317 | The checks and the report | command checks run in the worktree with the gate's core; the run's events are checked against the vocabulary; `ChecksRun` and `ReportWritten` are written from them |
| K318 | The driven session | a session whose topology writes its next message: checks on each `Returned`, then the next message or the report; ends `done`, `stuck` or `failed` on a scripted worker |
| K319 | The caller's hold | a run returns at once; its start and end are in the caller's record; the end is told once; the caller can stop, pause, resume, step and replay it |
| U176 | Panes for runs | a run's start opens its pane; view-only when the topology writes the next message; the caller's row stops and focuses it |
| K320 | Review | a one-shot run reviews a branch in a named style and returns its report; styles picked from published review practice |
| K321 | Build | one card worked in its own worktree until its checks pass; its report and branch returned |
| U177 | Real observation | a real model calls Review on a real branch and Build on a real card in a real repository; reports return, the build's checks pass, the panes show both runs |

Then: delegate as a session child, the autonomous build, the swarm, best-of-N on the same machinery, the topologies setting, and the later shapes (r8 § 4.7).
