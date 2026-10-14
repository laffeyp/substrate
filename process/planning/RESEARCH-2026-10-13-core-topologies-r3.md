# RESEARCH: the core topologies — round 3

*2026-10-13. Round 3 is the whole design in one document: round 1's parts that round 2 left out (what a topology is, Build's form, Swarm, what each model is given, the topologies setting, the document topologies) are back, brought into line with round 2's code findings. One thing changes from round 2 (`RESEARCH-2026-10-13-core-topologies-r2.md`): the autonomous build (§6) now rests on the 2026-09-24 note alone (`substrate-ui/process/methodology/2026-09-24-autonomous-build-topology.md`), with the SDD kit 3 (`sdd-kit-3/`) in its prompts. Rounds 1 and 2 also drew detail from the 2026-09-11 product spec (round 17: on-track and full reviews, follow-ups, schedule defaults); the Architect named the note the governing version, and that detail is gone. Rounds 1 and 2 stay on disk. Round 2 read the code each part of round 1 rests on — `tool_loop/substrate_tools.py`, `applications/registry.py`, the server's run, composite and worktree code (`substrate-ui/server.py`), `tool_loop/delegate.py`, the session topology's turn end (`topologies/session/__init__.py`), `tool_loop/background.py`, `coding_flow/gate.py`, and the UI's panes (`substrate-ui/web/reveal_component.ts`) — and corrects round 1, records what it missed, and settles the design where the code makes it plain.*

## 1. What a topology is here

A topology is a function a session calls. It has four parts.

- **A form.** The tool's schema lists every input. Required fields have no default, so the calling model cannot leave them out, and the tool refuses a call that does. The remaining fields fill from the calling session (its workspace, its driver, its guidance level) or from the topology's own defaults. The session model and the user settle the inputs together before the call; the call then loads them and runs.
- **A record.** Every run writes its own record, and the record names the session and seq that started it.
- **An output.** A typed result returned to the caller: what was made, where it is, and whether the run met its own end condition.
- **A pane.** Every run opens a pane in the caller's window, or a window of its own when it has several parts. A run whose next message comes from a person is interactive (delegate, the builder in pair coding); a run whose next message comes from its own topology is view-only (build, autonomous build, swarm), and the user watches it work (§4).

`delegate` stays the open-ended case: a child session given a task in prose. The other topologies are narrower on purpose. Each takes a fixed form and does one kind of work.

## 2. Corrections to round 1

- **Today's code makes no worktree for any session.** The design needs one for every build and swarm worker (§4 says how). Round 1 said a session on a git repo gets one (spec r15 §9c, Mode 2). The helper exists (`server.py:1930`, `_session_worktree`: a branch `substrate/<session>` at `~/.substrate/sessions/wt/<repo>-<session>`), with a read-only diff beside it (`_worktree_diff`), and both are tested. Nothing calls `_session_worktree` outside the tests. `workspace_shape = "worktree"` is a label `_classify_workspace_shape` puts on a picked folder that has a `.git`. A delegate child given `workspace_shape: worktree` gets the label and no worktree.
- **The form exists on the server and is hidden from the model.** Round 1 said nothing forces any field. The server does refuse a call missing a field that has no default, naming it (`_validate_topology_inputs`, `server.py:628`). But the model cannot see the fields: `list_applications` returns name, description, run shape and output kind (`substrate_tools.py:709`), never `inputs_schema`, and `run_topology`'s schema types `inputs` as a bare object. The model learns a required field only by being refused.
- **A delegate fan-out child runs the stand-in, not a model, unless told.** `driver = spec.get("driver") or "deterministic"` (`delegate.py:373`). Its guidance bundle defaults to `standard` whatever the model's class, and its `steps` is always -1.

## 3. What the code adds

**Delegate is four tools in one.** A named standing session, a different-model child, a child given a slice of the parent's record, and a fresh child are four paths (`delegate.py:661–811`). Two run real sessions through the registry (the standing session and the `children` fan-out: `SessionRegistry.create` + `turn_sync`). Three run a bare `tool_loop` on a worker thread with its own event loop: no session id, no manifest, no registry entry, a 6-step cap (`child_max_steps`), and a workspace in a private subfolder (`delegate-runs/d1-cN/workspace`), not the parent's tree as spec §9c says.

