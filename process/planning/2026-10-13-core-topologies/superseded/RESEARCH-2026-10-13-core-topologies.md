# RESEARCH: the core topologies — build, autonomous build, swarm, delegate

*2026-10-13. Brings Substrate's prior topology work together and sets out the software-engineering topologies a session needs first, then the document ones after them. Sources: the topology audit (`process/planning/AUDIT-2026-10-11-topologies.md`), the autonomous build papers (`substrate-ui/process/methodology/2026-09-24-autonomous-build-topology.md`, the latest, and `current-design-direction/product-spec/autonomous-build-topology/PRODUCT-SPEC-2026-09-11-autonomous-build-topology-round17.md`), the daily-driver spec round 15 §5, §6, §8 and §9c, the delegation memo (`substrate-ui/process/planning/delegation-research-r5.md`), and the code named below.*

## 1. What a topology is here

A topology is a function a session calls. It has four parts.

- **A form.** The tool's schema lists every input. Required fields have no default, so the calling model cannot leave them out; the tool refuses a call that does. The remaining fields fill from the calling session (its workspace, its driver, its guidance level) or from the topology's own defaults. The session model and the user settle the inputs together before the call; the call then loads them and runs.
- **A record.** Every run writes its own record, linked to the caller's: the caller's `ToolResult` carries the child's record root, and the child's `RunStarted.baseline` carries the parent session and seq (spec r15 §9b).
- **An output.** A typed result returned to the caller: what was made, where it is, and whether the run met its own end condition.
- **A pane.** Every run opens a pane in the caller's window, or a window of its own when it runs several parts at once. The pane is interactive or view-only by type: a topology that is a session (delegate, a standing reviewer) takes the user's input like any session; a topology that runs to an end on its own (build, autonomous build, swarm) is view-only, and the user watches it work.

`delegate` stays the open-ended case: a child session given a task in prose. The topologies below are narrower on purpose. Each takes a fixed form and does one kind of work.

## 2. What exists

**The function shape is half built.** An application manifest already declares typed inputs with defaults (`topologies/applications/code_review.manifest.toml`: `repo` required; `ref = "HEAD~1"`, `quorum = 3` and seven model fields defaulted). `run_topology(name, inputs)` runs a manifest's topology and returns its output (`tool_loop/substrate_tools.py:207`). The audit found the gaps:

- The session is offered 18 names by `list_topologies` and can run 3 (`code_review`, `best_of_n_verified`, `research_sweep`).
- The output is the last event's payload (`_extract_terminal_output`). It is the whole answer only for `research_sweep`; `best_of_n_verified` returns `{round, slot}`, not the answer.
- Roles default to `kimi-k2.6:cloud` and `claude` whatever the session runs on.
- The `[inputs]` table is not turned into the tool's schema: the model sees one `inputs: object` and nothing forces any field.
- `pair_coding` crashes from a session: the composite answers without a `run_id` and `substrate_tools.py:163` reads `response["run_id"]`.

**Delegate is built and unused.** `tool_loop/delegate.py` runs a child to an answer with its own record, caps depth (5), fan-out (16) and tree size (64), and fans out to parallel child sessions through `children`, each of which can take `workspace_shape: worktree`. Across the 86 sessions the audit counted, no model called it. Its default child stops after 6 steps (`child_max_steps=6`), too few for work that edits and tests code.

**Worktrees exist for sessions.** A session opened on a git repo gets a worktree on branch `substrate/<session-name>` (spec r15 §9c, Mode 2; `session_registry.py:86`).

**The autonomous build topology is specified, not built.** Two papers. Round 17 of the product spec (2026-09-11) gives five steps (initiation, continuation, on-track review, full review, follow-up), verbatim prompts, a schedule (on-track every second builder stop, full every five closed cards) and a halt on a follow-up turn cap. The methodology note of 2026-09-24 is later and simpler, and it governs where the two differ: it is the session topology copied and changed in three places — the input is fixed (a roadmap, the sprint cards, a prompt of a fixed best-practice part and a project part); every return to the user is answered by a standing auto-reply; every n-th return goes to a standing reviewer instead, whose review comes back with "analyze, verify, apply" appended. It ends on the last card or on measured lack of progress, and it can be called from a session or on its own.

