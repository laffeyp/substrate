# RESEARCH: the topologies that ship (round 11)

*2026-10-27. Round 11 follows round 10 (`RESEARCH-2026-10-25-core-topologies-r10.md`), which stays on disk. Round 10 audited every topology Substrate has and said which are rebuilt to work in a real session and which are cut from what a session can see. Round 11 keeps that audit and those shapes, and changes how each shipping topology is built: it starts as a copy of the session topology's files, and the copy's wiring is changed to the shape. Round 10 § 4.2 called this "point 10: composed, not copied". The 2026-09-24 note's point 10 says the opposite: "The build process for this will be to completely copy the session topology and then modify it." Round 11 follows the note. Every design is stated in Substrate's own parts: `producer_kind`, `view`, `trigger` with its predicate and policy, `route`, `initial`, `termination`, `instrument`. No part is new unless named as new.*

*Sources, read in full: research round 10; the autonomous build note (`substrate-ui/process/methodology/2026-09-24-autonomous-build-topology.md`); the before-distribution roadmap (`substrate-ui/process/planning/ROADMAP-2026-10-11-before-distribution.md`); the whole session package (`session/__init__.py`, `vocabulary.py`, `transcript.py`, `views.py`, `session_prompt_producer.py`, `ci.py`, `context_slice.py`, `context_windows.py`, `environment.py`, `handoff.py`, `interrupt_fragment_producer.py`, `model_class.py`, `roles.py`, `skills.py`, `mcp_channel.py`, the three language files, `prompts/`, `bundles/`, `skills/`, `records/ci_mode.record`); `runs/run.py`, `runs/build.py`, `runs/review.py`, `runs/hold.py`; `tool_loop/__init__.py`, `tools.py`, `background.py`, `kinds.py`, `agency.py`, `delegate.py`, `substrate_tools.py`; `session_registry.py`; `workspace.py`; `kernel/composition.py`; `bundled.py`; `app.py`; `best_of_n/`; `coding_flow/`; `adversarial_pair/`; `code_review/`; `debate/`; `conversation.py`; `applications/` (the four modules, `registry.py`, the five manifests); `substrate-ui/server.py`; `substrate/_daemon.py`. Read in part, by search: `substrate-ui/web/vm/session_controller.ts`, `vm/types.ts`, `reveal_component.ts` (the run listing and run panes).*

## 1. What a topology is, and what the session topology is

A topology is wiring the Substrate kernel runs and records: producers that do work and emit events, views over the event log, triggers that start a producer when a predicate holds, routes, initials, instruments, and a termination that ends the run.

The session topology is the one topology that works end to end today. Its wiring:

- **Producers:** model, tool, return, session_end, session_prompt, first_message, interrupt_fragment, skill_fragment, the optional language producer, and the `session_started` instrument.
- **Views:** results, user_turns, user_messages, returned_turns, fragment_cohort, session_settings, turn_history.
- **Termination:** daily, `any_of(pause_await_input(when Returned, resume UserMessage), finalise_on(SessionEnded))`; run mode (`runs/run.py`, `compose_run`), `any_of(finalise_on(ReportWritten), finalise_on(SessionEnded))`.
- **Around them:** the prompt build in `transcript.py`, the tool suite in `tool_loop/tools.py`, guidance bundles, role prompts, skills, the MCP channel.

The session topology is not already the other topologies. Each shape below differs from it in wiring: other producers, other triggers, other views, another termination.

## 2. How Substrate UI runs a topology today

Substrate UI hosts topologies on three paths. Each new topology runs on one of them.

