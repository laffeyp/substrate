# ROADMAP: the core topologies, round 2

*2026-10-13. Follows `ROADMAP-2026-10-13-core-topologies.md` (K314–K321, U176–U177, all closed), which stays as it is. Same research: `RESEARCH-2026-10-13-core-topologies-r8.md` § 3.4, § 4.2, § 4.4, § 4.6, § 5 and the order of § 6. Kernel cards in `process/sprints/`; app cards in `substrate-ui/process/sprints/`.*

## The check before this round

Round 1 built the command half of § 3.4 and not the other. A card's statement checks are recorded "judged by a reviewer" and judged by no one; `run_checks` counts only commands, so a card whose done-condition is a statement ends `done` after one turn. Every Review run so far is such a card. § 3.4 says the checks are run by a role that did not do the work, and the Autonomous Build's standing reviewer (§ 4.2 point 3) is that role. It comes first.

## Cards

| Card | What | Closes when |
|---|---|---|
| K322 | The checking role judges statements | a card's statement checks are judged by a model call apart from the worker, on the worktree's diff and the card; each result says passed or failed and why; a statement that fails keeps the run going; the judging call is on the record |
| K323 | Delegate as a session child | every delegate child is a registry session on the caller's model unless the call names another; the bare tool-loop child and its 6-step cap are gone; a child's answer folds back as today |
| U178 | Delegate's pane | a delegate child opens an interactive pane beside its caller while it works; a person can write to it; it stays after the answer folds back |
| K324 | How readily a session hands work to a topology | a session setting beside length and tone (vocabulary § T or its successor), written into the session prompt, changeable mid-session; topology calls per turn read from the record by setting and model |
| U179 | The setting in the app | the picker's row and `/topologies <level>`; the bar line names it; a live session on two settings shows different call rates in its record |
| K325 | Autonomous build | the 2026-09-24 note's 11 points (§ 4.2): a roadmap and its cards run card after card by one builder; every return gets the fixed reply or, every n-th, the standing reviewer's report with "analyze, verify, apply"; it ends when the last card closes or progress stops; SDD kit 3 in its prompt |
| K326 | Swarm | cards that touch different files run in parallel, after a Wave 0 card for shared files; each wave ends in an integration card; a report per card and one for the integration (§ 4.4) |
| U180 | A run's window | a run with several sessions opens a window of its own with a pane per session (open item 30) |
| U181 | Real observation | a real model runs an autonomous build of three cards and a swarm of two disjoint cards in the installed app; the reports return, every card's checks pass on its branch, the windows show the runs |

Then: best-of-N on the same machinery (§ 4.5) and the shapes of § 4.7 (pair coding, the adversarial reviewer for documents, the discovery arena); then the paper on what Substrate has, and its next step.