**`coding_flow` is a working best-of-N loop with a real gate** (`ruff check && mypy --strict && pytest`), outside the bundled list and with no session path.

**The decomposition and pair topologies are toys.** `recursive_decomposition`'s planner calls no model. `adversarial_pair` has no task input, cuts each artifact at 200 characters and draws severity from a hash. `pair_coding_chunked` discards its driver's reply.

**The UI can follow any record.** A pane controller attaches to a record by path (`SessionController.attachRecordRoot`, `client.streamRecordByPath`), which delegate descent uses today. Panes split (⌘D) and windows open (⌘N) on one backend. No pane opens by itself when a run starts.

**Guidance already splits models by class.** `topologies/session/model_class.py`: CLI harness agents and Ollama models of 70 B parameters or more are `large` (high level); 14–70 B are `medium`; under 14 B are `small` (low level, short role prompt).

## 3. The shared layer

Every topology below rests on four things, built once.

1. **Form from manifest.** A topology's manifest declares its inputs with type, `required` or a default, and a source for session defaults (`from = "session.workspace"`, `"session.driver"`, `"session.guidance"`). The tool's schema is generated from it: one tool per topology (`build`, `swarm`, `autonomous_build`), each with its own required fields, in place of one `run_topology(name, inputs: object)`. A call missing a required field is refused with the field's name.
2. **Typed output.** Each topology declares its output fields and emits them in one terminal event; the tool returns that event's payload and the record root. No topology answers with a pointer to go and read its record.
3. **Models follow the caller.** A role's model defaults to the session's driver; a field overrides it.
4. **A pane per run.** When a run starts, the server tells the caller's window, and the UI opens a pane bound to the run's record: view-only for run-to-end topologies, interactive for sessions. A run with parts (a swarm's workers, an autonomous build's builder and reviewer) opens a window with one pane per part. The caller's own pane shows the call as a row that names the run and focuses its pane on ↵.

## 4. Build

One card, one worktree, one result.

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

**Run.** A new worktree on `substrate/build/<id>` from `base`. The worker is the session topology with the return-to-user step replaced by a fixed continuation, as in the autonomous build note: it never waits for a person. Its first message is composed from the form. Each time the worker stops, the topology runs `done` itself in the worktree and records the exit codes; the card closes when they pass, so the worker's own say-so never closes it. The run ends `done`, or `stalled` when the step budget runs out or a set number of stops pass with no new commit and no change in `done`'s output, or `failed` on an error.

**Output.** `{status, branch, commits, diff_stat, done: [{command, exit, tail}], summary, record}`.

**Pane.** View-only, in the caller's window.

## 5. Autonomous build