- **A session a person drives.** `POST /api/session` registers a manifest; each `POST /api/session/<id>/turn` calls `SessionRegistry.turn_sync`, which builds the topology through `_build_session_topology_from_manifest` (`server.py:653`). That function always calls `session_topology(...)`. The manifest has no field that names another topology. Interrupts, parking, end, the SSE stream and the pane all hang off this path.
- **A run a session holds.** `build` and `review` call `RunTable.start(owner, run_id, topology, sessions, factory, record_root)` (`runs/hold.py`). It runs any factory on its own event loop in a worker thread and posts `TopologyRunStarted` into the caller's record. The app reads that event and opens a view-only pane per `RunSession` (`reveal_component.ts`, `_openRunPanes`; `session_controller.ts`, `attachRun`). `RunTable.stop` injects `SessionEndRequested(source=caller_stop)` into `sessions[0]`, so the run's first session must keep the session topology's end-on-end-request trigger. When the run ends, the caller's next model step reports it once (`drain_ended`, `run_notice`).
- **A one-shot application.** The `run_topology` tool calls the daemon over HTTP (`_daemon.run_topology`). `_topology_run` (`server.py:3563`) looks the name up in `_APP_BUILDERS` (`code_review`, `best_of_n_verified`, `research_sweep`) and runs it with `asyncio.run` on the request thread when `await_completion` is true, the default, or on a bare thread kept in `app.topology_runs`. It does not go through `RunTable`: the run gets no `TopologyRunStarted`, no pane, no stop and no notice to the caller.

## 3. How each topology is built

Each shipping topology gets its own package under `topologies/`. The package starts as a copy of the files of `session/`. Where round 10 rebuilds a bundled topology, that topology's wiring files are copied into the same package. The changes named in § 5 are then made in the copied files. Everything not named stays as copied: the prompt build, the tool suite, interrupts, guidance, the record, and the views it does not change. The note's point 9 says the same: "Anything not specifically mentioned here should be assumed to function the exact same as the session topology."

Calling `session_topology(...)` with other arguments, as `runs/build.py` does, is not how a topology is built. Wrapping its builder with extra producers and a new termination, as `session/ci.py` does, is not either. `ci.py` does show one fact the copies rely on: a producer that writes the next `UserMessage` on `Returned` drives the next turn inside one run (`driver_stepper`).

## 4. Roles inside a topology

A role that does real work is a session, not a bare `call_responder` on a fixed prompt cut to 120, 200 or 700 characters. Two ways of running one exist and are used as they are.

- **A run session.** `start_build` (`runs/build.py`) makes a worktree and branch, builds a session in run mode with its own first message and role, and holds it on a `RunTable` as a `RunSession`. It ends on `ReportWritten`: outcome, reply, files, branch, commits (`write_report`). A worker on a detached worktree (`make_detached_worktree`) reports `branch=None`. Inside a topology, `embedded_substrate(factory, exports={"ReportWritten": ...})` (`kernel/composition.py`) runs such a session as a producer: the inner run gets its own record at `inner_root`, which the producer's input must carry, and an inner failure arrives as one outer `ProducerFailed`.
- **A standing session.** `delegate`'s `_to_standing` runs one turn on a named registry session through `SessionRegistry.turn_sync` and reads back that turn's reply (`tool_loop/delegate.py`). Its record and context persist between turns. A producer body makes the same call on a worker thread.

`HeldRun.sessions` is fixed when `RunTable.start` is called, and the app opens panes once, from `TopologyRunStarted`. A role session started later in the run (a round-2 drafter, a wave-2 card) is not in the listing and gets no pane.

## 5. The shapes

Each subsection names what changes in the copy. Everything else stays as copied.

### 5.1 Autonomous build and pair coding

One package, `topologies/autonomous_build/`, copied from `session/`. Pair coding is the same package with the automatic reply off: a person writes each next message, and the standing reviewer reviews every turn. Point numbers are the 2026-09-24 note's.

Changes:

