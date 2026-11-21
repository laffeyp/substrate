# RESEARCH: the core topologies — build, autonomous build, swarm, delegate (round 4)

*2026-10-13. Round 4 replaces rounds 1 to 3 (`RESEARCH-2026-10-13-core-topologies.md`, `-r2.md`, `-r3.md`), which stay on disk. It is the whole design in one document, rewritten for plain reading, with everything the earlier rounds found kept.*

*Sources. The topology audit (`process/planning/AUDIT-2026-10-11-topologies.md`). The autonomous build note (`substrate-ui/process/methodology/2026-09-24-autonomous-build-topology.md`), which the Architect named as the governing version; the earlier and longer product-spec rounds of 2026-09-11 are not used. The daily-driver spec, round 15, §5, §6, §8 and §9c (`current-design-direction/product-spec/PRODUCT-SPEC-2026-08-17-round15.md`). The delegation memo (`substrate-ui/process/planning/delegation-research-r5.md`). The SDD kit 3 (`sdd-kit-3/AGENTS.md`). And the code: `topologies/tool_loop/substrate_tools.py`, `topologies/applications/registry.py`, `topologies/tool_loop/delegate.py`, `topologies/tool_loop/background.py`, `topologies/session/__init__.py`, `topologies/session/model_class.py`, `topologies/coding_flow/gate.py`, `substrate-ui/server.py`, and `substrate-ui/web/reveal_component.ts`.*

## 1. What this document is for

A Substrate session can already talk to a model, run tools and keep a record. What it cannot yet do is hand a piece of software work to something else and get it back done. This document sets out four topologies that do that, and the shared machinery they need:

- **Build:** one sprint card, worked in its own git worktree until the card's own checks pass.
- **Autonomous build:** a roadmap and its sprint cards, worked through in order by a builder that never waits for a person, with a standing reviewer correcting drift.
- **Swarm:** many cards worked in parallel by many builders, often small models, and merged into one branch.
- **Delegate:** the open-ended case that exists today, a child session given a task in prose, made reliable.

After these come two topologies for document work, an adversarial reviewer and pair coding, built on the same machinery.

## 2. What a topology is in Substrate

A topology is a function a session calls. It has four parts.

**A form.** The tool the model calls lists every input the topology takes. Some inputs are required and have no default; the model cannot leave them out, because the tool refuses the call and names the missing field. The rest fill themselves: from the calling session (its workspace, its model, its guidance level) or from the topology's own defaults. The session model and the user settle the inputs together first; the call then loads them and the work runs. A sprint card is the natural form for software work, so the forms below are shaped like cards.

**A record.** Every run writes its own record, like any session, and that record names the session and the point in its record that started it.

**An output.** A run ends with one typed event saying what was made, where it is, and whether the run met its own end condition. That event is what the caller gets back.

**A pane.** Every run opens a pane in the caller's window, or a window of its own when it has several parts. The pane is interactive or view-only, and the rule is simple: if a person writes the run's next message, the pane takes input; if the topology writes it, the pane is view-only and the user watches. Delegate children are interactive. Build, autonomous build and swarm runs are view-only.

## 3. What exists today

### 3.1 The topology tools

A session has two tools for topologies. `list_topologies` returns 18 names: the bundled demonstration topologies in `topologies/bundled.py`. `run_topology(name, inputs)` runs only applications, the topologies with a manifest in `topologies/applications/`, and there are five of those, of which three can actually run from a session (`code_review`, `best_of_n_verified`, `research_sweep`). So a session is offered 18 names and can run 3. The one recorded attempt shows the cost: in session `s_ab960f90985d49f796fd3754` the model tried `session`, then `daily`, then `tool_loop`, and got a refusal each time.

`run_topology` blocks the session's turn until the run finishes. With `await_completion=false` it returns a run id instead, which the model must then poll with `run_topology_poll`; the run ids live in a dictionary in the server's memory (`app.topology_runs`) and are lost on restart.