**Every topology call blocks the caller's turn, or makes the model poll.** `delegate` blocks until the child stops. `run_topology` blocks by default; with `await_completion=false` it returns a run id the model must poll with `run_topology_poll`, held in a per-boot dictionary (`app.topology_runs`). Substrate already has the better shape for work that ends later: a background command belongs to an owner, its end is written to the owner's record as `BackgroundTaskEnded` before the model's next step and told once, and `stop_owner` ends every task an owner holds (`tool_loop/background.py`, session vocabulary).

**A topology run works in a temp folder.** `_topology_run` makes `tempfile.mkdtemp(prefix="substrate-<name>-")`, runs there and deletes it (`server.py:3544`). Its record goes to the shared runs directory with only a name: no parent session, no parent seq. Delegate does set `parent_session_id` and `parent_seq_at_call` on its child's baseline (`_with_baseline`); `run_topology` does not.

**The output is a guess.** `_extract_terminal_output` returns the payload of the last event whose kind does not start with `substrate.`. For a session-shaped run the last such event is `Returned` or a language event, not an answer.

**The run shape already names the pane.** `ApplicationRuns` has three members: `one-shot`, `session`, `session_composite` (`registry.py:44`). A one-shot run is a record a pane can follow; a session or a composite is one or more registry sessions a pane can bind.

**`required` exists on slots and nothing reads it.** `SlotSpec.required` (`registry.py:90`) has no consumer since sprint 065; inputs mark required by leaving out a default.

**A session's turn ends in one place.** The `return` producer writes `Returned`; termination pauses on it and resumes on the next `UserMessage` (`pause_await_input`, `session/__init__.py:1622`). A `UserMessage` can already be written from inside the topology: the `first_message` producer does it on a fresh record (line 432).

**The gate exists and runs on parsed files.** `coding_flow.gate.run_gate` runs a shell command, takes its exit code as the truth, kills the process group, and normalises the output (`GateResult{passed, returncode, summary}`). It writes a reply's fenced files into a throwaway sandbox first and stops at 60 seconds.

**The UI's child view is prototype data.** The meta panel's descent into a delegate child draws from a hard-coded `demoDescentChildren` table (`reveal_component.ts:1155`), whose entries carry a `talkable` flag. A pane can follow a real record (`SessionController.attachRecordRoot`), and a pane binds a real session, but nothing opens a pane when a run starts. A window holds at most eight panes (`_split`, line 788).

## 4. The design, settled by the code

**One kind of worker: the session.** Every topology part that does model work over turns runs as a registry session: build, each swarm worker, the autonomous builder and its reviewer, every delegate child. A session already has an id, a manifest, a record, interrupt, end, and a pane that binds it. One-shot topologies that do no turn-taking work (`code_review`, `research_sweep`) stay plain runs. The bare `tool_loop` child goes.

**Interactive or view-only is who writes the next message.** A session whose next `UserMessage` comes from a person is interactive; its pane has the input bar. A session whose next `UserMessage` comes from its own topology is driven; its pane is view-only. The flag is a fact on the record, not a pane setting: a driven session's messages carry the producer that wrote them.

