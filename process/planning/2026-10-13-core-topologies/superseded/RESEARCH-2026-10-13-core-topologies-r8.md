# RESEARCH: the core topologies — SDD's team model on Substrate's record (round 8)

*2026-10-13. Round 8 replaces rounds 1 to 7 (`RESEARCH-2026-10-13-core-topologies.md`, `-r2.md` to `-r7.md`), which stay on disk. Round 7 rebuilt the design on the SDD kit 3: the kit's artifacts as the topologies' inputs and outputs, Substrate's record as the signal trace, the kit's team model running on it. Round 8 keeps that and moves the kit to where it belongs in a product most people will use: inside Substrate. The user writes a plain card and gets a plain report; the kit's discipline runs underneath, under plain names, and its rules for an SDD practitioner's own project are not imposed on the user's (§1, §3.2–§3.4, §3.8–§3.10).*

*Sources. The SDD kit 3 in full: `README.md`, `AGENTS.md`, `TECHNIQUES.md`, `ADDENDUMS.md`, `foundations/01`–`04`, `grammar/PRINCIPLES.md` and `BOOTSTRAP.md`, `templates/`, `lib/sdd.py`, `example/`. The autonomous build note (`substrate-ui/process/methodology/2026-09-24-autonomous-build-topology.md`), the governing version. The topology audit (`process/planning/AUDIT-2026-10-11-topologies.md`). The code read for round 2: `topologies/tool_loop/{substrate_tools,delegate,background}.py`, `topologies/applications/registry.py`, `topologies/session/__init__.py`, `topologies/session/model_class.py`, `topologies/coding_flow/gate.py`, `substrate-ui/server.py`, `substrate-ui/web/reveal_component.ts`. The Architect's statements in the 2026-10-13 sessions, cited as they are used.*

## 1. Where the topologies sit

The SDD kit is a methodology with no orchestrator, on purpose. Its README says where it stops: "Multiple agents running in parallel", "Dispatch decisions need to be made by a scheduler process", and then "Wrap the kit in a thin orchestrator. A Python script that walks `sprints/`, dispatches Workers to an LLM, parses Signal Reports, writes artifacts. The discipline (this kit) stays the same; the orchestrator handles the operations." `TECHNIQUES.md` §3 lists what it leaves to that orchestrator:

- best-of-N parallel dispatch with build-validation scoring and halt-on-all-fail;
- a correction loop with build-error feedback;
- preflight codebase signature verification;
- multi-foreman parallel sprint dispatch on file-disjoint sprints;
- auto-executing the observation contract;
- per-role model routing;
- a signal-trace sink with cross-session replay.

Substrate is that orchestrator. Its record is the signal trace with replay: every event a run produces, typed, ordered, persisted and replayable (`substrate replay` checks every recorded decision by hash). Its session vocabulary (`process/signals/session-vocabulary.md`) is a locked, versioned vocabulary in the kit's sense. The topologies in this document are the kit's team model (foundation 03) — coding, monitoring, test, vocabulary keeper, integration — run as Substrate sessions over that record, with the kit's sprint card as their input and its Signal Report as their output.

Two consequences shape everything below:

- **The discipline runs inside; the user never has to know it.** Substrate is a product for most people, not for SDD practitioners. The kit is how Substrate is built and how a topology does its work: checks run from the record, the worker never grades itself, reviews ground themselves in what can be checked, decisions are recorded. The user writes what they want done and how to tell it is done, and reads a report in plain words. Nobody has to know what a dual contract or a Rubber Duck Pass is, and the product does not call them that.
- **What the kit could only describe, Substrate can do.** The kit's agent narrates its signal trace into a report because the trace dies with the process. In Substrate the trace is the record, so a run's checks are read from it, not narrated, and the caller can watch, stop and replay a run as it happens.

## 2. What Substrate has today

The facts the design builds on, from the code and the audit.

**Topology calls.** A session has `run_topology(name, inputs)`, which blocks the turn or makes the model poll `run_topology_poll`, and returns the payload of the last non-`substrate.` event in the run's record (`_extract_terminal_output`). Of the 18 names `list_topologies` offers, a session can run 3. Application manifests declare `[inputs]` with defaults, and the server refuses a call missing a field with no default, naming it (`_validate_topology_inputs`, `server.py:628`); the model never sees those fields, because `list_applications` omits them (`substrate_tools.py:709`). Role models default to `kimi-k2.6:cloud` and `claude` whatever the session runs on. A run works in a temp folder that is deleted afterwards (`server.py:3544`), and its record does not name the session that started it. `ApplicationRuns` (`registry.py:44`) already separates `one-shot`, `session` and `session_composite`.