When a run finishes, the tool returns the payload of the last event in its record whose kind does not start with `substrate.` (`_extract_terminal_output`). That is the answer only for `research_sweep`. `best_of_n_verified` returns `{round, slot}` and not the chosen solution. A session-shaped run would return its last `Returned` or a language event.

### 3.2 Application manifests: a form the model never sees

Each application has a manifest with an `[inputs]` table, for example `code_review.manifest.toml`: `repo` with no default, and `ref = "HEAD~1"`, `quorum = 3` and seven model fields with defaults. The server treats a field without a default as required and refuses a call that leaves it out, naming the field (`_validate_topology_inputs`, `server.py:628`). So the form exists, on the server.

The model never sees it. `list_applications` returns each application's name, description, run shape and output kind, and not its inputs (`substrate_tools.py:709`). `run_topology`'s own schema types `inputs` as an untyped object. A model learns a required field only by being refused.

Every manifest defaults its model roles to `kimi-k2.6:cloud` and `claude`, whatever model the calling session runs on. A session on codex that calls `code_review` runs kimi and claude.

Manifests also have a `[slots]` table whose entries can say `required`; nothing has read that flag since sprint 065 (`SlotSpec.required`, `registry.py:90`).

### 3.3 How a topology run is set up

`_topology_run` (`server.py:3482`) makes a temporary folder (`tempfile.mkdtemp`), runs the topology there and deletes the folder when it ends. The run's record goes into the shared runs directory under a fresh id, and its first event carries only the topology's name: nothing records which session started it or when. The run never sees the session's workspace.

`pair_coding` is a "session composite": it opens two sessions and answers with their ids. The tool code then reads a `run_id` the answer does not have (`substrate_tools.py:163`), so every call to it from a session fails.

Each application declares a run shape (`ApplicationRuns`, `registry.py:44`): `one-shot` (a run that finishes on its own), `session` (opened through the session API instead) or `session_composite` (several sessions opened together).

### 3.4 Delegate

`delegate` (`tool_loop/delegate.py`) hands a task to a child and folds the child's answer back into the caller's turn. It is built carefully: depth, fan-out and whole-tree caps (5, 16 and 64), interrupting the caller interrupts the child, and the child's record names its parent session and the point it was called from. It has never been used: across the 86 sessions the audit counted, no model called it.

It is four tools in one. A call with `child_session_name` sends the task to a named standing session. A call with `children` starts several new sessions in parallel. Both of these run real sessions through the session registry. The other two paths, a different model and a plain fresh child, run a bare `tool_loop` in a background thread instead: no session id, no manifest, no entry in the registry, nothing a pane could attach to and type into. That bare child stops after 6 model steps (`child_max_steps=6`), too few to edit code and run tests, and it works in a private folder under the call's delegation directory, not in the parent's workspace as spec §9c says children should.

The parallel path has its own faults. A child given no model runs the deterministic test stand-in, not a model (`driver = spec.get("driver") or "deterministic"`, `delegate.py:373`). Its guidance bundle defaults to `standard` whatever the model's class. Its step count is always reported as -1.

### 3.5 Workspaces and worktrees

Spec §9c says a session opened on a git repository works in its own git worktree, on a branch named for the session. The function that makes such a worktree exists in the server (`_session_worktree`, `server.py:1930`), along with a read-only "what did it change" diff (`_worktree_diff`), and both have tests. But nothing calls `_session_worktree` except the tests. Today no session gets a worktree. "worktree" as a workspace shape is only a label the server puts on a chosen folder that contains `.git`. A delegate child asked for `workspace_shape: worktree` gets the label and no worktree.

### 3.6 How a session's turn ends

The session topology (`topologies/session/__init__.py`, 1,701 lines) ends every turn the same way. When the model's reply ends the turn, or the model fails, or the user interrupts, the `return` producer writes a `Returned` event. The topology's termination rule then pauses the run until the next `UserMessage` arrives from outside (`pause_await_input`, line 1622). A `UserMessage` can also be written from inside the topology: the `first_message` producer already does this when a session opens with its first message (line 432).