The 2026-09-24 note, built as written: the session topology copied, with a fixed input, the auto-reply, and the standing reviewer every n-th return. Round 17 supplies the detail the note leaves open (the prompts' outlines, the on-track and full reviews, the follow-up and its cap).

**Form.** `roadmap` (path, required), `cards` (directory or list, required), `project_prompt` (the variable part, required), `repo`, `base`, `model` and `reviewer_model` (defaults from the session), `review_every` (default 2), `full_review_every_cards` (default 5).

**Run.** One worktree for the whole build; the builder closes cards in order and may add cards. Each card's `done` is checked by the topology as in Build. The reviewer is a standing session opened with the builder, reviewing for drift against the roadmap, the cards, SDD, best practice and the project's conventions; it may propose new cards or a changed roadmap. Ends on the last card closed, or on no card closing in a set number of builder stops.

**Output.** `{status, branch, cards: [{id, status}], reviews, record}`.

**Pane.** A window with two view-only panes, builder and reviewer.

## 6. Swarm

Divide, run in parallel, integrate. Parallel writing in separate worktrees; integration on one branch, one merge at a time.

**Form.** Either `cards` with their `depends_on`, each card a Build form, or a `problem` statement. Plus `repo`, `base`, `worker_model` (default the session's driver; a small model is the intended case), `planner_model` (default the session's driver), `parallel` (default 4).

**Run.**

1. **Plan**, only when given a `problem`: one producer on `planner_model` writes a roadmap and cards with dependencies into the record. The caller sees them in the swarm's window before workers start. Given cards, this step does not run; the session and the user have already done it.
2. **Build.** Each card whose dependencies have merged runs as a Build on its own worktree from the integration branch's current head, up to `parallel` at once.
3. **Integrate.** One producer merges each finished branch into `substrate/swarm/<id>` in dependency order and reruns that card's `done` after the merge. A conflict or a failed check sends the card back as a new Build from the new head, a bounded number of times, then marks it `failed`.

**Output.** `{status, branch, cards: [{id, status, branch}], record}`.

**Pane.** A window with one view-only pane per running worker and one for the integrator.

## 7. Delegate, made real

Delegate stays prose-driven and interactive. To make it real:

- The default child is a session with the parent's suite and no 6-step stop; a step budget sized for real work, and the interrupt, end it.
- The child opens as an interactive pane in the caller's window, so the user can watch it and type to it.
- Its answer folds back as today; with `children`, each child gets its own pane.
- An observation test on a real model: a session delegates a task that edits and tests code, and the child's result is checked, not just the call.

## 8. What each model is given

The split by model class already used for guidance decides what a worker receives.

- **Large** (`harness_agent`, `large`): the roadmap and the cards. It can run Autonomous build and call Swarm itself.
- **Medium:** the card in full and the roadmap section it belongs to.
- **Small:** the card cut to `goal`, `scope`, `done` and the named context files, in the low guidance level; nothing else enters an 8,192-token window.

The topology composes the worker's first message from the form by the worker's class. The same card runs on any class; the form is the same and the message differs.

## 9. How readily a session uses them

A session control beside length and tone: **topologies**, with positions `off` (the tools are not offered), `ask` (the model proposes a call and waits for the user's yes), `use` (the model calls a topology when a task fits a form), `prefer` (the model splits work into topology calls wherever it fits). Each position is a text in the session prompt, written and changed as length and tone are, reaching the next message's prompt when changed (K299). The effect is measured from the record: topology calls per turn, by position and model.

## 10. After these

Document work, on the same form-and-pane layer.

- **Adversarial reviewer.** `adversarial_pair` made real: a `document` (path) and a `scope` (what to attack) as required inputs, no 200-character cut, severity from the reviewer's reply, rounds bounded, the revised document and the findings as output. View-only.
- **Pair coding.** A builder session with a standing reviewer: the composite's `run_id` crash fixed and the reviewer driven by the topology on a schedule, as Autonomous build does. Given a scope (a card), not a whole project. Both panes interactive.

## 11. The next step

The shared layer and Build, together. Build is the unit the other two reuse: a swarm runs Builds and an integrator, and an autonomous build is one long Build with a reviewer. The form-from-manifest, the typed output and the pane per run are what Build needs to be callable and watchable, and every later topology needs the same three. The first cards:

1. Manifest inputs with `required` and session sources, generated into one tool per topology; refusal names the missing field.
2. The terminal output event and its return to the caller.
3. A run opens a view-only pane bound to its record; a session-type run opens an interactive pane.
4. Build: worktree, continuation, the topology's own `done` check, stall detection, the output.
5. An observation test: a real session calls `build` on a real card in a real repository and the branch passes the card's `done`.

Then Autonomous build, then Swarm, then the delegate changes and the topologies control, then the document topologies.
