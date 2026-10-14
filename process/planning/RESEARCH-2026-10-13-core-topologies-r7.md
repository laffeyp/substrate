# RESEARCH: the core topologies — SDD's team model on Substrate's record (round 7)

*2026-10-13. Round 7 replaces rounds 1 to 6 (`RESEARCH-2026-10-13-core-topologies.md`, `-r2.md` to `-r6.md`), which stay on disk. It is a rewrite, made after a full reading of the SDD kit 3 (`sdd-kit-3/`): the kit's own artifacts are the topologies' inputs and outputs, Substrate's record is the signal trace the kit assumes, and the topologies are the kit's team model running on that record. Earlier rounds invented forms, outputs, event names and defaults that the kit already defines; those are gone.*

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

- **The discipline does not change.** A topology follows `AGENTS.md`: the vocabulary is the contract, the dual contract grades the work, the Rubber Duck Pass closes it, decisions are resolved and recorded. Nothing is bolted on.
- **What the kit could only describe, Substrate can do.** The kit's agent narrates its signal trace into a report because the trace dies with the process. In Substrate the trace is the record, so the grade of the signal contract is read from it, not narrated, and the caller can watch, stop and replay a run as it happens.

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

### 3.2 The input is a sprint card

`templates/SPRINT_CARD.md` is the form. The kit calls a sprint card "a typed Command Message — the canonical handoff between the Architect's plain-English direction and the Agent's executable work". Its sections:

- frontmatter: `id`, `status`, `phase`, `pass_kind` (`architecture | functional | docs | bridge | observation`);
- `scope`: one paragraph naming one verifiable property;
- `prerequisites`;
- `context_files`;
- `signal contract`: `Emits` (tags from the locked vocabulary only), `Consumes`, `Invariants`;
- `artifact contract`: files created, files modified, content assertions, command exit codes;
- `observation contract`: required for `functional` and `observation` cards;
- `done criteria`, `notes`.

The card's own self-review checklist is the validity rule the topology enforces before it runs anything: the scope is concrete; `context_files` covers what the work needs; every `Emits` tag is in the vocabulary; the artifact contract is gradable; a `functional` or `observation` card has an observation contract; the card touches at most two files and one concept (hard rule 6). Most of these are mechanical checks — tag membership, section presence, file counts — and the topology refuses a card that fails one, naming it, the way the server refuses a missing input field today. The calling session and the user write the card together first; that is the conversation the Architect described: work with the session model "to get all the inputs correct. And then you just load it up and it happens."

The fields a run needs beyond the card — which repository, which model — fill from the calling session, which is the auto-population the Architect asked for.

### 3.3 The output is a Signal Report

`templates/SIGNAL_REPORT.md` is the output. Foundation 03's four sections, Observed, Expected, Delta and Hypothesis, with nine subsections: `scope_confirmation`, `work_performed`, `signal_trace`, `signal_trace_tags`, `dual_contract_self_grade`, `blackboard_append`, `rubber_duck_observations`, `status_and_blockers`, `artifact_payloads`. Its status line is one of `complete`, `complete-partial` (with what was deferred), `blocked-on-user` (with the question) or `failed` (with the reason and the rescoped card).

Foundation 03 makes this report the protocol between agents: "No natural language between agents. The program described its own behavior precisely. The monitoring agent read it." A topology returns its Signal Report to its caller; one role hands another a Signal Report; a reviewer's reply is a Signal Report. The Report layer of the grammar (Layer 8, `grammar/PRINCIPLES.md`) binds the vocabulary's tags into it.

### 3.4 The grade is read from the record

The kit's dual contract has three legs, and a card closes only when all of them pass:

- **Signal contract.** Every tag in `Emits` fires; no tag outside the vocabulary fires; the declared invariants hold. In Substrate the record is the trace, so this leg is computed from the record: tag membership against the vocabulary, set difference against `Emits`, invariants checked as assertions over the events. It is not narrated.
- **Artifact contract.** The files exist, the content assertions hold, the commands return their expected exit codes. The commands run with the gate's core (`coding_flow/gate.py`), in the run's own worktree, not a throwaway folder.
- **Observation contract.** The driving steps run, and the expected log substrings, runtime signals and visual state are checked, by the project's own harness.

The grade is produced by a monitoring role that reads the record and runs the checks, never by the role that did the work. This is the kit's own condition for self-grading being worth anything: `TECHNIQUES.md` #5 and the Rubber Duck Pass section of `AGENTS.md` say pure self-critique is contested (Huang et al. 2023; Tyen et al. 2023) and the pass is defensible only against external check surfaces — the locked vocabulary, the card's contracts, the vocabulary's invariants, the tone canon. Substrate makes those surfaces mechanical. The Rubber Duck Pass itself (sequence narration, the six observation categories, the four dispositions) is written by the monitoring role over the record's events, in the vocabulary's terms.