### 3.7 Background work

Substrate already handles work that finishes later, for shell commands. A background command belongs to an owner, a session. When it ends, a `BackgroundTaskEnded` event is written to that session's record before the model's next step, and the model is told once. Ending or interrupting the session stops everything it owns (`stop_owner`, `tool_loop/background.py`).

### 3.8 The gate

`coding_flow/gate.py` runs a shell command and takes its exit code as the truth, kills the command's whole process group when it is stopped, and normalises the output so the same result reads the same way twice (`GateResult{passed, returncode, summary}`). It was written for `coding_flow`, so it first writes the files from a model's reply into a throwaway folder and runs there, and it stops after 60 seconds.

### 3.9 Model classes and guidance

`topologies/session/model_class.py` sorts every model into a class, and the class sets a default guidance level. Command-line agents (`claude`, `codex`, `cursor-agent`) and Ollama models of 70 billion parameters or more are `large` and get the high level. Models from 14 to 70 billion are `medium`. Models under 14 billion are `small` and get the low level, because their windows are small: 8,192 tokens for `llama3:8b`.

### 3.10 The UI

Panes split with ⌘D and new windows open with ⌘N, all on one server. A window holds at most eight panes (`_split`, `reveal_component.ts:788`). A pane can bind a session, and a pane's controller can follow any record by its path (`SessionController.attachRecordRoot`). Nothing opens a pane when a run starts. The meta panel's view of a delegate's children is prototype data, drawn from a fixed table (`demoDescentChildren`, line 1155); its entries already carry a `talkable` flag, the same interactive or view-only split this design uses.

### 3.11 The other topologies the session is offered

The audit found most of the bundled topologies are demonstrations, not tools. `recursive_decomposition`'s planner calls no model. `adversarial_pair` has no task input, cuts each draft at 200 characters and draws its severity from a hash of the text. `pair_coding_chunked` calls its model and throws the reply away. `coding_flow`, a real best-of-N loop with a real gate, is not in the bundled list and cannot be reached from a session. The one topology with a measured result on real work is the SWE-bench solver (108 of 300 SWE-bench Lite instances on qwen3-coder:480b-cloud, 2026-06-27), and it too has no session path.

## 4. The shared design

Every topology in this document rests on the rules in this section. Each is built once.

### 4.1 Every worker is a session

Every part of a run that does model work over several turns runs as a session in the session registry: a build, each swarm worker, the autonomous builder and its reviewer, every delegate child. A session already has everything a worker needs: an id, a manifest on disk, a record, interrupt and end, a workspace, and a pane that can bind it. The bare `tool_loop` child in delegate is retired. Topologies that do no turn-taking work of their own, such as `code_review` and `research_sweep`, stay plain one-shot runs.

### 4.2 Interactive or view-only

A session whose next message comes from a person is interactive. A session whose next message comes from its own topology is driven. This is a fact the record already holds: every event names the producer that wrote it, so a message written by the `continue` producer is told apart from one a person sent. The pane reads it: an interactive session's pane has the input bar, a driven session's pane does not.

### 4.3 The driven session

A driven session behaves exactly like a session until a turn ends. Then, in place of pausing for a person:

1. The `check` producer runs the run's done commands in its workspace (§4.9) and writes a `DoneChecked` event with each command, its exit code and the tail of its output.
2. If the run's end condition is met, an end producer writes the run's end event (`BuildEnded`, `AutonomousBuildEnded`), and the run finalises on it.
3. Otherwise the `continue` producer writes the next `UserMessage`: the topology's fixed continuation, or, for an autonomous build on a review turn, the reviewer's reply (§6).

Everything a driven run does is on its record: each check, each message the topology wrote, the end and why.

Section 9 asks whether this is built as an option on the one session topology or as a copy of it.