**Delegate.** `tool_loop/delegate.py` hands a task to a child and folds the answer back, with depth, fan-out and tree caps and parent provenance on the child's record. No model has called it in the 86 sessions the audit counted. Two of its four paths (a named standing session, the `children` fan-out) run real registry sessions; the other two run a bare `tool_loop` on a thread, with no session, a 6-step cap and a private folder instead of the parent's workspace. A fan-out child given no model runs the deterministic stand-in (`delegate.py:373`).

**Worktrees.** `_session_worktree` (`server.py:1930`) makes a worktree on a branch per session and `_worktree_diff` reads what changed; both are tested, and nothing outside the tests calls `_session_worktree`. No session gets a worktree today.

**The turn's end.** The session topology (`topologies/session/__init__.py`) ends every turn with a `Returned` event and pauses until the next `UserMessage` (`pause_await_input`, line 1622). A producer inside the topology can write a `UserMessage`: `first_message` does (line 432).

**Background work.** A background command belongs to a session; its end is written to that session's record as `BackgroundTaskEnded` before the model's next step and told once; ending or interrupting the session stops what it owns (`stop_owner`, `tool_loop/background.py`).

**The gate.** `coding_flow/gate.py` runs a command, takes its exit code as the truth, stops its process group, and normalises its output (`GateResult{passed, returncode, summary}`). It runs on files parsed out of a reply, in a throwaway folder.

**Model classes.** `topologies/session/model_class.py` sorts models into `harness_agent`, `large`, `medium` and `small`, and gives each a default guidance level; `small` models have windows as small as 8,192 tokens.

**The UI.** A pane binds a session or follows a record by path (`SessionController.attachRecordRoot`); a window holds at most eight panes. Nothing opens a pane when a run starts. The meta panel's view of a delegate's children is prototype data (`demoDescentChildren`), whose entries already carry a `talkable` flag.

## 3. The design

### 3.1 The roles are sessions

Foundation 03 names five roles: the Coding Agent (writes code against the vocabulary), the Monitoring Agent (reads the signal capture, compares observed with expected, writes the Signal Report), the Test Agent (turns confirmed-good captures into regression fixtures), the Vocabulary Keeper (owns the vocabulary, reviews every proposed change) and the Integration Agent (runs the whole system and reads traces across boundaries). It adds the rule that matters most here: "The Coding Agent should not also be evaluating whether its own signals are correct. That's the Monitoring Agent's job."

In a topology each role that takes model turns is a session in the registry, which already gives it an id, a manifest, a record, interrupt, end and a pane. A topology is a composition of these roles over shared records. The kit's single agent wears all the hats in sequence because nothing else is available to it; Substrate can give each hat its own session when the shape calls for it, and keep the one-session collapse when it does not.

### 3.2 The input is a card

The input to a working topology is a card: a short, structured statement of one piece of work. The kit's sprint card (`templates/SPRINT_CARD.md`, "a typed Command Message — the canonical handoff between the Architect's plain-English direction and the Agent's executable work") is the full form of it, and Substrate accepts the full form. But a card a person writes needs only three things:

- **What to do.** One piece of work, concrete enough to check.
- **Where.** The files or the part of the project it touches, and what to read first.
- **How to tell it is done.** The checks: commands that pass, things that must be true, behaviour to see.

These are the kit's scope, `context_files` and contracts, in the words anyone would use. A card missing one of the three is refused, and the refusal names what is missing, the way the server refuses a missing input field today. The kit's richer sections — signals the work must emit, invariants, `pass_kind`, the observation steps — are used when a card has them and never required. The calling session and the user write the card together first; that is the conversation the Architect described: work with the session model "to get all the inputs correct. And then you just load it up and it happens." The session model can fill in most of a card from that conversation, and can write the full SDD form for a user who wants it.

The fields a run needs beyond the card — which repository, which model — fill from the calling session, which is the auto-population the Architect asked for.

### 3.3 The output is a report

