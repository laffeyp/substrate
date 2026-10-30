---
date: 2026-10-27
round: 13
prior_round: process/planning/RESEARCH-2026-10-27-core-topologies-r12.md
context_files:   # read in full this session
  - path: docs/specs/kernel_spec/v15.md
    lines: 1067
  - path: docs/specs/kernel_spec/v16_reconciliation_note.md
    lines: 40
  - path: docs/specs/technical_spec/draft5.md
    lines: 1122
  - path: docs/specs/technical_spec/draft5_amendment_A1.md
    lines: 30
  - path: src/substrate/kernel/topology.py
    lines: 395
  - path: src/substrate/kernel/runtime.py
    lines: 1055
  - path: src/substrate/kernel/sequencer.py
    lines: 509
  - path: src/substrate/kernel/triggers.py
    lines: 111
  - path: src/substrate/kernel/policies.py
    lines: 214
  - path: src/substrate/kernel/views.py
    lines: 132
  - path: src/substrate/kernel/runstate.py
    lines: 107
  - path: src/substrate/kernel/composition.py
    lines: 243
  - path: src/substrate/topologies/session/__init__.py
    lines: 1771
  - path: src/substrate/topologies/session/vocabulary.py
    lines: 664
  - path: src/substrate/topologies/runs/run.py
    lines: 110
  - path: src/substrate/topologies/runs/build.py
    lines: 229
  - path: src/substrate/topologies/runs/review.py
    lines: 207
  - path: src/substrate/topologies/runs/hold.py
    lines: 378
  - path: src/substrate/topologies/tool_loop/delegate.py
    lines: 496
  - path: src/substrate/topologies/tool_loop/substrate_tools.py
    lines: 812
  - path: src/substrate/topologies/best_of_n/__init__.py
    lines: 213
  - path: src/substrate/topologies/adversarial_pair/__init__.py
    lines: 160
  - path: src/substrate/topologies/code_review/__init__.py
    lines: 208
  - path: src/substrate/topologies/conversation.py
    lines: 255
  - path: src/substrate/topologies/applications/research_sweep.py
    lines: 252
  - path: src/substrate/topologies/applications/pair_coding_composite.py
    lines: 117
  - path: ../substrate-ui/server.py
    lines: 4732
  - path: ../substrate-ui/process/methodology/2026-09-24-autonomous-build-topology.md
    lines: 27
  - path: src/substrate/topologies/tool_loop/tools.py   # lines 70-80 only: the toolkit tool names
    lines: 11
---

# RESEARCH: the topologies that ship (round 13)

*2026-10-27. Round 13 follows round 12 (`RESEARCH-2026-10-27-core-topologies-r12.md`), which stays on disk. Round 12 wrote the session topology's wiring as the kernel and the code define it, and set each shape against it. Round 13 applies a review of round 12: it states the kernel's termination rule once and applies it, gives every embedded role a failure path, and fills the gaps the review named. § 12 lists each change.*

## 1. The kernel's parts

From kernel v15 and technical DRAFT 5, as `kernel/` implements them.

