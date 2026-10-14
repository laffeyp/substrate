# RESEARCH: the core topologies (round 9)

*2026-10-14. Round 9 replaces round 8 (`RESEARCH-2026-10-13-core-topologies-r8.md`), which stays on disk. Round 8 put machinery on the topologies that the Architect never asked for: a card had to say how to tell it is done or it was refused; a separate role ran the card's commands and graded the work; a failed grade went back to the worker as its next message, up to a limit; a second model call judged the card's sentences. Round 9 takes all of that out. A topology takes its input, does the work, and reports back. The Architect's words for each shape are quoted where they are used.*

*Sources. The Architect's statements in the 2026-10-13 and 2026-10-14 sessions. The autonomous build note (`substrate-ui/process/methodology/2026-09-24-autonomous-build-topology.md`). The SDD kit 3 (`README.md`, `templates/SPRINT_CARD.md`). The code as built through kernel sprint 324.*

## 1. What a topology is here

A topology is a shape of work a session can start: one or more sessions, an input, an output. Substrate already gives every session a record, a model, tools, a pane, and interrupt and end. A topology composes sessions; it adds no grading of its own. Substrate is also the orchestrator the SDD kit says it leaves to someone else (`README.md`: "Wrap the kit in a thin orchestrator… The discipline (this kit) stays the same; the orchestrator handles the operations").

## 2. The input is a sprint card, through a tool

The Architect: Build "should specify that it takes basically like a sprint card… a function interface for an LLM… forced to fill all these things in by the tool itself… some of them can be auto populated."

So a topology's input is a tool call whose parameters are the fields of a sprint card. The model calling the tool fills them in; the tool's schema is what makes it fill them in. The fields come from the kit's template (`templates/SPRINT_CARD.md`): what to do, the files it touches, the files to read first, and the card's other sections where the caller has them. A card in the kit's full markdown form is accepted as it is. The fields a run needs beyond the card — the repository, the model — fill from the calling session.

The card is what the worker is told. Nothing in Substrate runs the card's contents or grades the work against them.

## 3. The output is a report

A run ends with a report: what the worker said it did, the files it changed, its branch and commits, and how the run ended — done, failed (the model failed), or stopped (its caller stopped it). The caller's model reads it when the run ends.

## 4. The caller holds the run

The Architect: "The caller needs to be able to stop it and have full control over it… frame by frame… with full replay."

A run started by a session belongs to that session. It returns at once; its end is written into the caller's record before the caller's next step, told once. The caller can stop it, pause and resume it, step through its events, and replay it. Ending the caller ends its runs. These are tools for the caller's model and controls for the person.

A run's pane opens when it starts: beside the caller for one session, in a window of its own for several. A pane takes typing when a person writes the session's next message, and is view-only when the topology writes it.

## 5. The worktree is the context

The Architect: "the only context it will have will be whatever Git work tree-like area that we give it… It's only about the input and output."

A run works in a worktree of the caller's repository, on its own branch. Every session's workspace is a git repository: Substrate runs `git init` and a first commit when it is not one (the Architect: "By default, a new session is a Git repo"). The worker gets the role prompt and guidance its model class gets — "build doesn't lose all that shaping" — and no memory index or parent context.

## 6. Card size follows model size

The Architect: high models get a roadmap and its sprint cards; low models get "as much sprint card as they can understand." This is guidance for the session model when it helps the user write cards.

## 7. Vocabulary first, for Substrate's own work

New events are proposed against the session vocabulary and ratified before they are built. The topology layer needs: a run started by a caller, a run ended, a report written, a run paused and resumed, a run stopped by its caller.

## 8. The shapes

### 8.1 Build

The Architect: "You give them one task, they build it. They always work in a Git work tree." **Input:** one sprint card, through the `build` tool. **Work:** one session in its own worktree and branch, given the card as its first message; it works the card to the end of its turn. **Output:** the report and the branch. **Pane:** view-only. The build does not merge; the caller reads the branch and decides.

### 8.2 Autonomous build

The 2026-09-24 note, point by point:

1. **Input** — a roadmap, its sprint cards, and a prompt with a fixed part (general best practice) and a project part.
2. **The automatic reply** — every time the builder would return to a person, a fixed reply is written instead.
3. **The review** — every n-th return goes to a standing reviewer instead, opened with the builder. Its review returns to the topology, which appends "analyze, verify, apply" and sends it to the builder.
4. **Callers** — normally started from a session once the roadmap and cards are made with the user.
5. **The review corrects drift** — against the roadmap, the original intent and cards, SDD, best practice and the project's conventions.
6. **The reviewer may propose** new cards, changed cards or a new roadmap; an option, not the default.
7. **The end** — the last card is done, or the build stops making progress in a measured way; it returns to its caller.
8. **It runs on its own** as well as from a session.
9. **Everything else** works as the session topology does.
10. **How it is built** — composed onto the session topology, not a copy of it.
11. **The SDD kit is part of its prompt** (the Architect: "the std kit needs to be woven in there. The most recent version std kit three"), with no step that waits for a person.

**Panes:** builder and reviewer, view-only, in a window of their own.

### 8.3 Review

The Architect: "review… that is actually very useful. To have that run as a one shot, as a parameterized thing… pick a style… one of these three common types of reviews." **Input:** what to review (a branch, a range or files) and a style. **Work:** one session per style, in a worktree at the target, with read-only tools, one turn. **Output:** the review. **Pane:** view-only. The three styles are texts picked from published review practice (defects, design, security; sources in `runs/review_styles/README.md`).

### 8.4 Swarm

The Architect: "a swarm topology for low-level agents… parallelize and divide… you give it either the problem statement… or like a roadmap and a series of sprint cards… mostly non interactive." **Input:** a roadmap and its cards, or a problem statement (a large model writes the cards first). **Work:** cards that touch different files run in parallel as builds, each on its own branch; cards that share files wait their turn. **Output:** a report per card. **Panes:** a window with a pane per running session.

### 8.5 Delegate

The Architect: "you could just use the delegate tool… We need to make sure that that's real." A child session given a task in prose, on the caller's model unless the call names another, interactive, its answer folded back as the tool's result. Built in kernel sprint 323.

### 8.6 After these

Best-of-N on the same machinery, pair coding, the adversarial reviewer for documents. The Architect: there are fewer than twenty natural shapes, and they are all plays on each other.

## 9. How readily a session hands work off

The Architect's "level setting" for the propensity to delegate: a session setting beside length and tone, changeable mid-session, measured from the record as topology calls per turn. Built in kernel sprint 324 (`handoff`).

## 10. What changes in the code

Built through kernel sprint 324 and taken out by this round:

- the card refusal (`CardRefused`; a card is no longer refused for lacking a done-condition);
- the checks after each turn (`ChecksRun`, command and sentence checks, the record check, `run_checks`, the judge of sprint 322);
- the loop that sent failed checks back as the worker's next message, and its limits (`RunLimits`, `stuck`);
- the report's checks.

Kept: the caller's hold, the panes, the worktrees, the build and review tools' card fields, the report of what was said, changed and committed, delegate children as sessions, and the handoff setting.