A working topology ends with a report, and the report has a fixed shape, so that a caller, a person or another topology can read any report the same way. The shape is the kit's Signal Report (`templates/SIGNAL_REPORT.md`), whose four parts are what any report on work needs: what happened, what was expected, the difference, and what to do about it. In plain words:

- what the card asked for, as the worker understood it;
- what was done, and the files changed;
- each check, and whether it passed, with its output;
- what is left, and why: done, done with something deferred, stuck on a question only the user can answer, or failed (with what to try next).

Inside Substrate the report carries the rest of the kit's Signal Report — the run's events, the review of the run, the decisions it made — for the caller's model and for any later run to read. Foundation 03 makes such a report the protocol between agents ("No natural language between agents"): one role hands another a report, and a reviewer's reply is a report.

### 3.4 The checks, read from the record

A card is done when its checks pass, and the checks are run by a separate role that reads the record, never by the role that did the work. Foundation 03: "The Coding Agent should not also be evaluating whether its own signals are correct." This is the kit's dual contract, built into the product under the plain name of checks:

- **The card's own checks.** The commands it names, run with the gate's core (`coding_flow/gate.py`: exit code as the truth, the process group stopped on interrupt, output normalised) in the run's own worktree; the things it says must be true; the behaviour it says to see, through the project's harness where it has one.
- **Substrate's own checks.** Every run is recorded in Substrate's locked session vocabulary, so the record can be checked mechanically: the run's events are known kinds, in an allowed order, with the payloads they must carry. A user's project needs no vocabulary of its own for this; the vocabulary checked is Substrate's.

At the end of each run the checking role also reviews the run against those check surfaces — the kit's Rubber Duck Pass, under no such name: it walks the run's events in order and notes anything missing, out of order, unexpected or malformed, and what was done about each. `TECHNIQUES.md` #5 gives the reason the review must be grounded this way: pure self-critique is contested (Huang et al. 2023; Tyen et al. 2023), and a review is worth something only against surfaces it can check. Substrate makes those surfaces mechanical, because the trace is the record.

### 3.5 The loop

Foundation 03's single-agent loop is WRITE, RUN, READ, CLOSE: write the code, run it and let it emit, read the capture, make one targeted change. A build is that loop with the roles separated: the coding session writes and runs; at the end of its turn the monitoring role reads the record and grades; the failed checks go back to the coding session as its next message; the loop ends when the card closes or cannot.

