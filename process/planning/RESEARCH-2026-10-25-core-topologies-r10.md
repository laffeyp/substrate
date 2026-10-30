# RESEARCH: the topologies that ship (round 10)

*2026-10-25. Round 10 follows round 9 (`RESEARCH-2026-10-14-core-topologies-r9.md`), which stays on disk. Round 9 named the shapes; round 10 goes through every topology Substrate has, one by one, and says for each whether it is rebuilt to work in a real session or cut from what a session can see. That is the before-distribution audit (`substrate-ui/process/planning/ROADMAP-2026-10-11-before-distribution.md`, "Topologies: real and useful from a session, or dropped from it"). Every design here is stated in Substrate's own parts: `producer_kind`, `view`, `trigger` with its predicate and policy, `route`, `initial`, `termination`, `instrument`, `embedded_substrate`. No part is new unless named as new.*

*Sources, read in full: the autonomous build note (`substrate-ui/process/methodology/2026-09-24-autonomous-build-topology.md`); research round 9; the before-distribution roadmap; `topologies/README.md`; sprint card 326 (swarm, round 8, history); the code of `session/__init__.py` (`session_topology`), `runs/run.py`, `runs/build.py`, `adversarial_pair`, `pair_coding`, `code_review`, `best_of_n`, `recursive_decomposition`, `conversation.py`, `debate`, `prisoners_dilemma`, `intel_asymmetry`, `natural_conversation`, `game_of_life`, `code_evolution`, `coding_flow`, and `applications/` (`best_of_n_verified`, `fanout_review`, `pair_coding_composite`, `research_sweep`, the five manifests). Read in part: `kernel/composition.py` (`embedded_substrate`), `runs/hold.py`, `tool_loop/delegate.py`, `tool_loop/substrate_tools.py`, `bundled.py`, the heads of `tool_loop/__init__.py`, `swebench_solver/__init__.py` and `instruments/`.*

## 1. What is wrong with the topologies today