- **Producer.** A kind registered with `producer_kind(kind, schemas, schema_version, factory|start, deterministic, budget)`. It takes a sealed input and yields typed events (frozen msgspec Structs). The input is the canonical bytes the record holds, decoded into the Producer's own copy (K267); nothing changes it after start.
- **Event.** One frame: `seq` (dense, the identity), `kind`, `schema`, `producer {kind, instance, parent}` (null for runtime events), `t` (excluded from equivalence), `payload`. Twelve lifecycle kinds are reserved under `substrate.`: RunStarted, TriggerFired, InputBuildFailed, ProducerStarted, ProducerEmittedInvalidEvent, ProducerCompleted, ProducerFailed, ProducerCancelled, InjectionApplied, PredicateQuarantined, TerminationMatched, RunFinalised.
- **View.** A deterministic projection with a subscription, updated synchronously in step 3. The kernel ships `KindBuffer`, `KindCount`, `BufferView`, `PerKindLatest`, `StartedCompletedCounts`.
- **Trigger.** `trigger(id, subscription, predicate, starts, input_builder, policy, cooldown)`. On each matching append, the predicate runs over the as-of-N Views and staged Route messages. If it holds and the policy admits, the input builder runs, the input is sealed and recorded in `TriggerFired`, and the Producer is scheduled to start after the cycle. Policies: `Once`, `PerEvent`, `PerKey(fn)`, `WhileTrue(cooldown)`. A closed set.
- **Route.** `route(id, subscription, slot, transform)` stages `transform(event)` in a slot in step 4, before triggers run, and records `InjectionApplied`. Staged messages persist across cycles; a later trigger's input builder reads `ctx.staged`.
- **Initial.** `initial(kind, input)` starts a Producer at run open.
- **Instrument.** `instrument(name, on, schemas, input_builder, ...)`: a producer kind and a `PerEvent` trigger on one kind, in one call.
- **TerminationPolicy.** A callback over `TermContext {event, quiescent, running, started, completed, counts}` returning `continue`, `finalise-run`, `cancel-others` or `pause-await-input`. Recipes: `threshold_count`, `finalise_on`, `all_completed` (not resumable), `cancel_all_others`, `quiescence`, `pause_await_input`, `any_of`, `all_of`.
- **Composition.** `embedded_substrate(topology, exports=...)` is a Producer start that runs an inner `Runtime` at `inner_root`, which the input must carry, and yields only export-mapped inner kinds onto the outer bus. An inner failure arrives as one outer `ProducerFailed` carrying the inner run id.

### 1.1 The append cycle

One writer runs each admitted event through six synchronous steps: validate, assign `seq` and append, update Views, stage Routes, evaluate predicates and fire triggers, then drain the control queue (each control event — `TriggerFired`, `InjectionApplied`, and the rest — runs its own full cycle, FIFO). Producers start after the cycle.

### 1.2 When termination is consulted

`Runtime._writer_loop` consults the policy once per processed item, after the cycle and its control-queue drain, with `st.last_event`. `AppendCycle.cycle` drains the control queue by recursion (`sequencer.py` lines 127–128), and each recursive cycle sets `st.last_event` again. A trigger that fires on event K appends its `TriggerFired` after K, so the policy sees `TriggerFired`, not K. This is open item 33 (`substrate-ui/process/planning/OPEN-ITEMS-2026-10-10.md`, line 27, found 2026-10-14; the kernel is unchanged).

**The rule every shape below applies.** The kind a `finalise_on` or a `pause_await_input` keys on must be a kind that no trigger in the final wiring subscribes to. `threshold_count(K, n)` reads counts, not the last event, and escapes the rule, but it is wrong across a resume, because a resume restores counts from the whole record.

### 1.3 A fan-in needs one report per role, failure included

`embedded_substrate` raises when its inner run fails, and the outer record gets one `ProducerFailed` for that producer instance, carrying `inner_run_id`. The role then emits no report. Every shape that counts reports (best-of-N's verdicts, swarm's card reports, the sweep's findings, the panel's reviews) would wait forever at quiescence. So each embedded role gets a failure path:
- a `<role>_failed` producer, triggered `PerEvent` on `substrate.ProducerFailed` whose `producer.kind` is the role's kind;
- it emits the role's report kind with a failed outcome;
- its input builder finds the role's item (the draft slot, the card, the source) through a View over that trigger's `TriggerFired` frames, keyed by `instance`. `TriggerFired` records both `instance` and `resolved_input` (`sequencer.py`, `_eval_triggers`).

This is the same rule `coding_flow`'s drafter and `research_sweep`'s reader already keep in code: one report per started item, a failure being a report.

## 2. The session topology's wiring

`session_topology(...)` in `topologies/session/__init__.py` registers the following. Names are the constants in `session/vocabulary.py`.

### 2.1 Producers

