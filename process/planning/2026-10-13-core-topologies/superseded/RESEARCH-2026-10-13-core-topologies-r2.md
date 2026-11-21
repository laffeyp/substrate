# RESEARCH: the core topologies — round 2, checked against the code

*2026-10-13. Round 1 (`RESEARCH-2026-10-13-core-topologies.md`) stays on disk. This round reads the code each part of round 1 rests on — `tool_loop/substrate_tools.py`, `applications/registry.py`, the server's run, composite and worktree code (`substrate-ui/server.py`), `tool_loop/delegate.py`, the session topology's turn end (`topologies/session/__init__.py`), `tool_loop/background.py`, `coding_flow/gate.py`, and the UI's panes (`substrate-ui/web/reveal_component.ts`) — and corrects round 1, records what it missed, and settles the design where the code makes it plain.*

## 1. Corrections to round 1

- **No session gets a worktree.** Round 1 said a session on a git repo gets one (spec r15 §9c, Mode 2). The helper exists (`server.py:1930`, `_session_worktree`: a branch `substrate/<session>` at `~/.substrate/sessions/wt/<repo>-<session>`), with a read-only diff beside it (`_worktree_diff`), and both are tested. Nothing calls `_session_worktree` outside the tests. `workspace_shape = "worktree"` is a label `_classify_workspace_shape` puts on a picked folder that has a `.git`. A delegate child given `workspace_shape: worktree` gets the label and no worktree.
- **The form exists on the server and is hidden from the model.** Round 1 said nothing forces any field. The server does refuse a call missing a field that has no default, naming it (`_validate_topology_inputs`, `server.py:628`). But the model cannot see the fields: `list_applications` returns name, description, run shape and output kind (`substrate_tools.py:709`), never `inputs_schema`, and `run_topology`'s schema types `inputs` as a bare object. The model learns a required field only by being refused.
- **A delegate fan-out child runs the stand-in, not a model, unless told.** `driver = spec.get("driver") or "deterministic"` (`delegate.py:373`). Its guidance bundle defaults to `standard` whatever the model's class, and its `steps` is always -1.

## 2. What the code adds

**Delegate is four tools in one.** A named standing session, a different-model child, a child given a slice of the parent's record, and a fresh child are four paths (`delegate.py:661–811`). Two run real sessions through the registry (the standing session and the `children` fan-out: `SessionRegistry.create` + `turn_sync`). Three run a bare `tool_loop` on a worker thread with its own event loop: no session id, no manifest, no registry entry, a 6-step cap (`child_max_steps`), and a workspace in a private subfolder (`delegate-runs/d1-cN/workspace`), not the parent's tree as spec §9c says.

**Every topology call blocks the caller's turn, or makes the model poll.** `delegate` blocks until the child stops. `run_topology` blocks by default; with `await_completion=false` it returns a run id the model must poll with `run_topology_poll`, held in a per-boot dictionary (`app.topology_runs`). Substrate already has the better shape for work that ends later: a background command belongs to an owner, its end is written to the owner's record as `BackgroundTaskEnded` before the model's next step and told once, and `stop_owner` ends every task an owner holds (`tool_loop/background.py`, session vocabulary).

**A topology run works in a temp folder.** `_topology_run` makes `tempfile.mkdtemp(prefix="substrate-<name>-")`, runs there and deletes it (`server.py:3544`). Its record goes to the shared runs directory with only a name: no parent session, no parent seq. Delegate does set `parent_session_id` and `parent_seq_at_call` on its child's baseline (`_with_baseline`); `run_topology` does not.

**The output is a guess.** `_extract_terminal_output` returns the payload of the last event whose kind does not start with `substrate.`. For a session-shaped run the last such event is `Returned` or a language event, not an answer.

**The run shape already names the pane.** `ApplicationRuns` has three members: `one-shot`, `session`, `session_composite` (`registry.py:44`). A one-shot run is a record a pane can follow; a session or a composite is one or more registry sessions a pane can bind.

**`required` exists on slots and nothing reads it.** `SlotSpec.required` (`registry.py:90`) has no consumer since sprint 065; inputs mark required by leaving out a default.

**A session's turn ends in one place.** The `return` producer writes `Returned`; termination pauses on it and resumes on the next `UserMessage` (`pause_await_input`, `session/__init__.py:1622`). A `UserMessage` can already be written from inside the topology: the `first_message` producer does it on a fresh record (line 432).

**The gate exists and runs on parsed files.** `coding_flow.gate.run_gate` runs a shell command, takes its exit code as the truth, kills the process group, and normalises the output (`GateResult{passed, returncode, summary}`). It writes a reply's fenced files into a throwaway sandbox first and stops at 60 seconds.

**The UI's child view is prototype data.** The meta panel's descent into a delegate child draws from a hard-coded `demoDescentChildren` table (`reveal_component.ts:1155`), whose entries carry a `talkable` flag. A pane can follow a real record (`SessionController.attachRecordRoot`), and a pane binds a real session, but nothing opens a pane when a run starts. A window holds at most eight panes (`_split`, line 788).