### 4.4 A run started by a session is the session's background work

A call to `build`, `autonomous_build` or `swarm` returns at once. It writes a `TopologyRunStarted` event to the caller's record, naming the run, its session or sessions, and whether each is driven, and the run's pane opens (§4.11). The caller's model keeps working, or ends its turn.

When the run ends, a `TopologyRunEnded` event is written to the caller's record, carrying the run's output, before the caller's model takes its next step, and the model is told once. This is how `BackgroundTaskEnded` already works. If the caller's session is waiting for a person when the run ends, the event waits in the record and the model reads it on its next turn.

Interrupting or ending the caller's session stops its runs, as `stop_owner` stops background commands.

Each form has a `wait` field. With `wait` true the call blocks until the run ends and returns the output in the same turn. `wait` defaults to true for `delegate`, which is how delegate works today, and to false for `build`, `autonomous_build` and `swarm`, which can run for hours. Polling, and `run_topology_poll`, are retired.

`TopologyRunStarted`, `TopologyRunEnded` and `DoneChecked` are new kinds, so they go through the session vocabulary as every kind does.

### 4.5 One form, read everywhere

A topology's manifest is the single home of its form. Its `[inputs]` table gains two keys: `required = true` for a field the caller must fill, and `from` for a field that fills itself from the caller's session (`"session.workspace"`, `"session.driver"`, `"session.guidance"`). The same table then does three jobs:

- It produces the topology's tool. Each topology that a session can call gets its own tool, named for it (`build`, `autonomous_build`, `swarm`), whose JSON schema lists the fields, their descriptions and types, and the required ones in `required`. A model's tool-calling interface shows these fields before the call.
- It fills the defaults: `from` fields from the session, the rest from the manifest.
- It validates the call on the server, as `_validate_topology_inputs` does now.

Once each callable topology has its own tool, `list_topologies` and `run_topology` leave the session's toolset. The demonstration topologies stay runnable from the command line. `list_applications`, if kept, returns each topology's inputs.

### 4.6 One declared output

Each manifest names its output event kind, and the topology writes exactly one event of that kind when it ends. The tool returns that event's payload. Nothing reads the tail of the record and guesses.

### 4.7 Every run records where it came from

Every run's first event carries `parent_session_id` and `parent_seq_at_call`, as delegate's children already do. A reader can go from the caller's record to the run and back.

### 4.8 Every workspace is a git repository

When a session opens on a workspace that is not a git repository, Substrate runs `git init` there and makes a first commit of what the folder holds. The default sandbox workspace starts as a repository. Branches and worktrees are then always available, for every session and every run, and every change a model makes can be seen as a diff.

Worktrees move into the kernel. `_session_worktree` moves from the server into the session registry, so that creating a session with `workspace_shape = worktree` makes the worktree and its branch. `_worktree_diff` stays as the read of what a run changed. Builds and swarm workers each get a worktree. Delegate children work in the caller's workspace, as spec §9c says, unless the call isolates them.

### 4.9 The done check

A run's done commands are the observation contract of its card: the commands whose success means the work is done. The `check` producer runs them with the gate's core (§3.8): exit code as the truth, the whole process group stopped on interrupt, the output normalised. It runs them in the run's worktree, not a throwaway folder, and with a time limit taken from the form, since a real test suite can run far longer than 60 seconds. The model's own statement that it is done never closes a card; the check does.

### 4.10 Models follow the caller, and each class gets what it can hold

Every model field in a form defaults to the calling session's model. A form field overrides it.

What a worker receives depends on its model's class (§3.9). The topology composes the worker's first message from the same form in three ways:

- **Large:** the card in full, the roadmap it belongs to, and the SDD kit 3's working agreement. A large model can also call an autonomous build or a swarm itself.
- **Medium:** the card in full and the section of the roadmap it belongs to.
- **Small:** the card cut to its goal, its scope, its done commands and the files named in its context, at the low guidance level, because nothing more fits an 8,192-token window.