| Kind | Emits | Started by |
|---|---|---|
| `session_started` (instrument) | `SessionStarted` | `substrate.RunStarted` |
| `session_prompt` | `PromptFragment`, `SessionWarning`, `SessionChanged` | initial at run open; `session-prompt-on-user-message-change` |
| `first_message` (only with a first message) | `UserMessage` | `first-message-on-session-prompt` (`Once`), or initial |
| `model` | `PromptComposed`, `ModelReply`, `ToolCall`, `TranscriptCompacted`, `BackgroundTaskEnded`, `TopologyRunEnded`, `HarnessToolCall`, `HarnessToolResult` | `model-on-user-message`, `model-on-tool-result`, `model-wrap-up-on-tool-result`, `model-on-skill-fragment`, `model-on-session-prompt-change` |
| `tool` | `ToolResult` | `tool-on-tool-call` |
| `return` | `Returned` | `return-on-reply`, `return-on-model-error`, `return-on-interrupt`, `return-on-language` |
| `session_end` | `SessionEnded` | `end-on-exit`, `end-on-turn-cap`, `end-on-end-request` (all `Once`) |
| `interrupt_fragment` | `PromptFragment` (source `interrupt`) | `interrupt-fragment-on-interrupt-request` |
| `skill_fragment` | `PromptFragment` (source `skill`), `SessionWarning` | `skill-fragment-on-user-message`, `skill-fragment-on-session-prompt-change` |
| `language` (when `language=True`) | `LanguageProfile`, `LanguageDrift` | `language-on-reply` |
| `report` (run mode only, `compose_run`) | `ReportWritten` | `report-on-returned` (`Once`) |

### 2.2 Triggers, with their predicates

All `PerEvent` unless marked.