In the session topology this is one change at a turn's end: where a session pauses on `Returned` for a person, a driven session runs the checks and writes the next `UserMessage` from them, or ends. The change is composed onto the one session topology, not built on a copy, as recorded in the kernel board's Decisions on 2026-10-13 (round 5 §9 gives the grounds: one canonical home for the turn's vocabulary, composition as the topology already does for `first_message` and `language`, and the 33-hunk drift between two copies of `session_registry.py` before sprint 099).

### 3.6 The caller holds the run

A run started by a session belongs to that session, and the session holds all of it, because a Substrate run is its record. Foundation 02 names this as its third stage, continuous observation: "Signals stream from a running service into an agent that observes without being prompted." The caller is that agent. It reads the child's record as the child writes it, in the vocabulary's terms, and can act on it: stop the run, pause and resume it, step through its events, replay it in full, compare it with another run (`first_divergence`). A model that calls a topology can watch the shape of the work it set in motion while the work is happening, and change it.

These controls are operations on the record, available to the caller's model as tools and to the user in the panes. The panes are views of the same records:

- A run's pane opens when the run starts: in the caller's window for one session, in a window of its own for several.
- A pane is interactive when a person writes the session's next message, and view-only when the topology writes it. Delegate children are interactive; build, autonomous build and swarm sessions are view-only.
- The controls work from the caller: the caller's pane shows the run, and the caller can stop it at any time.

A run started by a session returns at once and its end is written into the caller's record before the caller's next step, told once, the way `BackgroundTaskEnded` works. Ending or interrupting the caller ends its runs. Polling goes.

### 3.7 The worktree is the context; every workspace is a repository

A run's only context is the worktree it is given: the files it can see. The card's `context_files` name the files in that worktree to read first; the kit's hard rule against authoring without reading them applies unchanged.

Every session's workspace is a git repository: Substrate runs `git init` and a first commit when it is not one. The Architect's grounds, 2026-10-13: git is useful well beyond code, making every workspace a repository automatically is a large benefit, and the user can do what they like with it afterwards, since it is a folder on their own machine. Worktree creation moves from the server into the kernel's session registry, so that any run can take its own worktree and branch.

### 3.8 Card size follows model size

Small cards work better: the kit found an agent's reliable scope tops out around two files and one concept, across about 130 soundfield sprints (`TECHNIQUES.md` #12), and splits bigger changes into a chain of small cards (#17). In the product this is guidance the session model applies when it helps the user write cards, not a rule the user must follow; a card larger than the worker can hold is split, and the user is told why. Model classes (§2) decide how much a worker is given: a large model can take a roadmap and its cards and run an autonomous build or a swarm itself; a small model gets one card, kept to what its window holds. This is the Architect's division of high, medium and low models: the high models get a roadmap and its sprint cards; the low models get as much of a sprint card as they can understand.

### 3.9 Vocabulary first, for Substrate's own work

The kit's founding rules — a locked vocabulary before any implementation (hard rule 12), no tag invented inline (hard rule 2), each new one a typed proposal ratified with a version bump (`grammar/PRINCIPLES.md`) — govern how Substrate itself is built. They do not apply to a user's project, which may have no vocabulary at all and still gets every check of §3.4.

Building the topologies needs events the session vocabulary does not have: a run started by a caller, a run ended, a card refused, the checks run, a report written, a run stopped by its caller. Each is a proposal against the session vocabulary, made in a vocabulary session for the topology layer before any of it is built (§6, card 1). The audit found eight topologies with no vocabulary at all; none of the topologies below is built without one.

### 3.10 Names in the product

The kit's terms stay in Substrate's own documents and code. The product names things by what they do — a card, a check, a report, a review — and explains each in a line where it appears. A user who knows SDD can write the full card and read the full report; a user who does not never meets the terms.

## 4. The shapes

Each shape is roles, an input, an output and a loop. The kit names most of them already.

### 4.1 Build

**Roles:** one coding session, one checking role. **Input:** one card. **Output:** its report, and the branch its work is on. **Loop:** §3.5, until the card's checks pass or the card cannot close; the build does not merge, and the caller reads the diff and decides. **Pane:** view-only.

A card in the full SDD form can carry a `pass_kind`, and it changes the run in the ways the kit's template states: an `architecture` card gets the deepest review; a `bridge` card writes down the external library's real API (`TECHNIQUES.md` #46) before any code; an `observation` card writes no code and runs the checks of earlier cards.

### 4.2 Autonomous build

The 2026-09-24 note, point by point, on the design above.

1. **Input** — a roadmap, its sprint cards, and a prompt with a fixed part (general best practice) and a project part.
2. **The automatic reply** — every time the builder would return to a person, a fixed reply is written instead. In kit 3's terms this is resolve-and-record: a question is settled on the three grounds (the project, SDD practice, engineering practice with a named source), recorded, and work continues.
3. **The review** — every n-th return goes to a standing reviewer instead, opened with the builder. Its review returns to the topology, which appends "analyze, verify, apply" and sends it to the builder. The review is a report (§3.3): the reviewer is the checking role, reading the record.
4. **Callers** — normally started from a session once the roadmap and cards are made with the user.
5. **The review corrects drift** — against the roadmap, the original intent and cards, SDD, best practice and the project's conventions.
6. **The reviewer may propose** new cards, changed cards or a new roadmap; an option to experiment with, not the default.
7. **The end** — the last card closes, or the build stops making progress in a measured way; it returns to its caller. It is suited to one epic's cards as much as a whole project.
8. **It runs on its own** as well as from a session.
9. **Everything else** works as the session topology does.
10. **How it is built** — the note says to copy the session topology; it is composed onto it instead (§3.5).
11. **The SDD kit is part of its prompt.** Kit 3 is that kit with the waits removed: no step waits for a person; a question only the user can answer is recorded and work continues. The builder and the reviewer both work under it; the user sees the build's cards close and its reports, not the kit.

**Panes:** builder and reviewer, view-only, in a window of their own.

### 4.3 Review

**Roles:** one or more reviewing sessions. **Input:** what to review, and the review's style. **Output:** a report per reviewer. **Loop:** one pass; a one-shot run. **Pane:** view-only.

The Architect named review as one of the first shapes: "review, code review, that is actually very useful. To have that run as a one shot, as a parameterized thing." A style is a text chosen by name, the way length and tone are; the set is picked from well-known review styles in published practice when Review is built. The kit gives a review its grounding: what it reviews against must be checkable — the card, its checks, the record (§3.4) — and Addendum A gives three lenses that each catch what the others cannot — structural, perceptual, and adversarial ("could this lie?"). The existing `code_review` application, whose severity is a hash of the text and whose reviews never return, is replaced by it.

### 4.4 Swarm

**Roles:** many coding sessions in parallel, a checking role per card, an integration role. **Input:** a roadmap and its cards, or a problem statement. **Output:** a report per card and one for the integration. **Pane:** a window with a pane per running session.

The kit names its parts. Parallel work is safe on cards that touch different files (`TECHNIQUES.md` §3), and each card says where it works, so the topology works out which cards can run together from the cards themselves. Shared contract files go first, in a Wave 0 card whose output the parallel cards build against (#15). Each wave ends with an N.INT integration card that asserts everything in the wave is mounted, wired and visible end to end (#16). Given a problem statement, a planning step on a large model writes the roadmap and cards before the workers start; given cards, the session and the user have already planned.

### 4.5 Best-of-N and the correction loop

Both are in `TECHNIQUES.md` §3. Best-of-N runs one card as several builds and keeps the one whose checks pass, stopping when none does; Substrate already has two versions of it (`best_of_n_verified`, `coding_flow`). The correction loop feeds a failed build's error back into the next attempt, bounded; in this design it is what the driven session does on every failed grade (§3.5).

### 4.6 Delegate

Delegate stays the open-ended shape: a child session given a task in prose, interactive. It becomes one kind of child, a session, so that every child has a pane a person can write to; the child's model defaults to the caller's, never the stand-in; the bare `tool_loop` child and its 6-step cap go. Its answer folds back as today.

### 4.7 After these

Pair coding (a builder the user works with, and a reviewer the topology drives), the adversarial reviewer for documents (the adversarial lens of §4.3 in rounds), and the discovery arena of Addendum D (a real model loose in a disposable container on adversarial tasks, its crashes harvested from the record into reproduce-then-kill tests). Each is roles, a card, a report and a loop, on the same machinery. The Architect: there are fewer than twenty natural shapes, and they are all plays on each other.

## 5. How readily a session uses topologies

A session setting at the level of length and tone, for how readily the model hands work to a topology rather than doing it itself, written into the session prompt and changeable mid-session the way length and tone are. Its effect is measured from the record: topology calls per turn, by setting and by model.

## 6. The next step

In the kit's order: the vocabulary first, then the machinery, then the shapes, each card closed against its dual contract.

1. **Vocabulary session for the topology layer** (`grammar/BOOTSTRAP.md`, on Substrate's session vocabulary). Proposals for the events of §3.9, their payloads, the session that frames a run, the ordering rules (a run's end follows its start; nothing follows its end), and the report's binding to them. Ratified, versioned, with a rationale document.
2. **Every workspace a repository; worktrees from the kernel** (§3.7).
3. **The card as input.** Reading a card in plain form or the full SDD form, and refusing one that lacks what to do, where, or how to tell it is done, naming what is missing (§3.2).
4. **The checks from the record.** The card's checks with the gate's core in the worktree and through the project's harness where it has one; Substrate's own checks of the run's events against its vocabulary; the review of the run; the report written from them (§3.3, §3.4).
5. **The driven session.** The turn's end composed onto the session topology: run the checks, then the next message or the end (§3.5).
6. **The caller's hold.** Runs as the caller's background work; the caller reading the child's record live; stop, pause, resume, step and replay; panes that open with a run, view-only when the topology writes the next message (§3.6).
7. **Review**, the first shape: one-shot, styles as texts, its report back to the caller (§4.3).
8. **Build** (§4.1).
9. **Real observation.** A session on a real model calls Review on a real branch and Build on a real card in a real repository; each returns its report, the build's branch passes its card's checks, and the panes showed both runs as they went.

Then delegate as a session child, the autonomous build, the swarm, best-of-N on the same machinery, the topologies setting, and the shapes of §4.7.