The same card runs on any class. The form is the same; the message differs.

### 4.11 Panes and windows

When a `TopologyRunStarted` event reaches the caller's pane, the UI opens a pane for the run:

- One session (a build, a delegate child): a pane in the caller's window, bound to that session, view-only when the session is driven.
- Several sessions (an autonomous build, a swarm): a new window with one pane per session. A window holds eight panes; a swarm with more workers shows the integrator and the workers that are running.
- A one-shot run (`code_review`): a view-only pane following its record.

The caller's own pane shows the call as a row naming the run and its state; ↵ on that row focuses the run's pane. When the run ends, its pane stays open showing the finished run, marked ended, until the user closes it.

## 5. Build

One sprint card, worked in its own worktree until the card's checks pass. A driven session.

### 5.1 The form

| Field | Required | Default | What it is |
|---|---|---|---|
| `goal` | yes | — | What the card delivers, in a sentence or two. |
| `scope` | yes | — | The files and modules the work may touch. |
| `done` | yes | — | The commands whose success closes the card: its observation contract. |
| `context` | yes | — | Files, documents and records to read first. |
| `constraints` | no | none | Rules beyond the project's own: an API that must not change, a library not to use. |
| `repo` | no | the session's workspace | The repository to work in. |
| `base` | no | `HEAD` | The commit the worktree starts from. |
| `model` | no | the session's model | The worker's model. |
| `guidance` | no | the model's class level | The worker's guidance level. |
| `max_stops` | no | 40 | How many times the worker may end a turn before the run stops. |
| `stall_after` | no | 3 | Stops in a row with no new commit and no change in the checks before the run counts as stalled. |
| `check_timeout_s` | no | 1,800 | The time limit for one run of the done commands. |
| `wait` | no | false | Whether the call blocks until the run ends. |

### 5.2 The run

1. The registry makes a worktree on a new branch `substrate/build/<id>` from `base`, and opens a session there on `model`.
2. The topology writes the first message from the form, shaped by the model's class (§4.10): the card, and the instruction to work it until its done commands pass, committing as it goes.
3. The worker works: reads, edits, runs commands, commits.
4. Each time the worker ends a turn, the `check` producer runs `done` in the worktree.
5. If every command passes, the run ends `done`. Otherwise `continue` writes the continuation, which carries the failing commands' output, and the worker goes on.
6. The run ends `stalled` when `max_stops` is reached, or when `stall_after` stops in a row bring no new commit and no change in the checks' output. It ends `failed` on an error the session cannot continue past.

The build never merges. Its branch is the result; the caller reads the diff and decides.

### 5.3 The output

`BuildEnded{status, branch, commits, diff_stat, done: [{command, exit, tail}], summary, record}`. `status` is `done`, `stalled` or `failed`. `summary` is the worker's last reply.

### 5.4 The pane

A view-only pane in the caller's window.

## 6. Autonomous build

A roadmap and its cards, worked through in order by a builder that never waits for a person, with a standing reviewer correcting drift. This section follows the 2026-09-24 note point by point.

**The input** (note 1). The form: `roadmap` (a path, required), `cards` (a directory, required), `project_prompt` (what is specific to this project, required), and `repo`, `base`, `model` and `reviewer_model`, which default from the caller's session. `review_every` (default 3) sets how often the reviewer runs. The fixed part of the prompt is the same for every build:

- The SDD kit 3, read in full. `sdd-kit-3/AGENTS.md` is the builder's working agreement. The note's last point asked for a version of the kit with its halt-and-wait language taken out, for a builder that never waits; kit 3 already is that version. It replaced every halt with resolve-and-record: decide on stated grounds, write the decision down, say it, keep working ("no step in this kit waits for an Architect 'go'"). The one human touch left in it, a question only a person can answer, is recorded under `## Surfaced for review` and the builder keeps working.
- Software engineering best practice and the project's existing conventions.
- The roadmap, and every card in order.