## 3. The design, settled by the code

**One kind of worker: the session.** Every topology part that does model work over turns runs as a registry session: build, each swarm worker, the autonomous builder and its reviewer, every delegate child. A session already has an id, a manifest, a record, interrupt, end, and a pane that binds it. One-shot topologies that do no turn-taking work (`code_review`, `research_sweep`) stay plain runs. The bare `tool_loop` child goes.

**Interactive or view-only is who writes the next message.** A session whose next `UserMessage` comes from a person is interactive; its pane has the input bar. A session whose next `UserMessage` comes from its own topology is driven; its pane is view-only. The flag is a fact on the record, not a pane setting: a driven session's messages carry the producer that wrote them.

**A driven session is the session topology with one change at the turn's end.** On `Returned`, a `check` producer runs the run's done command in its workspace and writes the result; a `continue` producer then writes the next `UserMessage` (the continuation, or for an autonomous build every n-th time the reviewer's reply with "analyze, verify, apply"), or an end producer writes `BuildEnded`. Termination finalises on `BuildEnded` instead of pausing on `Returned`. Everything the run does is on its record.

**A run started from a session is the session's background work.** The call returns at once with the run's session id, and the run's pane opens. Its end is written to the caller's record as an event, told to the model before its next step once, as `BackgroundTaskEnded` is. Interrupting or ending the caller ends the run (`stop_owner`). The form has a `wait` field for the case that wants the answer in the same turn: default true for `delegate`, false for `build`, `autonomous_build` and `swarm`. Polling goes.

**The form is one table, read by both sides.** The manifest's `[inputs]` gains `required = true` and `from = "session.workspace" | "session.driver" | "session.guidance"`. The same table produces each topology's tool schema (one tool per topology, its required fields in `required`), fills the session defaults, and validates on the server. `list_applications` returns it.

**The output is a declared kind.** Each manifest names its output event kind; the tool returns that event's payload. No guessing from the tail.

**Every run records where it came from.** `parent_session_id` and `parent_seq_at_call` go on every run's baseline, as delegate does now.

**Worktrees come from the kernel.** `_session_worktree` moves into the session registry: creating a session with `workspace_shape = worktree` on a repository makes the worktree and branch. `_worktree_diff` stays the "what did it change" read. Build and swarm workers ask for it; delegate children take the parent's workspace (spec §9c) unless the call isolates them.

**The done check is the gate, run in place.** `run_gate`'s core (exit code as truth, process-group kill, normalised output) runs a command in a directory, with the limit the form gives, so a build's `done` runs in its worktree.

**The pane follows the run's shape.** A one-shot run opens a view-only pane on its record. A session run opens a pane bound to the session, view-only when driven. A run with parts opens a window with a pane per part; past eight parts, the window shows the integrator and the running workers.

## 4. What changes in round 1's topologies

- **Build** is one driven session in a worktree: the form of round 1 §4, the `check` and `continue` producers, `BuildEnded{status, branch, commits, diff_stat, done}` as its output event, `wait = false`.
- **Autonomous build** is one driven builder session and one standing reviewer session, as round 1 §5; the `continue` producer sends the reviewer's reply on the schedule. The 2026-09-24 note says to build it by copying the session topology; the code shows the copy would differ from the original only in its turn end, which the drive change above covers with one topology body.
- **Swarm** is a one-shot run that opens worker sessions (each a Build) and integrates their branches, as round 1 §6.
- **Delegate** is a session child always: the fan-out path with one child is the single case. Its driver defaults to the parent's, its bundle to the model's class level, its workspace to the parent's; its pane is interactive; `wait = true`.

## 5. Open for the Architect

The 2026-09-24 note says the autonomous build is built by copying the session topology and modifying the copy. Round 2 finds the modification is one change at the turn's end, which one topology body can carry for build, autonomous build and swarm workers, at the cost of departing from the note's stated method. Copy, or one body with a drive change?

## 6. The next step, revised

The shared layer and Build. The cards, in order:

1. **Worktrees in the kernel.** `SessionRegistry.create` makes the worktree and branch for `workspace_shape = worktree` on a repository; the server's helper moves; tests move with it.
2. **The form.** `[inputs]` with `required` and `from`; one generated tool per topology; `list_applications` returns the inputs; one validation for tool and server.
3. **Runs as the caller's background work.** Immediate return with the run's id; the end event in the caller's record before its next step; `stop_owner` on interrupt and end; parent provenance on every run's baseline; `wait` honoured.
4. **The driven session.** `check`, `continue` and `BuildEnded` on the session topology's turn end; the gate core running in a directory.
5. **Build.** Manifest, form, output event; a worktree from `base`; stall rules.
6. **Panes.** A run's start opens a pane bound to it, view-only when driven; a window per run with parts.
7. **Observation.** A real session calls `build` on a real card in a real repository; the branch passes the card's `done`; the pane showed the run as it went.

Then delegate as a session child, then autonomous build, then swarm, then the topologies control and the document topologies.