**A driven session is the session topology with one change at the turn's end.** On `Returned`, a `check` producer runs the run's done command in its workspace and writes the result; a `continue` producer then writes the next `UserMessage` (the continuation, or for an autonomous build every n-th time the reviewer's reply with "analyze, verify, apply"), or an end producer writes the run's end event (`BuildEnded` for a build, `AutonomousBuildEnded` for an autonomous build). Termination finalises on that event instead of pausing on `Returned`. Everything the run does is on its record.

**A run started from a session is the session's background work.** The call returns at once with the run's session id, and the run's pane opens. Its end is written to the caller's record as an event, told to the model before its next step once, as `BackgroundTaskEnded` is. Interrupting or ending the caller ends the run (`stop_owner`). The form has a `wait` field for the case that wants the answer in the same turn: default true for `delegate`, false for `build`, `autonomous_build` and `swarm`. Polling goes.

**The form is one table, read by both sides.** The manifest's `[inputs]` gains `required = true` and `from = "session.workspace" | "session.driver" | "session.guidance"`. The same table produces each topology's tool schema (one tool per topology, its required fields in `required`), fills the session defaults, and validates on the server. `list_applications` returns it.

**The output is a declared kind.** Each manifest names its output event kind; the tool returns that event's payload. No guessing from the tail.

**Every run records where it came from.** `parent_session_id` and `parent_seq_at_call` go on every run's baseline, as delegate does now.

**Every session's workspace is a git repository.** When a session opens on a workspace that is not one, Substrate runs `git init` there and makes a first commit; the default sandbox workspace starts as one. Branches and worktrees are then always available, for every session and every run. **Worktrees come from the kernel.** `_session_worktree` moves into the session registry: creating a session with `workspace_shape = worktree` on a repository makes the worktree and branch. `_worktree_diff` stays the "what did it change" read. Build and swarm workers ask for it; delegate children take the parent's workspace (spec §9c) unless the call isolates them.

**The done check is the gate, run in place.** `run_gate`'s core (exit code as truth, process-group kill, normalised output) runs a command in a directory, with the limit the form gives, so a build's `done` runs in its worktree.

**The pane follows the run's shape.** A one-shot run opens a view-only pane on its record. A session run opens a pane bound to the session, view-only when driven. A run with parts opens a window with a pane per part; past eight parts, the window shows the integrator and the running workers.

## 5. Build

One card, one worktree, one result. A driven session (§4).

**Form.**

| Field | Required | Default |
|---|---|---|
| `goal` | yes | — |
| `scope` (files and modules it may touch) | yes | — |
| `done` (the commands whose success closes the card: the observation contract) | yes | — |
| `context` (files, docs and records to read first) | yes | — |
| `constraints` | no | none |
| `repo` | no | the session's workspace |
| `base` | no | `HEAD` |
| `model` | no | the session's driver |
| `guidance` | no | the model's class level |
| `max_steps` | no | set high enough for edit-and-test work |
| `wait` | no | false |

**Run.** The kernel makes a worktree on `substrate/build/<id>` from `base`. The worker's first message is composed from the form by its model's class (§9). On each `Returned` the `check` producer runs `done` in the worktree and records exit codes and output; the card closes when they pass, so the worker's own say-so never closes it. Otherwise `continue` writes the next message. The run ends `done`; `stalled` when the step budget runs out or a set number of stops pass with no new commit and no change in `done`'s output; or `failed` on an error.

**Output.** `BuildEnded{status, branch, commits, diff_stat, done: [{command, exit, tail}], summary, record}`, written to the caller's record as the run's end (§4).

**Pane.** View-only, in the caller's window.

## 6. Autonomous build

From the 2026-09-24 note, point by point, on the design of §4.

**Input** (note 1). A fixed form: `roadmap` (path, required), `cards` (directory, required), `project_prompt` (the project part, required); `repo`, `base`, `model` and `reviewer_model` default from the session; `review_every` (n, default 3). The fixed part of the prompt is the same for every build:

- The SDD kit 3, read in full: `sdd-kit-3/AGENTS.md` is the builder's working agreement, and the kit's resolve-and-record rule replaces every wait for a person. Kit 3 already removed sdd-kit-2's halts ("no step in this kit waits for an Architect 'go'"), which is what the note's point 11 asked of an autonomous copy. The one human touch left in kit 3, a user-only question, is recorded under `## Surfaced for review` and the builder keeps working.
- Software engineering best practice and the project's existing conventions.
- The roadmap and every card, in order.

**The automatic reply** (note 2). On every `Returned` but the n-th, the `continue` producer writes a fixed `UserMessage`: a question is answered by best practice and the kit; continue with the current card, or the next one when its `done` passes.

**The review** (notes 3, 5, 6). On every n-th `Returned` the builder gets no reply. The topology sends the reviewer a fixed prompt: review the work since the last review for drift against the roadmap, the cards and their intent, the SDD kit, best practice and the project's conventions. The reviewer's working agreement is the same kit. Its reply comes back to the topology, which appends `-- analyze, verify, apply` and writes the whole as the builder's next `UserMessage`. A form switch lets the reviewer propose new cards, changed cards or a new roadmap; it is off by default and is the experiment the note names.

**The end** (note 7). The last card's `done` passes, or no card closes in a set number of builder stops; `AutonomousBuildEnded` records which, and the run returns to whatever called it. It builds an epic's cards as readily as a whole project's.

**Callers** (notes 4, 8). A session calls it with a form it settled with the user; it also runs on its own, from the CLI or another topology.

**Everything else** (note 9) is the session topology's behaviour.

**How it is built** (note 10). The note says: copy the session topology and modify the copy.

**Output.** `AutonomousBuildEnded{status, branch, cards: [{id, status}], reviews, record}`.

**Pane.** A window with two view-only panes, builder and reviewer.

## 7. Swarm

Divide, run in parallel, integrate. Parallel work in separate worktrees; integration on one branch, one merge at a time.

**Form.** Either `cards` with their `depends_on`, each card a Build form, or a `problem` statement. Plus `repo`, `base`, `worker_model` (default the session's driver; a small model is the intended case), `planner_model` (default the session's driver), `parallel` (default 4), `wait` (default false).

**Run.**

1. **Plan**, only when given a `problem`: one producer on `planner_model` writes a roadmap and cards with dependencies into the record. The caller sees them in the swarm's window before workers start. Given cards, this step does not run; the session and the user have already done it.
2. **Build.** Each card whose dependencies have merged runs as a Build session on its own worktree from the integration branch's current head, up to `parallel` at once.
3. **Integrate.** One producer merges each finished branch into `substrate/swarm/<id>` in dependency order and reruns that card's `done` after the merge. A conflict or a failed check sends the card back as a new Build from the new head, a bounded number of times, then marks it `failed`.

**Output.** `SwarmEnded{status, branch, cards: [{id, status, branch}], record}`.

**Pane.** A window with one view-only pane per running worker and one for the integrator (at most eight panes, §4).

## 8. Delegate

Delegate stays prose-driven and interactive, and becomes one shape: every child is a session, the fan-out path with one child being the single case. The bare `tool_loop` child and its 6-step cap go.

- **Defaults.** Driver: the parent's (not the stand-in). Bundle: the model's class level. Workspace: the parent's (spec §9c), unless the call isolates the child. `wait`: true, so the answer folds back in the same turn as today; with `wait` false it ends like any run (§4).
- **Pane.** Interactive, in the caller's window; with `children`, one pane per child.
- **Observation.** A session on a real model delegates a task that edits and tests code, and the child's result is checked, not just the call.

## 9. What each model is given

The split by model class already used for guidance decides what a worker receives.

- **Large** (`harness_agent`, `large`): the roadmap and the cards. It can run an autonomous build and call a swarm itself.
- **Medium:** the card in full and the roadmap section it belongs to.
- **Small:** the card cut to `goal`, `scope`, `done` and the named context files, in the low guidance level; nothing else enters an 8,192-token window.

The topology composes the worker's first message from the form by the worker's class. The same card runs on any class; the form is the same and the message differs.

## 10. How readily a session uses them

A session control beside length and tone: **topologies**, with positions `off` (the tools are not offered), `ask` (the model proposes a call and waits for the user's yes), `use` (the model calls a topology when a task fits a form), `prefer` (the model splits work into topology calls wherever it fits). Each position is a text in the session prompt, written and changed as length and tone are, reaching the next message's prompt when changed (K299). The effect is measured from the record: topology calls per turn, by position and model.

## 11. After these

Document work, on the same form-and-pane layer.

- **Adversarial reviewer.** `adversarial_pair` made real: a `document` (path) and a `scope` (what to attack) as required inputs, no 200-character cut, severity from the reviewer's reply, rounds bounded, the revised document and the findings as output. A driven run; view-only.
- **Pair coding.** A builder session with a standing reviewer, given a scope (a card), not a whole project: the composite's `run_id` crash fixed, the reviewer driven by the topology on a schedule as an autonomous build's is. The person works with the builder, so its pane is interactive; the topology writes the reviewer's messages, so its pane is view-only (§4).

## 12. Open for the Architect

The 2026-09-24 note (point 10) says the autonomous build is built by copying the session topology and modifying the copy. Round 2 found the modification is one change at the turn's end, which one topology body can carry for build, autonomous build and swarm workers, at the cost of departing from the note's stated method. Copy, or one body with a drive change?

## 13. The next step

The shared layer and Build. The cards, in order:

1. **Every workspace a repository; worktrees in the kernel.** Opening a session runs `git init` and a first commit in a workspace that is not a repository. `SessionRegistry.create` makes the worktree and branch for `workspace_shape = worktree`; the server's helper moves; tests move with it.
2. **The form.** `[inputs]` with `required` and `from`; one generated tool per topology; `list_applications` returns the inputs; one validation for tool and server.
3. **Runs as the caller's background work.** Immediate return with the run's id; the end event in the caller's record before its next step; `stop_owner` on interrupt and end; parent provenance on every run's baseline; `wait` honoured.
4. **The driven session.** `check`, `continue` and `BuildEnded` on the session topology's turn end; the gate core running in a directory.
5. **Build.** Manifest, form, output event; a worktree from `base`; stall rules.
6. **Panes.** A run's start opens a pane bound to it, view-only when driven; a window per run with parts.
7. **Observation.** A real session calls `build` on a real card in a real repository; the branch passes the card's `done`; the pane showed the run as it went.

Then delegate as a session child, then autonomous build, then swarm, then the topologies control and the document topologies.