**The automatic reply** (note 2). Whenever the builder ends a turn and no review is due, the `continue` producer writes a fixed reply in place of a person's. It answers the kinds of things a model says at the end of a turn, which rarely depend on the work: a question is answered by best practice and the kit; a report of progress is met with "continue". Then it points the builder at the current card, or the next one once the current card's checks pass.

**The review** (notes 3, 5, 6). On every `review_every`-th end of a turn the builder gets no automatic reply. The topology sends the reviewer a fixed prompt instead: review the work since the last review for drift, against the roadmap, the cards and their intent, the SDD kit, best practice and the project's conventions. The reviewer is a standing session opened with the builder and given the same kit. Its reply comes back to the topology, not to the builder. The topology appends `-- analyze, verify, apply` and sends the whole to the builder as its next message. A form switch, off by default, lets the reviewer also propose new cards, changed cards or a new roadmap; the note names this as the experiment to run.

**The end** (note 7). The run ends when the last card's checks pass, or when no card closes over a set number of the builder's turns, which is the measured lack of progress the note asks for. `AutonomousBuildEnded` records which, and the run returns to whatever started it. It is as suited to one epic's cards as to a whole project.

**Who starts it** (notes 4 and 8). A session starts it, once the user and the session's model have made the roadmap and cards together. It also runs on its own, from the command line or from another topology.

**Everything else** (note 9) is the session topology's behaviour.

**How it is built** (note 10). The note says to copy the session topology and change the copy. Section 9 asks the Architect about this.

**The output.** `AutonomousBuildEnded{status, branch, cards: [{id, status}], reviews, record}`.

**The panes.** A new window with two view-only panes, the builder and the reviewer.

## 7. Swarm

Many cards, worked in parallel by many builders, merged into one branch. The work is parallel; the merging is one merge at a time.

### 7.1 The form

Either `cards`, each a build form with an `id` and a `depends_on` list, or a `problem` statement. Plus `repo`, `base`, `worker_model` (default the session's model; small models are the intended case), `planner_model` (default the session's model), `parallel` (default 4), `retries` (default 2) and `wait` (default false).

### 7.2 The run

1. **Plan**, only when the form gives a `problem`. One producer on `planner_model` writes a roadmap and cards with their dependencies into the record, and they show in the swarm's window before any worker starts. When the form gives cards, there is no plan step: the session and the user have already planned.
2. **Integration branch.** The topology makes `substrate/swarm/<id>` from `base`.
3. **Build.** Every card whose dependencies have all merged runs as a build (§5) on its own worktree from the integration branch's current head, `parallel` at a time.
4. **Integrate.** One producer merges each finished branch into the integration branch, in dependency order, and runs that card's done commands again after the merge.
5. **Retry.** A merge conflict, or checks that fail after the merge, send the card back as a new build from the new head, with the conflict or the failure in its context, up to `retries` times. After that the card is marked `failed` and the cards that depend on it do not run.

### 7.3 The output

`SwarmEnded{status, branch, cards: [{id, status, branch}], record}`.

### 7.4 The panes

A new window with a view-only pane for each running worker and one for the integrator, at most eight (§4.11).

## 8. Delegate

Delegate stays the open-ended case, a child given a task in prose, and stays interactive. It becomes one shape: every child is a session, and a single child is the parallel path with one child.

- **Defaults.** The child's model is the caller's model, never the test stand-in. Its guidance bundle is its model's class level. Its workspace is the caller's workspace, unless the call isolates it. `wait` is true, so the answer folds back into the same turn as it does today; with `wait` false, it ends like any background run (§4.4).
- **No 6-step stop.** The child takes turns like any session, ended by its own reply, an interrupt, or the caller ending.
- **The pane.** An interactive pane in the caller's window, so the user can watch the child and write to it. With `children`, one pane per child.
- **The test.** A session on a real model delegates a task that edits and tests code, and the child's result is checked, not just the call.