- `model-on-user-message` (on `UserMessage`): no skill asked and no pending setting change. Input: step 0, the prompt fragments (`fragment_cohort`), and a history ticket (`_prompt_input`: a seq range of the record chosen to fit the driver's window).
- `tool-on-tool-call` (on `ToolCall`): always.
- `model-on-tool-result` (on `ToolResult`): the result answers a reply (not an MCP call) and `step + 1 < turn_max_steps`.
- `model-wrap-up-on-tool-result`: the same, with `step + 1 >= turn_max_steps`; input `final=True`.
- `return-on-reply` (on `ModelReply`): `stop_reason != tool_use` and the turn is open (`returned_turns < user_turns`); off when `language` is on.
- `language-on-reply` / `return-on-language`: the same chain with the measurement between the reply and `Returned`.
- `return-on-model-error` (on `ProducerFailed` of `model`), `return-on-interrupt` (on `ProducerCancelled` of `model` or `tool`): turn open.
- `session-prompt-on-user-message-change`, `model-on-session-prompt-change`, `skill-fragment-on-session-prompt-change`: a message that arrives while a setting differs from the record first records the change, then starts the model or the skill.
- `skill-fragment-on-user-message`, `model-on-skill-fragment`: a `/<skill>` message loads the skill, then starts the model.
- `interrupt-fragment-on-interrupt-request` (on `InterruptRequested`): always.
- `end-on-exit` (`/exit`), `end-on-turn-cap` (user turns > `max_turns`), `end-on-end-request` (on `SessionEndRequested`; reason `daemon_shutdown` or `caller_stop` when the source says so, else `user_end`).
- `report-on-returned` (on `Returned`, `Once`): run mode only.

### 2.3 Views

`results` (`KindBuffer(ToolResult)`), `user_turns` (`KindCount(UserMessage)`), `user_messages` (`KindBuffer(UserMessage)`), `returned_turns` (`KindCount(Returned)`), `fragment_cohort` (newest session-open fragment per source, plus turn-scoped fragments cleared on the next `PromptComposed`), `session_settings` (the settings the record last stated), `turn_history` (turn sizes and the last cut, for the history ticket).

### 2.4 Termination

- Daily: `any_of(pause_await_input(when the event is Returned, resume_condition=UserMessage), finalise_on(SessionEnded))`. It works because no daily trigger subscribes to `Returned` or `SessionEnded` (§ 1.2).
- Run mode: `any_of(finalise_on(ReportWritten), finalise_on(SessionEnded))`. `report-on-returned` subscribes to `Returned`, which is why run mode cannot pause on `Returned`; nothing subscribes to `ReportWritten`.
- `_refuse_all_completed` rejects any policy with an `all_completed` leaf.

### 2.5 What the copy keeps

A topology copied from `session/` keeps all of § 2.1–2.3 unchanged unless its section in § 5 names a change: the prompt build and its compaction (the history ticket and `TranscriptCompacted`), interrupts, skills, setting changes, background-task and run notices, and the session-open sources (`role`, `bundle_methodology`, `bundle_style`, `control`, `baseline`, `memory`, `parent_context`, `tools_suite`, `per_turn`).

## 3. How Substrate UI runs a topology

- **A session a person drives.** `SessionRegistry.turn_sync` builds the topology through `_build_session_topology_from_manifest` (`server.py:653`), which always calls `session_topology(...)`; no manifest field names another package. It runs the turn with `Runtime.run` on a fresh record or `Runtime.resume(resume_event=UserMessage)` on a paused one.
- **A run a session holds.** `RunTable.start` (`runs/hold.py`) runs any factory on its own loop in a worker thread and posts `TopologyRunStarted` into the caller's record; the app opens a view-only pane per `RunSession`. `RunTable.stop` injects `SessionEndRequested(source=caller_stop)` into `sessions[0]`. The caller's next model step reports the end once (`drain_ended`).
- **A one-shot application.** `run_topology` calls the daemon over HTTP; `_topology_run` (`server.py:3563`) runs one of three `_APP_BUILDERS` with `asyncio.run`, outside `RunTable`: no `TopologyRunStarted`, no pane, no stop, no notice.

## 4. How each topology is built

Each shipping topology is its own package under `topologies/`, made by copying the files of `session/`. Where it replaces a bundled topology, that topology's wiring file is copied in beside it. Then only the changes in its § 5 section are made. The copy's own termination block (§ 2.4) is deleted and replaced by the one its section names; `TopologyBuilder.termination` keeps only the last policy set, so a second call would otherwise decide which one runs by order alone.

A role inside a topology that does real work is a session, in one of two forms:
- **A run session**, started the way `start_build` starts one: its own worktree, a `RunSpec`, and a `ReportWritten` when its turn ends. Inside a topology it runs through `embedded_substrate`.
- **A turn on a standing session**, run the way `delegate`'s `_to_standing` runs one: `SessionRegistry.turn_sync` on a named registry session, whose record and context persist between turns.

One exception to the package rule: the panel judge (§ 5.6) goes inside `runs/review.py`, because review is already a session-backed run (K331).

## 5. The shapes

### 5.1 Autonomous build

Package `topologies/autonomous_build/`, copied from `session/`. Point numbers are the 2026-09-24 note's.

- **Termination (point 7).** `any_of(finalise_on(BuildEnded), finalise_on(SessionEnded))`. No trigger subscribes to `BuildEnded` (§ 1.2). The daily pause on `Returned` could not stay in any case: three triggers below subscribe to `Returned`.
- **The reviewer's failure.** A failed reviewer turn (`turn_sync` raises) makes `review_turn` emit `ReviewWritten` with the error as its text, so the builder is told and the build goes on (§ 1.3).
- **View.** `returns` = `KindCount(Returned)`.
- **`end_check`** (new producer, emits `BuildEnded`), trigger `end-check-on-returned` on `Returned`, predicate: every input card has `status: closed` in its front matter in the worktree, or the last k returns added no commit to the branch.
- **`auto_reply`** (point 2; emits `UserMessage` with its own `slash_source`), trigger `auto-reply-on-returned` on `Returned`: `returns % n != 0` and neither end condition holds. The end check and the reply read the same two conditions, so exactly one of them acts on each return.
- **`review_turn`** (point 3; emits `ReviewWritten`), trigger `review-turn-on-returned` on `Returned`: `returns % n == 0` and neither end condition holds. Its body runs one turn on the standing reviewer through `SessionRegistry.turn_sync` on a worker thread, with the fixed review prompt and the commits since the last review. The reviewer works on a detached worktree at the builder's branch head with read-only tools, and checks drift against the roadmap, the cards, SDD, practice and the project's conventions (point 5).
- **`review_reply`** (emits `UserMessage`), trigger on `ReviewWritten`: the review text, then "--", then "analyze, verify, apply".
- **Input (points 1, 4).** The first message carries the roadmap path, the card paths and the project part of the prompt.
- **Prompt (point 11).** The copied `session_prompt` producer gains one session-open source: the SDD kit with its halt-and-wait steps removed.
- **Callers (points 4, 8).** A tool starts it on the `RunTable` path, as `build` does. Its pane is view-only, which fits a session whose messages the topology writes.
- **Point 6.** The reviewer proposing new cards or a new roadmap is a second review prompt, off by default.

### 5.2 Pair coding

Package `topologies/pair_coding/` (the new one), copied from `topologies/autonomous_build/` once it exists, not from the chunked `pair_coding` demo. A person writes every message; the standing reviewer reviews every turn.

- `auto_reply`, `end_check` and `review_reply` are removed.
- `review_turn` fires on every `Returned` (n = 1).
- **Termination.** The daily `pause_await_input` cannot pause on `Returned` once `review-turn-on-returned` subscribes to it (§ 1.2). The pause moves to the review's end: `pause_await_input(when the event is ReviewWritten, resume_condition=UserMessage)`, with `finalise_on(SessionEnded)`. Removing `review_reply` is what makes `ReviewWritten` a kind no trigger subscribes to, and that is what lets the pause fire.
- The person reads the review in the reviewer's pane and writes the next message, which resumes the run.
- It runs on the person-driven path (§ 3), which needs the manifest to name the package (§ 6).

### 5.3 Best-of-N

Package `topologies/best_of_n/`, copied from `session/`, with `best_of_n/__init__.py` and `contracts.py` copied in. `best_of_n_correction(b, n, max_rounds, draft_factory, validate_factory, judge_factory, termination, seed_on, ...)` registers `seeder`, `drafter`, `validator`, `judge`, the `verdicts` `KindBuffer`, and the triggers `seed`, `draft`, `validate`, `judge` (the judge fires when a round's verdict count reaches n).

- **Start.** `seed_on=UserMessage`: the task arrives as the session's first message.
- **The session's own model.** `model-on-user-message` is removed, so the copy's model does not answer the task itself.
- **Drafter.** `draft_factory` returns an `embedded_substrate(session_topology(..., run=RunSpec(...)), exports={"ReportWritten": Candidate-carrier})`. Its input carries `inner_root`. Each draft gets a worktree on `bon/<run>/<round>-<slot>`; from round 2 its first message carries the prior round's failures (the `context` field). The model is set per slot.
- **Validator.** The task's command (tests, a build, a linter) in the candidate's worktree; the exit code is the verdict (`source="gate"`). Where no command exists, a read-only review session on a model the caller names (`source="model"`).
- **Return.** A new producer `return_on_judge` on `Solved` or `Exhausted` writes `Returned` with the selected branch and every candidate's report in `detail`.
- **A drafter's failure.** `drafter_failed` (§ 1.3) emits a `Candidate` with no branch and the inner error as its report, so the validator writes a failing `Verdict` and the round still reaches n.
- **Termination.** The copied session's termination block is deleted (§ 4). `best_of_n_correction(termination=...)` sets the only policy: `any_of(finalise_on(Returned), finalise_on(SessionEnded))`, in place of the loop's default (`Solved | Exhausted | quiescence`). No trigger subscribes to `Returned` in this package.
- `coding_flow` becomes this topology; its kvstore task stays as a test.

### 5.4 Adversarial document reviewer

Package `topologies/document_review/`, copied from `session/`, with `adversarial_pair/__init__.py` copied in: `writer` initial, `to-finder` on `Artifact`, `route("stage-challenge", slot="challenge")`, `refine` on `Challenge` while `version < max_attempts`.

- **Writer.** An embedded run session on the document in a worktree, replacing the 200-character `call_responder`. Version 0 drafts or takes the caller's document; each later version gets the staged challenge in its first message.
- **Finder.** A read-only embedded run session on a different model, replacing the 120-character call.
- **Failures.** `writer_failed` and `finder_failed` (§ 1.3) emit `Adjudicated` with the failure as its outcome, so a failed role ends the run with a reason, not at quiescence.
- **Termination.** `quiescence()` becomes `finalise_on(Adjudicated)`. A new producer `adjudicate` on the `Challenge` whose `version == max_attempts` emits `Adjudicated`; no trigger subscribes to `Adjudicated`.

### 5.5 Swarm

Package `topologies/swarm/`, copied from `session/`.

- **`plan`** (deterministic producer, emits `WavePlanned`), on the first `UserMessage` (the roadmap and cards). A card waits for the cards it depends on and for any card sharing a file; shared files go first in their own card. A card naming no files is refused at planning, named.
- **`card`** (embedded build session per card, exports `ReportWritten` as `CardReported`), triggered `PerEvent` on `WavePlanned` for each card in the wave.
- **A card's failure.** `card_failed` (§ 1.3) emits `CardReported` with `outcome: failed` and the inner error, for the card its instance ran. The wave's count still reaches its card count.
- **`integrate`** (embedded run session on the main model on an integration branch, exports its report as `WaveIntegrated`), trigger on `CardReported` when the wave's report count reaches its card count (`KindBuffer(CardReported)`). A failed card is in its input, and its branch is not merged.
- **Next wave.** `plan-on-wave-integrated` on `WaveIntegrated` emits the next `WavePlanned`, or `SwarmEnded` after the last wave, on a conflict, on a failed test run, or when a card in the wave failed. `integrate_failed` (§ 1.3) emits `WaveIntegrated` with the failure, so a failed integration also ends in `SwarmEnded`.
- **Termination.** `finalise_on(SwarmEnded)`. `plan-on-wave-integrated` subscribes to `WaveIntegrated`, not `SwarmEnded`, so the rule in § 1.2 holds. Open item 33 does not block swarm; it would block only a design that finalised on `WaveIntegrated`.

### 5.6 Review with a panel judge

The exception to § 4: this is not a new package. Review (K331, `runs/review.py`) is already a session-backed run: one read-only session per style (`defects`, `design`, `security`) on a detached worktree at the target. The three parts from `code_review` are added inside `runs/review.py`, used when more than one style is asked for:
- a `KindBuffer` over the reviews;
- an `adjudicate` trigger at a quorum, with `Once`, that starts a judge session;
- `cancel_all_others` on the judge's `ProducerCompleted`.

A failed reviewer counts toward the quorum through `reviewer_failed` (§ 1.3).

**Decision: three styles, not five roles.** Review keeps its three styles and drops `code_review`'s five roles (security, performance, style, correctness, clarity). Grounds: the three styles are texts with published sources (`runs/review_styles/README.md`), while the five roles are one-line prompts in `code_review/__init__.py` ("Review this code for {role} problems ONLY"). Revisit if the Architect wants performance and clarity as styles of their own; each would be a new text in `review_styles/`.

### 5.7 Research sweep

Package `topologies/research_sweep/`, copied from `session/`, with `applications/research_sweep.py` copied in: `seeder` emits one `ReadRequest` per source; `read` per request; `critique` `Once` at N findings; `synthesize` `Once` on `Gaps`.

- **Readers.** Read-only embedded run sessions with `read_file` and `web_fetch`. Today the daemon passes each document's whole text in the call's inputs, and the CLI's `gather` cuts it at 8,000 characters. In the copy, the `ReadRequest` carries the source's path or URL, not its text. The reader's first message names the question and the source, and the reader opens and reads the source with its own tool calls during its turn. Nothing is pasted into the message, so no source is cut.
- **A reader's failure.** `reader_failed` (§ 1.3) emits a `Finding` naming the failure, so the critique still fires at N findings.
- **Critic and synthesizer.** Embedded run sessions.
- **Termination.** `all_completed` and `quiescence()` go; the run ends on `finalise_on(Synthesis)`, which no trigger subscribes to.

### 5.8 Debate

Package `topologies/debate/`, copied from `session/`, with `conversation.py`'s round-robin copied in: one `after-k` trigger per speaker on `Turn` and a `transcript` `KindBuffer(Turn)`.

- Each speaker is a standing session (§ 4), so each side keeps its context and tools across rounds.
- The claim and the sides come from the caller.
- The 700-character cap goes: `text=text[:700]` in `_speaker_factory` (`conversation.py:165`), which cuts each recorded `Turn`. A speaker that is a standing session reports its whole reply.
- **Termination.** `any_of(threshold_count(Converged, 1), quiescence())` is kept; the round budget in the `after-k` predicates ends the cascade.

## 6. What Substrate UI needs

- **The manifest names the topology.** A person-driven copy (pair coding) needs a manifest field naming its package; `_build_session_topology_from_manifest` builds that package in place of `session_topology`. A manifest without the field builds the session topology as now.
- **Topology runs go through `RunTable`.** A topology a session starts is held as build and review are: `TopologyRunStarted`, panes, `run(action=stop|events|replay)`, and the report on the caller's next step.
- **A run's sessions can grow.** Round-2 drafters and later swarm waves start after `RunTable.start`. `HeldRun.sessions` and the panes learn of each role session when it starts.
- **Stop reaches the topology.** `RunTable.stop` ends `sessions[0]`. Each copy keeps `end-on-end-request`, so stop works unchanged.

## 7. The audit

| Topology | Today | Round 13 |
|---|---|---|
| `session` (`daily`) | the daily session; Substrate UI runs it | kept; the files every shipping topology starts from |
| build, review, delegate, handoff (K331–K334) | session-backed, on `RunTable` or the registry | kept |
| autonomous build | not built | § 5.1 |
| `pair_coding` (application) | two sessions; reviews only when the builder's model delegates | § 5.2 |
| `pair_coding_chunked` | canned chunks | cut |
| `best_of_n` loop, `best_of_n_verified`, `coding_flow` | bare-call drafters | § 5.3 |
| `adversarial_pair` | 200- and 120-character calls | § 5.4 |
| swarm | not built | § 5.5 |
| `code_review`, `fanout_review` | five bare-call reviewers and a judge | folded into review, § 5.6; both cut as entries |
| `research_sweep` | bare-call readers over pasted text | § 5.7 |
| `debate` | two bare-call advocates on a fixed claim | § 5.8 |
| `prisoners_dilemma`, `intel_asymmetry`, `natural_conversation`, `natural_conversation_bare`, `conversation.py`, `instruments/` | fixed assay scenarios | cut from the session; kept for the assay |
| `recursive_decomposition` | "part i" strings | cut; delegate's caps (5 deep, 16 per call, 64 per tree) bound real recursion |
| `game_of_life`, `game_of_life_glider` | deterministic simulation | cut from the session; the glider stays the pixel-decode fixture |
| `tool_loop` | superseded by the session | cut from the session; its tool suite stays |
| `swebench_repair`, `swebench_solver` | benchmark solver | cut from the session; kept for benchmarking |
| `code_evolution` | real gate, bare-call mutator | later, the way § 5.3 is built |

"Cut" means it leaves `list_topologies`, `run_topology` and the guidance, and stays in Substrate.

## 8. What the session sees

`list_topologies` returns `bundled.names()`, 18 CI configurations on `DeterministicResponder` stand-ins. `run_topology` runs the three `_APP_BUILDERS` entries and refuses `daily`; `pair_coding` goes to `_topology_run_composite`. After round 13, `list_topologies` returns the shipping set with each one's inputs as a tool schema, the way the `build` tool's schema does, and starting one goes through `RunTable` (§ 6). `BUNDLED` stays for `substrate demo` and for the committed records `scripts/gen_topology_records.py` writes.

This changes a surface the session's model already uses. Three tools are named in `tool_loop/tools.py` (`TOOL_NAME_LIST_TOPOLOGIES`, `TOOL_NAME_RUN_TOPOLOGY`, `TOOL_NAME_RUN_TOPOLOGY_POLL`, lines 75–78), built for every session in `server.py` (lines 703–714), and tested in `tests/test_substrate_tools_list_228.py` and `tests/test_realmodel_tool_comprehension.py`:
- `list_topologies` keeps its name and returns the shipping set with schemas;
- `run_topology` keeps its name and returns at once with a run id, as `build` does; the run's end reaches the caller's next step as `TopologyRunEnded`;
- `run_topology_poll` is replaced by `run(run_id, action=events)`, the run tool `build` and `review` already use. Its name stays one release with a message pointing to `run`.

Both test files change with the tools. On 2026-10-14 the create-topology work removed four of the session's run and list tools (K338). The BLACKBOARD records it as withdrawn, and the tools above are the ones in force.

## 9. Vocabulary to propose before building

The session vocabulary in force is v0.15 (K334). v0.16 to v0.16.3 were withdrawn on 2026-10-14 with the create-topology tool (BLACKBOARD, "The code as it stands"), so the next version is v0.17; a withdrawn number is not reused. The founding lock is past, so the changes are ratified as typed proposals (`grammar/PRINCIPLES.md`, the eight proposal types), each recorded in `process/signals/session-vocabulary.md` and the BLACKBOARD before the code that emits it (§ 10, step 0). Each package's copied `vocabulary.py` carries its own kinds, producer kinds and trigger ids, all named in v0.17.

- **Autonomous build:** `ReviewWritten`; `BuildEnded` (reason: cards done, no progress, stopped); the automatic reply's `slash_source`; producers `end_check`, `auto_reply`, `review_turn`, `review_reply`.
- **Pair coding:** `ReviewWritten` (shared).
- **Best-of-N:** reuses `best_of_n.contracts`; the candidate fields change from text to report and branch; producer `return_on_judge`.
- **Document reviewer:** reuses `Artifact`, `Challenge`; adds `Adjudicated`.
- **Swarm:** `WavePlanned`, `CardReported`, `WaveIntegrated`, `SwarmEnded`.
- **Research sweep:** reuses its four kinds; fields change to report and source.
- **Failure paths (§ 1.3):** producers `drafter_failed`, `writer_failed`, `finder_failed`, `card_failed`, `integrate_failed`, `reader_failed`, `reviewer_failed`, each emitting its role's report kind with a failed outcome; the report kinds gain an `outcome` field where they lack one.
- **Substrate UI:** the manifest's topology field; the event that adds a role session to a held run.

## 10. Order

0. v0.17: the proposals in § 9, ratified and recorded.
1. § 6: topology runs on `RunTable`, growing session lists, the manifest's topology field; and § 8.
2. Best-of-N, the first copy of `session/`. A test checks that a drafter's report crosses into the outer record and its pane opens.
3. The adversarial document reviewer.
4. Autonomous build, then pair coding (copied from it).
5. Swarm.
6. The review panel judge, research sweep, debate.
7. The cuts of § 7.

A topology is kept only after it has run from a session against a real model (the local Ollama models and one cloud model) and its record has been read.

## 11. Two choices for the Architect

- **Debate:** built as in § 5.8, or cut with the other conversation topologies.
- **`code_evolution`:** built with best-of-N in this round, or after it.

## 12. Changes from round 12

Each item answers one finding of the review of round 12.

1. **Open item 33** is cited at its source, `OPEN-ITEMS-2026-10-10.md` line 27 (§ 1.2). The review said it had no anchor; it has one.
2. **The termination rule** is stated once, in § 1.2, and each shape applies it.
3. **Pair coding** says why removing `review_reply` admits the pause (§ 5.2).
4. **Failures in embedded roles.** The review found a failed swarm card would stall at quiescence. The same holds for every fan-in, so § 1.3 gives each embedded role a failure path, and § 5.1 and § 5.3–5.7 each name theirs.
5. **The copy's termination** is deleted and replaced, stated in § 4 and § 5.3.
6. **The panel judge** is named as the exception to the package rule, and three styles over five roles is recorded as a decision with its grounds (§ 5.6).
7. **The sweep's readers** read their sources with their own tool calls; the request carries the path or URL, not the text (§ 5.7).
8. **The vocabulary.** v0.15 is in force, v0.16–v0.16.3 were withdrawn, v0.17 is next, ratified as typed proposals in a new step 0 (§ 9, § 10). The review said to ratify through a vocabulary session; after the founding lock the kit ratifies through the proposal types.
9. **The session's tools.** § 8 names the three tools, their code, their tests, and what each becomes.
10. **The 700 cap** is located in `_speaker_factory` at `conversation.py:165` (§ 5.8). The review placed it in the after-k predicate; it is not there.
11. **§ 4's role sentence** is split into one line per form.