- **Termination (point 7).** `pause_await_input(when Returned, resume UserMessage)` becomes `any_of(finalise_on(BuildEnded), finalise_on(SessionEnded))`.
- **View.** `view("returns", KindCount(Returned))`, beside the copied `user_turns` and `returned_turns`.
- **`auto_reply` (point 2).** A producer of `UserMessage`, triggered `PerEvent` on `Returned` when `returns % n != 0` and no end condition holds. It writes the fixed reply with its own `slash_source`, so the record tells it from a person's message. It is absent in pair coding.
- **`review_turn` (point 3).** A producer of `ReviewWritten`, triggered on `Returned` when `returns % n == 0`. On that return no reply goes to the builder. The producer runs one turn on the standing reviewer (§ 4), opened with the builder, with the fixed review prompt and the commits since the last review. The reviewer works on a detached worktree at the builder's branch head with read-only tools. Its review is a drift check against the roadmap, the cards, SDD, engineering practice and the project's conventions (point 5). In pair coding, n is 1.
- **`review_reply` (point 3).** A producer of `UserMessage`, triggered on `ReviewWritten`. It writes the review text, then "--", then "analyze, verify, apply", as the builder's next message.
- **`end_check` (point 7).** A producer of `BuildEnded`, triggered on each `Returned`. It emits when either holds:
  - every input card has `status: closed` in its front matter in the worktree (190 of this project's cards carry that value);
  - the last k returns added no commit to the branch. k is a setting.
- **Input (points 1, 4).** The first message carries the roadmap path, the card paths and the project part of the prompt.
- **Prompt (point 11).** The copied `session_prompt` producer gets one more source, a session-open fragment: the SDD kit 3 with its halt-and-wait steps removed. The reviewer gets the same kit.
- **Point 6.** The reviewer proposing new cards or a new roadmap is a second review prompt, off by default.
- **Callers (points 4, 8).** From a session, a tool starts it on the `RunTable` path, as `build` does; its pane is view-only, which fits a session whose messages the topology writes. Pair coding is driven by a person, so it runs on the person-driven path (§ 2), which needs the manifest to name the package (§ 6).

Pair coding today (`applications/pair_coding_composite.py`) registers two sessions and seeds the builder with an instruction to call `delegate` after each change. In the copy, the review fires from a trigger on every return. No step depends on the model remembering to ask.

### 5.2 Best-of-N

One package, `topologies/best_of_n/`, copied from `session/`, with `best_of_n/__init__.py` and `contracts.py` copied in. Their wiring runs `seeder` → N `Draft` → `drafter` → `Candidate` → `validator` → `Verdict`. The `judge` trigger fires when a round's verdict count reaches N (`PerEvent`, predicate over the `verdicts` `KindBuffer`) and emits `Solved`, a new round of `Draft`, or `Exhausted`.

Changes:

- **Start.** `best_of_n_correction` already takes `seed_on`: the seeder fires on the session's `UserMessage`, which carries the task.
- **Drafter.** A run session per `Draft` (§ 4), in a worktree on `bon/<run>/<round>-<slot>`. Its first message is the task; from round 2 it also carries the prior round's failures (the `context` field). Its `ReportWritten` becomes the `Candidate`, so a candidate is a branch and a report, not a block of text. The model is set per slot, so N different models stay possible (`coding_flow`'s ensemble).
- **Validator.** The command the task names (tests, a build, a linter), run in the candidate's worktree; the exit code is the verdict, as in `coding_flow/gate.py` (`source="gate"`). Where no command exists, the validator is a read-only review session on a model the caller names (`source="model"`).
- **Return and termination.** `best_of_n_correction`'s `termination` argument replaces its `quiescence()` default: `Solved` or `Exhausted` writes the session's `Returned`, carrying the selected branch and every candidate's report, and the run finalises on it. Nothing merges.

`coding_flow` becomes this topology. Its fixture task (`coding_flow/task.py`, the kvstore) stays as a test.

### 5.3 Adversarial document reviewer

One package, `topologies/document_review/`, copied from `session/`, with `adversarial_pair`'s wiring copied in: `writer` initial, `to-finder` on each `Artifact`, `route("stage-challenge", slot="challenge")`, `refine` while `version < max_attempts`.

Changes:

- **Writer.** A run session on the document in a worktree, in place of the 200-character `call_responder`. Version 0 drafts or takes the caller's document; each later version gets the staged challenge in its first message.
- **Finder.** A read-only run session on a different model the caller names, in place of the 120-character call. It reads the committed document and reports its worst flaws.
- **Termination.** `quiescence()` becomes `finalise_on` on a final `Adjudicated` event, so the run ends on its own signal.

The roadmap's "information flows compose" example is this topology.

### 5.4 Swarm

One package, `topologies/swarm/`, copied from `session/`. The input is a roadmap and its cards. Given a problem statement instead, a large model's run session writes the cards first, and its report is the card list.

Changes:

- **`plan`.** A deterministic producer that reads each card's `files` and `depends_on` and emits one `WavePlanned` per wave.
  - A card waits for the cards it depends on and for any card that shares a file.
  - Shared files go first in their own card (round 8's "Wave 0").
  - A card that names no files is refused at planning, with the card named.
- **`card`.** A run session per card (§ 4), triggered `PerEvent` on `WavePlanned` for each card in the wave. Each card gets its own worktree, its own branch, and the smallest model the caller names. Its `ReportWritten` becomes `CardReported`.
- **`integrate`.** `view("reports", KindBuffer(CardReported))`. A trigger fires when the wave's report count reaches its card count, the predicate `best_of_n` uses for a round. It starts a run session on the main model, on an integration branch. That session merges the wave's branches and runs the project's tests. Its report is `WaveIntegrated`, and the next wave's `WavePlanned` waits on it.
- **Termination.** `finalise_on(SwarmEnded)`. It is emitted after the last wave's integration, or after an integration that reports a conflict or a failed test run; its report names the conflict.

Open item 33 bears on this. `finalise_on(K)` misses `K` when a trigger also waits on `K`, because `_consult_termination` reads the trigger's `TriggerFired`. No trigger waits on `SwarmEnded`, but one waits on `WaveIntegrated`. The kernel fix comes first, or the termination is written around it.

### 5.5 Review with a panel judge

Review (K331, `runs/review.py`) already runs one read-only session per style (`defects`, `design`, `security`) on a detached worktree at the target. `code_review` adds three parts:

- a `KindBuffer` over the reviews;
- an `adjudicate` trigger at a quorum, with `Once`, that starts a judge session;
- `cancel_all_others` on the judge's completion.

Review takes these as an option when more than one style is asked for. `code_review`'s five fixed role prompts are not carried over.

### 5.6 Research sweep

One package, `topologies/research_sweep/`, copied from `session/`, with `applications/research_sweep.py`'s wiring and its four kinds copied in:

- a `seeder` emits one `ReadRequest` per source;
- `read` fires per request;
- `critique` fires `Once` at N findings;
- `synthesize` fires `Once` on the `Gaps` event.

Changes:

- **Readers.** Read-only run sessions with `read_file` and `web_fetch`. A source is a path or a URL the reader opens and pages through. Today the daemon passes each document's whole text in the call's inputs, and the CLI's `gather` cuts it at 8,000 characters.
- **Critic and synthesizer.** Run sessions.
- **Termination.** `all_completed` and `quiescence()` go; the run ends on `finalise_on(Synthesis)`.

### 5.7 Debate

One package, `topologies/debate/`, copied from `session/`, with `conversation.py`'s round-robin copied in: one `after-k` trigger per speaker and a `transcript` view.

Changes:

- Each speaker is a standing session (§ 4), so each side keeps its own context and tools across rounds.
- The claim and the sides come from the caller, in place of `debate`'s fixed claim.
- The 700-character turn cap goes.

## 6. What Substrate UI needs for these to run

The § 2 paths carry the session topology, build and review today. These are the parts they lack.

- **The manifest names the topology.** A person-driven session of a copied topology (pair coding) needs a manifest field naming its package, and `_build_session_topology_from_manifest` builds that package in place of `session_topology`. Every manifest without the field builds the session topology as now.
- **Topology runs go through `RunTable`.** A topology a session starts is held as build and review are: `TopologyRunStarted`, a pane per run session, `run(action=stop|events|replay)`, and the report on the caller's next step. Today's `run_topology` path (`_topology_run`, `app.topology_runs`) gives none of these.
- **A run's sessions can grow.** Best-of-N's round-2 drafters and swarm's later waves start after `RunTable.start`. `HeldRun.sessions` and the app's panes need to learn of a role session when it starts.
- **The run's own session is `sessions[0]`.** `RunTable.stop` ends `sessions[0]`. Each copied topology keeps the end-on-end-request trigger, so stop works on it unchanged.

## 7. The audit

| Topology | Today | Round 11 |
|---|---|---|
| `session` (`daily`) | the daily session; Substrate UI runs it | kept; the files every shipping topology starts from |
| build, review, delegate, handoff (K331–K334) | session-backed, held on `RunTable` or in the registry | kept; the roadmap's real-model test from a session applies to them too |
| autonomous build | not built | copied from `session/`, § 5.1 |
| `pair_coding` (application, `pair_coding_composite`) | two sessions; reviews only when the builder's model chooses to delegate | the autonomous build package with the automatic reply off, § 5.1 |
| `pair_coding_chunked` | canned chunks; the model's text is thrown away | cut |
| `best_of_n` loop, `best_of_n_verified`, `coding_flow` | bare-call drafters; `coding_flow` runs a real gate on a fixture task | one package copied from `session/` with `best_of_n`'s wiring, § 5.2 |
| `adversarial_pair` | bare-call writer and finder, 200 and 120 chars | copied from `session/` with its wiring, § 5.3 |
| swarm | not built (round-8 card 326 withdrawn) | copied from `session/`, § 5.4 |
| `code_review`, `fanout_review` | five bare-call role reviewers (200 chars) and a judge | the quorum judge folds into review, § 5.5; both cut as separate entries |
| `research_sweep` | bare-call readers over pasted document text | copied from `session/` with its wiring, § 5.6 |
| `debate` | two bare-call advocates on a fixed claim | copied from `session/` with the round-robin, § 5.7 |
| `prisoners_dilemma`, `intel_asymmetry`, `natural_conversation`, `natural_conversation_bare`, `conversation.py`, `instruments/` | fixed scenarios for the dynamics assay | cut from the session; kept in Substrate for the assay's research pass |
| `recursive_decomposition` | planner yields "part i" strings | cut; the recursive trigger and depth guard are kept as a pattern, and delegate's depth caps (5 deep, 16 per call, 64 per tree) bound real recursion |
| `game_of_life`, `game_of_life_glider` | a deterministic simulation, no model | cut from the session; kept in Substrate (the glider is the pixel-decode harness's fixture) |
| `tool_loop` | the model–tool loop the session topology supersedes | cut from the session; its tool suite stays the session's |
| `swebench_repair`, `swebench_solver` | the benchmark solver | cut from the session; kept for benchmarking |
| `code_evolution` | evolutionary search with a real gate, bare-call mutator; not in `BUNDLED` | not session-facing in this round; built later the way § 5.2 is |

"Cut" means the roadmap's "dropped": the topology leaves `list_topologies`, `run_topology` and the guidance, and stays in Substrate.

## 8. What the session sees

Two defects sit on the session's side today. `list_topologies` returns `bundled.names()`: 18 CI configurations wired to `DeterministicResponder` stand-ins, such as `code_review` over the hard-coded `def f(x): return x / 0`. `run_topology` runs a different set, the three `_APP_BUILDERS` entries, and refuses `daily`; `pair_coding` goes to `_topology_run_composite`. A session is told of topologies it cannot run, and runs ones it is not told of.

After round 11, `list_topologies` returns the shipping set. For each topology it gives the inputs as a tool schema, the way the `build` tool's schema does. Starting one goes through `RunTable` (§ 6). The `BUNDLED` registry stays for the CLI's `substrate demo` commands and the committed records, and the session no longer reaches it.

## 9. Vocabulary to propose before building

New events, proposed against the session vocabulary as v0.17 and ratified before code. Each package's copied `vocabulary.py` carries its own kinds.

- **Autonomous build:** `ReviewWritten`; `BuildEnded`, with reason cards done, no progress or stopped; the automatic reply's `slash_source`.
- **Swarm:** `WavePlanned`, `CardReported`, `WaveIntegrated`, `SwarmEnded`.
- **Best-of-N, the document reviewer and the sweep:** reuse `best_of_n.contracts`, `adversarial_pair`'s `Artifact` and `Challenge`, and `research_sweep`'s four kinds. Their fields change from text to report and branch.
- **Substrate UI:** the manifest's topology field, and the event that adds a role session to a held run (§ 6).

## 10. Order

1. The parts of § 6: topology runs on `RunTable`, a run's sessions that can grow, and the manifest's topology field; and the session's view of § 8.
2. Best-of-N, the smallest use of N sessions. Its package is the first copy of `session/`. A test checks that a drafter's report crosses into the outer record and that its pane opens.
3. The adversarial document reviewer.
4. Autonomous build, with pair coding as its option.
5. Open item 33, then swarm.
6. The review panel judge, research sweep, debate.
7. The cuts of § 7.

A topology is kept only after it has been run from a session against a real model (the local Ollama models on this machine and one cloud model) and its record has been read.

## 11. Two choices for the Architect

- **Debate:** built as in § 5.7, or cut with the other conversation topologies. It is the one conversation shape with a use in a working session: arguing both sides of a design decision.
- **`code_evolution`:** built with best-of-N in this round, or left until after it. It needs the same drafter change and a cost command beside the gate command.