The wiring in the bundled topologies is sound Substrate: `code_review` fires a judge on a `KindBuffer` quorum with `Once` and ends on `cancel_all_others`; `adversarial_pair` routes a challenge into the writer's next instantiation and bounds the loop with a predicate; `best_of_n` gates its judge on a round's verdict count. The producers are what make them toys. Each role is one `call_responder` on a fixed prompt. It has no tools, no worktree, no session record, no guidance, no pane. Its output is cut to 120 characters (`adversarial_pair`'s finder), 200 (the writer, the code reviewers) or 700 (a conversation turn). `pair_coding`'s driver ignores the model and yields a canned chunk. `recursive_decomposition`'s planner yields the strings "part 0" and "part 1".

Two defects sit on the session's side of the seam.

- `list_topologies` returns `bundled.names()`: 15 CI configurations wired to `DeterministicResponder` stand-ins, such as `code_review` over the hard-coded `def f(x): return x / 0`.
- `run_topology` runs a different set, the application manifests (`code_review`, `best_of_n_verified`, `research_sweep`). It cannot run any name `list_topologies` returns except by coincidence of spelling. A session is told of topologies it cannot run, and runs ones it is not told of.

## 2. The change that makes a role real: the role is a session

Substrate already has the two parts this needs.

**A run session as a producer.** `session_topology(..., run=RunSpec(...))` is a whole session that works one turn in a worktree and finalises on `ReportWritten` (`runs/run.py`, `compose_run`). `embedded_substrate(topology, exports={...})` turns any topology into a producer's `start`: the inner run gets its own record at `inner_root`, its exported kinds cross onto the outer bus, and an inner failure arrives as one outer `ProducerFailed` (`kernel/composition.py`). So a role becomes:

```python
b.producer_kind(
    "writer",
    schemas=[WriterReported],
    schema_version=1,
    start=embedded_substrate(
        session_topology(..., run=RunSpec(worktree, base, first_message)),
        exports={"ReportWritten": WriterReported},
    ),
    deterministic=False,
)
```

The outer topology keeps the toy's triggers, routes, views and termination unchanged. The input builder that used to fill a prompt now fills `first_message` and `inner_root`. Each inner record is listed as a `RunSession` on the `HeldRun`, so the app opens a pane on it as it does for a build.

**A standing session as a producer.** A role that keeps its context across turns, such as the standing reviewer, is a registry session addressed by name. `delegate`'s `child_session_name` path already runs one turn on such a session through `SessionRegistry.turn_sync` and returns its reply (`tool_loop/delegate.py`, `_to_standing`). A producer whose body makes that same call is a standing role: one turn per instantiation, the session's record and context persisting between them.

**A role composed onto the session itself.** When a topology changes only what happens at a session's own seams, it is registered on the session topology's builder, the way `compose_run` adds the report producer and its trigger and swaps the termination. The autonomous builder is built this way (§ 4.2).

Every topology below is built from these three and the bundled wiring. The outer topology is held by the caller's `RunTable` (stop, events, replay), as build and review are.

## 3. The audit

| Topology | Today | Verdict |
|---|---|---|
| `session` (`daily`) | the daily session | kept: the base everything composes onto |
| build, review, delegate, handoff (K331–K334) | session-backed, in force | kept; the roadmap's real-model test from a session applies to them too |
| autonomous build | not built | built new, § 4.2 |
| swarm | not built (round-8 card 326 withdrawn) | built new, § 4.3 |
| `best_of_n` loop, `best_of_n_verified`, `coding_flow` | bare-call drafters; `coding_flow` runs a real gate on a fixture task | rebuilt as one best-of-N with session drafters, § 4.1 |
| `adversarial_pair` | bare-call writer and finder, 200 and 120 chars | rebuilt as the adversarial document reviewer, § 4.4 |
| `pair_coding` (chunked) | canned chunks; the model's text is thrown away | cut |
| `pair_coding` (application, `pair_coding_composite`) | two real sessions; reviews only when the builder's model chooses to delegate | rebuilt, § 4.2: the review is the topology's, not the model's choice |
| `code_review`, `fanout_review` | five bare-call role reviewers and a judge | the panel's quorum judge folds into review, § 4.5; both cut as separate entries |
| `research_sweep` | bare-call readers over documents cut at 8,000 chars | rebuilt with read-only session readers, § 4.6 |
| `debate` | two bare-call advocates on a fixed claim | rebuilt on the conversation engine with session speakers and the caller's claim, § 4.7 |
| `prisoners_dilemma`, `intel_asymmetry`, `natural_conversation`, `natural_conversation_bare`, `conversation.py`, `instruments/` | fixed scenarios for the dynamics assay | cut from the session; kept in Substrate for the assay's research pass |
| `recursive_decomposition` | planner yields "part i" strings | cut; the recursive trigger and depth guard are kept as a pattern, and delegate's depth caps already bound real recursion |
| `game_of_life`, `game_of_life_glider` | a deterministic simulation, no model | cut from the session; kept in Substrate (the glider is the pixel-decode harness's fixture) |
| `tool_loop` | the model–tool loop the session topology supersedes | cut from the session; its tool suite stays the session's |
| `swebench_repair`, `swebench_solver` | the benchmark solver | cut from the session; kept for benchmarking |
| `code_evolution` | evolutionary search with a real gate, bare-call mutator; not in `BUNDLED` | not session-facing in this round; the same session-drafter change as best-of-N applies later |

"Cut" means the roadmap's "dropped": the topology leaves `list_topologies`, `run_topology` and the guidance, and stays in Substrate.

## 4. The shapes, in Substrate's parts

### 4.1 Best-of-N

`best_of_n_correction` stays as written: `seeder` → N `Draft` → `drafter` → `Candidate` → `validator` → `Verdict`; the `judge` trigger fires when a round's verdict count reaches N (`PerEvent`, predicate over the `verdicts` `KindBuffer`) and emits `Solved`, a new round of `Draft`, or `Exhausted`.

What changes is the work the caller supplies.

- **Drafter:** an embedded run session per `Draft`, in a worktree on `bon/<run>/<round>-<slot>`. Its first message is the task plus, from round 2, the prior round's failures (the `context` field). It exports `ReportWritten` as the `Candidate`, so a candidate is a branch and a report, not a block of text. The drafter's model is per slot, so N different models stay possible (`coding_flow`'s ensemble).
- **Validator:** a command run in the candidate's worktree. The task names it: tests, a build, a linter. The real exit code is the verdict, as in `coding_flow/gate.py` (`source="gate"`). Where no command exists, the validator is a read-only review session on a model the caller names (`source="model"`).
- **Output:** the selected branch and every candidate's report. Nothing merges.

`coding_flow` becomes this topology. Its fixture task stays as a test.

### 4.2 Autonomous build and pair coding

The two share their parts. Pair coding is a person driving a builder while a standing reviewer reviews each turn. Autonomous build is the same with the person replaced by a fixed reply. Point numbers are the 2026-09-24 note's.

**Composed onto the builder's session topology** (point 10: composed, not copied):

- `view("returns", KindCount(Returned))`, plus the session's own `user_turns` and `returned_turns`.
- **The automatic reply (point 2).** `producer_kind("auto_reply", schemas=[UserMessage])`, triggered on `Returned`. Its predicate is `returns % n != 0` and no end condition holds. It is `PerEvent`. It writes the fixed reply as a `UserMessage` with its own `slash_source`, so the record tells it from a person's message. In pair coding this producer is absent and the person writes the next message.
- **The review (point 3).** `producer_kind("review_turn", schemas=[ReviewWritten])`, triggered on `Returned` when `returns % n == 0`. Its body runs one turn on the standing reviewer, a registry session opened with the builder (§ 2). The message is the fixed review prompt and the commits since the last review. The reviewer works in a worktree at the builder's branch head with read-only tools. In pair coding, n is 1.
- **Back to the builder.** `producer_kind("review_reply", schemas=[UserMessage])`, triggered on `ReviewWritten`, writes the review text followed by "--" and "analyze, verify, apply" as the builder's next message.
- **Termination (point 7).** The session's `pause_await_input` is replaced, as `compose_run` replaces it, by `any_of(finalise_on(BuildEnded), finalise_on(SessionEnded))`. An `end_check` producer runs on each `Returned` and emits `BuildEnded` when either of two things holds:
  - every card in the input has `status: closed` in its front matter in the worktree (190 of this project's cards carry that value);
  - the last k returns added no commit to the branch. This is the "measured" lack of progress; k is a setting.
- **Input (points 1, 4, 11).** The input is the roadmap path, the card paths and the project part of the prompt. The fixed part is the SDD kit 3 with its halt-and-wait steps removed, given as a session-open fragment on the session's existing `session_prompt` producer.
- **Callers (point 8).** It is held by the session that started it through a tool; started from the CLI or the app, it is a top-level run.

**Point 6**, the reviewer proposing new cards or a new roadmap, is a second review prompt, off by default.

Pair coding today registers two sessions and tells the builder's model to call `delegate` after each change. Rebuilt, the review fires from the topology on every return. No step depends on the model remembering to ask.

### 4.3 Swarm

The input is a roadmap and its cards. With a problem statement instead, a large model's run session writes the cards first; its report is the card list.

- **Planning.** A deterministic `plan` producer reads each card's `files` and `depends_on` and emits one `WavePlanned` per wave. A card waits for the cards it depends on and for any card that shares a file. Shared files go first in their own card (round 8's "Wave 0"). A card that names no files is refused at planning with the card named: the plan cannot place it.
- **Work.** A `card` producer, an embedded build session per card, is triggered `PerEvent` on `WavePlanned` for each card in the wave. Each card gets its own worktree and branch and the smallest model the caller names. It exports `ReportWritten` as `CardReported`.
- **Integration.** `view("reports", KindBuffer(CardReported))`. An `integrate` trigger fires when the wave's report count reaches its card count, the predicate `best_of_n` uses for a round. It starts an embedded run session on the main model, on an integration branch. That session merges the wave's branches and runs the project's tests; its report is `WaveIntegrated`. The next wave's `WavePlanned` waits on it.
- **End.** `finalise_on(SwarmEnded)`, emitted after the last wave's integration, or after one that reports a conflict or a failed test run. Its report names the conflict.

Open item 33 matters here. `finalise_on(K)` misses `K` when a trigger also waits on `K`, because `_consult_termination` reads the trigger's `TriggerFired`. `SwarmEnded` has no trigger waiting on it, but `WaveIntegrated` does, so the kernel fix comes first or the termination is written around it.

### 4.4 Adversarial document reviewer

`adversarial_pair`'s wiring is kept whole: `writer` initial; `to-finder` on each artifact; `route("stage-challenge", slot="challenge")`; `refine` while `version < max_attempts`; then the termination.

- **Writer:** an embedded run session on the document in a worktree. Version 0 drafts or takes the caller's document; each later version gets the staged challenge in its first message.
- **Finder:** an embedded read-only run session on a different model the caller names. It reads the committed document and reports its worst flaws.
- **Termination:** `quiescence()` is replaced by `finalise_on` on a final `Adjudicated` event, so the run ends on its own signal.

The roadmap's "information flows compose" example is this topology.

### 4.5 Review with a panel judge

Review (K331) already runs one read-only session per style on a real target. `code_review` adds three parts: `KindBuffer` over the reviews, an `adjudicate` trigger at a quorum with `Once` that starts a judge session, and `cancel_all_others` on the judge's completion. Review takes these as an option when more than one style is asked for. The five fixed role prompts are not carried over; review's three published styles stay.

### 4.6 Research sweep

The wiring is kept: a `seeder` emits one `ReadRequest` per source; `read` fires per request; `critique` fires `Once` at N findings; `synthesize` fires `Once` on the `Gaps` event.

- **Readers** become read-only run sessions with `read_file` and `web_fetch`. They page through a source and do not get it cut at 8,000 characters, and a source may be a URL.
- **Critic and synthesizer** become run sessions.
- **Termination** drops `all_completed` for `finalise_on(Synthesis)`.

### 4.7 Debate

`conversation_topology`'s round-robin is kept: one `after-k` trigger per speaker and a `transcript` view. Each speaker becomes a standing session (§ 2), so each side keeps its own context and tools across rounds. The claim and the sides come from the caller. The turn cap of 700 characters goes.

## 5. What the session sees

`list_topologies` returns the shipping set and, for each, its inputs as a tool schema in the way the `build` tool's schema does. `run_topology` runs exactly that set. The `BUNDLED` registry stays for the CLI's `substrate demo` commands and the committed records. The session no longer reaches it.

## 6. Vocabulary to propose before building

The vocabulary gets new events, proposed against the session vocabulary as v0.17 and ratified before code:

- **Autonomous build:** `ReviewWritten`, `BuildEnded` (reason: cards done, no progress, stopped), and the automatic reply's `slash_source`.
- **Swarm:** `WavePlanned`, `CardReported`, `WaveIntegrated`, `SwarmEnded`.
- **Best-of-N, the document reviewer and the sweep:** they reuse `best_of_n.contracts`, `adversarial_pair`'s `Artifact` and `Challenge`, and `research_sweep`'s four kinds. The fields change from text to report and branch.

## 7. Order

1. The role parts of § 2, and the session's view of § 5, with a test that an embedded run session's report crosses and its pane opens.
2. Best-of-N, the smallest use of N sessions.
3. The adversarial document reviewer.
4. Pair coding, then autonomous build. They share their producers.
5. Open item 33, then swarm.
6. The review panel judge, research sweep, debate.
7. The cuts of § 3.

Each topology is kept only after it has been run from a session against a real model: the local Ollama models on this machine, and one cloud model. Its record has been read.

## 8. Two choices for the Architect

- **Debate:** rebuilt as in § 4.7, or cut with the other conversation topologies. It is the one conversation shape with a use in a working session: arguing both sides of a design decision.
- **`code_evolution`:** rebuilt with best-of-N in this round, or left until after it. It needs the same drafter change and a cost command beside the gate command.