### 3.5 The loop

Foundation 03's single-agent loop is WRITE, RUN, READ, CLOSE: write the code, run it and let it emit, read the capture, make one targeted change. A build is that loop with the roles separated: the coding session writes and runs; at the end of its turn the monitoring role reads the record and grades; the grade's delta goes back to the coding session as its next message; the loop ends when the card closes or cannot.

In the session topology this is one change at a turn's end: where a session pauses on `Returned` for a person, a driven session runs the grade and writes the next `UserMessage` from it, or ends. The change is composed onto the one session topology, not built on a copy, as recorded in the kernel board's Decisions on 2026-10-13 (round 5 §9 gives the grounds: one canonical home for the turn's vocabulary, composition as the topology already does for `first_message` and `language`, and the 33-hunk drift between two copies of `session_registry.py` before sprint 099).

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

The kit's sprint sweet spot is two files and one concept, found across about 130 soundfield sprints (hard rule 6, `TECHNIQUES.md` #12), and a bigger change is split into a chain of small cards (#17). Model classes (§2) decide how much of that a worker is given: a large model can take a roadmap and its cards and run an autonomous build or a swarm itself; a small model gets one card, kept to what its window holds. This is the Architect's division of high, medium and low models: the high models get a roadmap and its sprint cards; the low models get as much of a sprint card as they can understand.

### 3.9 Vocabulary first

Hard rule 12: no implementation sprint dispatches until the vocabulary exists. Hard rule 2: tags are never invented inline; each new one is a typed proposal (`grammar/PRINCIPLES.md`: `NEW_TAG_PROPOSED`, `PAYLOAD_FIELD_PROPOSED`, `SEQUENCE_RULE_PROPOSED`, `INVARIANT_PROPOSED` and four more), ratified on the grounds, with a version bump. The topologies need events the session vocabulary does not yet have: a run started by a caller, a run ended, a card refused, a contract graded, a Signal Report written, a run stopped by its caller. Each is a proposal against the session vocabulary, made in a vocabulary session for the topology layer before any of it is built (§6, card 1). The audit found eight topologies with no vocabulary at all; none of the topologies below is built without one.

## 4. The shapes

Each shape is roles, an input, an output and a loop. The kit names most of them already.

### 4.1 Build

**Roles:** one coding session, one monitoring role. **Input:** one sprint card. **Output:** its Signal Report, and the branch its work is on. **Loop:** §3.5, until the card's dual contract passes or the card cannot close; the build does not merge, and the caller reads the diff and decides. **Pane:** view-only.

`pass_kind` changes the run in the ways the template states: an `architecture` card gets the deepest self-review; a `bridge` card writes its SDK bridge mapping (`TECHNIQUES.md` #46) before any code; an `observation` card writes no code and runs the observation contract of earlier cards.

### 4.2 Autonomous build

The 2026-09-24 note, point by point, on the design above.

1. **Input** — a roadmap, its sprint cards, and a prompt with a fixed part (general best practice) and a project part.
2. **The automatic reply** — every time the builder would return to a person, a fixed reply is written instead. In kit 3's terms this is resolve-and-record: a question is settled on the three grounds (the project, SDD practice, engineering practice with a named source), recorded, and work continues.
3. **The review** — every n-th return goes to a standing reviewer instead, opened with the builder. Its review returns to the topology, which appends "analyze, verify, apply" and sends it to the builder. The review is a Signal Report (§3.3): the reviewer is the monitoring role, reading the record.
4. **Callers** — normally started from a session once the roadmap and cards are made with the user.
5. **The review corrects drift** — against the roadmap, the original intent and cards, SDD, best practice and the project's conventions.
6. **The reviewer may propose** new cards, changed cards or a new roadmap; an option to experiment with, not the default.
7. **The end** — the last card closes, or the build stops making progress in a measured way; it returns to its caller. It is suited to one epic's cards as much as a whole project.
8. **It runs on its own** as well as from a session.
9. **Everything else** works as the session topology does.
10. **How it is built** — the note says to copy the session topology; it is composed onto it instead (§3.5).
11. **The SDD kit is part of its prompt.** Kit 3 is that kit with the waits removed: no step waits for a person; a question only the user can answer is recorded and work continues. The builder and the reviewer both work under it, and the builder keeps the project's `BLACKBOARD.md` and `KIT_DIARY.md` as the kit requires.

**Panes:** builder and reviewer, view-only, in a window of their own.

### 4.3 Review

**Roles:** one or more monitoring sessions. **Input:** what to review, and the review's style. **Output:** a Signal Report per reviewer. **Loop:** one pass; a one-shot run. **Pane:** view-only.

The Architect named review as one of the first shapes: "review, code review, that is actually very useful. To have that run as a one shot, as a parameterized thing." A style is a text chosen by name, the way length and tone are; the set is picked from well-known review styles in published practice when Review is built. The kit gives a review its grounding: the vocabulary, the contracts, the invariants and the tone canon are its check surfaces (§3.4), and Addendum A gives three lenses that each catch what the others cannot — structural, perceptual, and adversarial ("could this lie?"). The existing `code_review` application, whose severity is a hash of the text and whose reviews never return, is replaced by it.

### 4.4 Swarm

**Roles:** many coding sessions in parallel, a monitoring role per card, an integration role. **Input:** a roadmap and its cards, or a problem statement. **Output:** a Signal Report per card and one for the integration. **Pane:** a window with a pane per running session.

The kit names its parts. Parallel dispatch is safe on file-disjoint cards (`TECHNIQUES.md` §3), and a card's artifact contract lists the files it creates and modifies, so the topology computes which cards can run together from the cards themselves. Shared contract files go first, in a Wave 0 card whose output the parallel cards build against (#15). Each wave ends with an N.INT integration card that asserts everything in the wave is mounted, wired and visible end to end (#16). Given a problem statement, a planning step on a large model writes the roadmap and cards before the workers start; given cards, the session and the user have already planned.

### 4.5 Best-of-N and the correction loop

Both are in `TECHNIQUES.md` §3. Best-of-N runs one card as several builds and keeps the one whose dual contract passes, halting when none does; Substrate already has two versions of it (`best_of_n_verified`, `coding_flow`). The correction loop feeds a failed build's error back into the next attempt, bounded; in this design it is what the driven session does on every failed grade (§3.5).

### 4.6 Delegate

Delegate stays the open-ended shape: a child session given a task in prose, interactive. It becomes one kind of child, a session, so that every child has a pane a person can write to; the child's model defaults to the caller's, never the stand-in; the bare `tool_loop` child and its 6-step cap go. Its answer folds back as today.

### 4.7 After these

Pair coding (a builder the user works with, and a reviewer the topology drives), the adversarial reviewer for documents (the adversarial lens of §4.3 in rounds), and the discovery arena of Addendum D (a real model loose in a disposable container on adversarial tasks, its crashes harvested from the record into reproduce-then-kill tests). Each is roles, a card, a report and a loop, on the same machinery. The Architect: there are fewer than twenty natural shapes, and they are all plays on each other.

## 5. How readily a session uses topologies

A session setting at the level of length and tone, for how readily the model hands work to a topology rather than doing it itself, written into the session prompt and changeable mid-session the way length and tone are. Its effect is measured from the record: topology calls per turn, by setting and by model.

## 6. The next step

In the kit's order: the vocabulary first, then the machinery, then the shapes, each card closed against its dual contract.

1. **Vocabulary session for the topology layer** (`grammar/BOOTSTRAP.md`, on the session vocabulary). Proposals for the events of §3.9, their payloads, the session that frames a run, the ordering rules (a run's end follows its start; nothing follows its end), and the binding of the Signal Report (Layer 8). Ratified, versioned, with a rationale document.
2. **Every workspace a repository; worktrees from the kernel** (§3.7).
3. **The card as input.** Parsing a sprint card, and refusing one that fails the template's mechanical checks, naming the failure (§3.2).
4. **The grade from the record.** The signal leg against the vocabulary and the card, the artifact leg with the gate's core in the worktree, the observation leg through the project's harness; the Signal Report written from them (§3.3, §3.4).
5. **The driven session.** The turn's end composed onto the session topology: grade, then the next message or the end (§3.5).
6. **The caller's hold.** Runs as the caller's background work; the caller reading the child's record live; stop, pause, resume, step and replay; panes that open with a run, view-only when the topology writes the next message (§3.6).
7. **Review**, the first shape: one-shot, styles as texts, its report back to the caller (§4.3).
8. **Build** (§4.1).
9. **Real observation.** A session on a real model calls Review on a real branch and Build on a real card in a real repository; each returns its Signal Report, the build's branch passes its card's dual contract, and the panes showed both runs as they went.

Then delegate as a session child, the autonomous build, the swarm, best-of-N on the same machinery, the topologies setting, and the shapes of §4.7.