## 9. Open question for the Architect

The note's point 10 says to build the autonomous build by copying the session topology and changing the copy. The session topology is one file, `topologies/session/__init__.py`, 1,701 lines. Build, autonomous build and the swarm's workers all need the same change to it, and only that change: at the end of a turn, check the work and write the next message, instead of pausing for a person (§4.3).

There are two ways to make that change:

- **Copy.** A new file that starts as a copy of the session topology, with the end of a turn changed. Two files of about 1,700 lines, which differ in one place and drift apart as either is changed.
- **Option.** One session topology with an option that turns on the driven end of a turn. One file; the driven end is about the size of the `first_message` producer plus a termination rule.

Which should it be: copy the session topology, or add an option to it?

## 10. How readily a session uses topologies

A new session setting beside length and tone, named **topologies**, with four positions:

- `off`: the topology tools are not offered.
- `ask`: the model proposes a call, with its filled form, and waits for the user's yes.
- `use`: the model calls a topology when a task fits one of the forms.
- `prefer`: the model looks for work it can hand to a topology and hands it off.

Each position is a text in the session's prompt, written and changed the way length and tone are, and a change reaches the prompt for the very next message (K299). Its effect is measured from the record: topology calls per turn, by position and by model.

## 11. After these: document topologies

On the same forms, records and panes.

- **Adversarial reviewer.** `adversarial_pair` made real. Required inputs: the `document` (a path) and the `scope` (what to attack). No 200-character cut; the severity comes from the reviewer's reply, not a hash; the rounds are bounded. The output is the revised document and the findings. A driven run, view-only.
- **Pair coding.** A builder session with a standing reviewer, given a scope (a card), not a whole project. The `run_id` crash fixed (§3.3); the reviewer is sent the builder's work on a schedule, as in an autonomous build. The user works with the builder, so its pane is interactive; the topology writes the reviewer's messages, so its pane is view-only.

## 12. The next step

The shared machinery and Build come first, together, because Build is the unit the rest reuse: a swarm runs builds and merges them, and an autonomous build is a long build with a reviewer. The cards, in order, each with what closes it:

1. **Every workspace a repository; worktrees in the kernel.** Opening a session runs `git init` and a first commit in a workspace that is not a repository. The session registry makes the worktree and branch for `workspace_shape = worktree`; `_session_worktree` and its tests move from the server. *Closed when* a session opened on a plain folder finds a repository with one commit, and a worktree session finds its own branch.
2. **The form.** `required` and `from` in `[inputs]`; one tool per callable topology, generated from its manifest; one validation shared by the tool and the server; `list_topologies` and `run_topology` out of the session's toolset. *Closed when* a model's tool list shows `build` with its required fields, and a call missing one is refused by name.
3. **Runs as background work.** `TopologyRunStarted` and `TopologyRunEnded` in the session vocabulary; the immediate return; the end event before the caller's next step; `stop_owner` on interrupt and end; parent provenance on every run; `wait`. *Closed when* a session starts a run, keeps working, and is told of the run's end once.
4. **The driven session.** `check`, `continue`, `DoneChecked` and the end event, on whichever of the two shapes §9 settles; the gate's core running in a directory with the form's time limit. *Closed when* a scripted worker's session ends `done` when its checks pass, and `stalled` when they never do.
5. **Build.** Its manifest, form, first message by model class, and `BuildEnded`. *Closed when* a deterministic build on a fixture repository ends `done` with its branch and diff.
6. **Panes.** A run's start opens its pane or window; view-only when driven; the caller's row with ↵ to focus. *Closed when* the app's gates see a build's pane open on its own, show the run, refuse typing, and stay after the end.
7. **The real test.** A session on a real model calls `build` on a real card in a real repository. *Closed when* the branch passes the card's done commands and the pane showed the run as it went.

Then delegate as a session child, then the autonomous build, then the swarm, then the topologies setting, then the document topologies.
