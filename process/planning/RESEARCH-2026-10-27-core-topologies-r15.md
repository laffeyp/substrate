---
date: 2026-10-27
round: 15
prior_round: process/planning/RESEARCH-2026-10-27-core-topologies-r14.md
context_files:   # read in full in this session, and in context when this was written
  - path: docs/specs/kernel_spec/v15.md
    lines: 1067
  - path: docs/specs/technical_spec/draft5.md
    lines: 1122
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
  - path: src/substrate/topologies/best_of_n/contracts.py
    lines: 64
  - path: src/substrate/topologies/coding_flow/__init__.py
    lines: 282
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
---

# The topologies that ship (round 15)

*2026-10-27. This document describes the topologies Substrate will ship to a person working in a session: what each one is for, what a person gives it, how a run of it goes from start to end, what comes back, how it stops, and how it fails, in the kernel's own parts. Part 1 says what the topologies are for. Part 2 explains the parts they are built from, with the session topology walked through as the working example. Part 3 describes each topology in full. Part 4 lists what Substrate UI and the vocabulary need, the build order, and what is cut. Rounds 10 to 14 stay on disk; the last section says what each contributed.*

---

## Part 1. What the topologies are for

A person works in Substrate through a session: one conversation with one model, in one workspace, with tools to read, write and run things. Some work does not fit one conversation. A roadmap of twenty cards needs a model to keep working when no person is there to type "continue". A hard change is better tried three ways at once and the one that passes kept. A design document gets better when a second model attacks it. A long list of independent cards finishes sooner when each runs in its own worktree at the same time.

A topology is Substrate's answer to each of these. The person, or the model in their session, starts it with one tool call. It runs while the session carries on. It does its work through sessions of its own: each with its own model, worktree, record and pane, so the person can watch any part of it. It ends with a report that comes back into the session that started it, once, at that session's next step. Nothing it does merges into the person's branch; the person decides.

Eight topologies ship:

| Topology | The person's problem |
|---|---|
| Autonomous build | Work a roadmap's cards to the end without a person at the keyboard, with a reviewer checking for drift. |
| Pair coding | Drive a builder by hand while a reviewer reads every change. |
| Best-of-N | Try one change several ways at once, and keep the one that passes a real check. |
| Document reviewer | Make a document better by having a second model find its worst flaws, round after round. |
| Swarm | Work many cards in parallel, each in its own worktree, merging and testing after each wave. |
| Review panel | Review a change in several styles at once and get one verdict. |
| Research sweep | Answer a question from many sources, each read in full by its own reader. |
| Debate | Argue both sides of a design decision before making it. |

---

## Part 2. The parts they are built from

### 2.1 The kernel, in plain terms

Substrate's kernel (kernel spec v15, `kernel/`) runs a *topology*: a set of parts that write *events* to one ordered, append-only record.

- A **producer** is a piece of work: a model call, a tool run, a git command, a whole inner run. It takes an input and writes events. Its input is sealed when it starts: it gets its own copy of exactly what the record holds, and nothing changes it afterwards.
- An **event** is one line on the record, with a sequence number, a kind (its type name), the producer that wrote it, and a payload. Kinds that begin `substrate.` belong to the kernel: `RunStarted`, `TriggerFired`, `ProducerStarted`, `ProducerCompleted`, `ProducerFailed`, `ProducerCancelled`, `RunFinalised` and five more.
- A **view** is a running summary of some kinds of event, such as a count or a list, kept up to date as each event lands.
- A **trigger** starts a producer. It listens for one or more kinds. When one lands, its *predicate* (a quick yes-or-no question over the views) is asked. If the answer is yes, its *input builder* makes the producer's input, the kernel writes a `TriggerFired` event holding that input, and the producer starts. A trigger fires once per matching event (`PerEvent`), once ever (`Once`), once per key (`PerKey`), or repeatedly with a cooldown (`WhileTrue`).
- A **route** carries something from one event into a later producer's input: a challenge into the writer's next draft, a failure reason into a retry.
- A **termination policy** decides, after each event, whether the run goes on, ends (*finalises*), cancels the others, or *pauses* to wait for outside input.
- **Composition** runs one whole topology as a producer inside another (`embedded_substrate`). The inner run keeps its own record; only the kinds it exports cross into the outer record; if the inner run fails, the outer record gets one `ProducerFailed`.

Every decision lands on the record: which trigger fired, with what input, and why the run ended. A run can be replayed from its record alone.

### 2.2 The session topology, one turn

The session topology (`topologies/session/__init__.py`) is the one topology that works end to end today, and every topology in Part 3 starts as a copy of its files. One turn goes like this.

1. **The session opens.** At run start the kernel writes `RunStarted`. The `session_started` producer writes `SessionStarted` (the model, workspace, tools, settings). The `session_prompt` producer writes one `PromptFragment` per source the session opens with: its role, its guidance bundle's method and style, its length, tone and handoff settings, its environment, its memory indexes, its parent's context, its tool list.
2. **A message arrives.** The person's text arrives as a `UserMessage` (from the `first_message` producer on a fresh record, or as the event that resumes a paused run).
3. **The model starts.** The trigger `model-on-user-message` starts the `model` producer. It builds the whole prompt from the record (the fragments, and the newest turns that fit the model's window), writes it as `PromptComposed`, sends it, and writes the answer as `ModelReply`.
4. **Tools run.** If the reply asks for a tool, the model also writes a `ToolCall`. The trigger `tool-on-tool-call` starts the `tool` producer, which runs it and writes `ToolResult`. The trigger `model-on-tool-result` starts the model again with the result. This repeats until the model answers without a tool, or until the step limit, where `model-wrap-up-on-tool-result` makes it answer in plain text.
5. **The turn ends.** The trigger `return-on-reply` starts the `return` producer, which writes `Returned`. A failed model call (`return-on-model-error`) or an interrupt (`return-on-interrupt`) also writes `Returned`, with that reason.
6. **The session waits.** The termination policy pauses the run on `Returned`, waiting for the next `UserMessage`. The next message resumes it at step 2.
7. **The session ends.** `/exit`, the turn cap, or a `SessionEndRequested` from outside (the person ending it, Substrate shutting down, or a caller stopping it) starts the `session_end` producer, which writes `SessionEnded`. The policy finalises the run.

Other parts sit beside this loop and stay in every copy: interrupts (`InterruptRequested` and the `interrupt_fragment` producer), skills loaded with `/<skill>` (`skill_fragment`), mid-session setting changes (`SessionChanged`), notices of background commands and held runs that ended, and the cuts that keep the history inside the model's window (`TranscriptCompacted`).

### 2.3 A run held by a session

`build` and `review` already work this way, and the topologies in Part 3 follow them. The model in a session calls a tool. The tool makes a worktree, builds a session topology in *run mode* (`RunSpec`: its worktree, its starting commit, its first message), and hands it to the session's run table (`RunTable.start`, `runs/hold.py`). The run table runs it on its own thread and writes `TopologyRunStarted` into the caller's record, naming the run's sessions; the app opens a pane on each. A run-mode session works one turn and then writes `ReportWritten`: its last words, the files it changed, its branch and its commits. When the run ends, the caller's next model step writes `TopologyRunEnded` and reads the report. The caller can stop the run (`run(run_id, action=stop)`), which sends `SessionEndRequested(source=caller_stop)` into it.

### 2.4 Four rules every topology here obeys

1. **A topology a session holds ends by writing `ReportWritten` on its own record.** The run table tells the caller the outcome by reading that event (`hold.py`, `_ended`). A run with no report is told to the caller as failed, unless it was stopped.
2. **A termination policy keyed to an event kind can only see a kind nothing else listens to.** The kernel consults the policy after a whole cascade, with the last event the cascade wrote (`runtime.py`, `_writer_loop`). If a trigger fires on kind K, its `TriggerFired` lands after K, so the policy never sees K. This is open item 33 (`substrate-ui/process/planning/OPEN-ITEMS-2026-10-10.md`, line 27). Every topology below ends on `ReportWritten` or `SessionEnded`, and no trigger listens to either.
3. **A predicate reads only views, and quickly.** Predicates run under a 100 µs budget; three overruns in a row quarantine the trigger. Anything that reads files, git or a model happens in a producer, and the triggers after it decide on that producer's event.
4. **Every role that is counted reports, even when it fails.** When an inner run fails, the outer record gets a `ProducerFailed` and no report. Any topology that waits for N reports would wait forever. So each counted role has a failure producer that listens for its `ProducerFailed` and writes the role's report with a failed outcome. It finds the role's item through a view over the `TriggerFired` events that started the role, which record both the producer instance and its input.

### 2.5 How a topology is made

Each topology is its own package under `topologies/`, made by copying the files of `session/` and then changing the copy. Where it grows out of an existing bundled topology, that topology's wiring is copied in beside it. The copy keeps everything in § 2.2 that the topology does not change, so a topology's sessions have the same prompts, tools, interrupts, settings and compaction as the person's own session. The changes are what Part 3 describes. Calling `session_topology(...)` with other arguments, as `build` does, makes a run of the session topology; it does not make a new topology.

---

## Part 3. The topologies

### 3.1 Autonomous build

**What it is for.** A person and their session have written a roadmap and its sprint cards together, following the SDD kit. The person wants the cards built without sitting at the keyboard to type "continue" after every turn, and without the builder drifting from the roadmap, the cards, or the project's conventions over many turns. The design comes from the 2026-09-24 note (`substrate-ui/process/methodology/2026-09-24-autonomous-build-topology.md`); its numbered points are cited below.

**What the person gives it.** From their session, through a tool call: the roadmap's path, the cards' paths, a paragraph about the project (point 4), and two settings with defaults: how often the reviewer reviews (every n turns, default 4) and how many turns without a commit count as no progress (k, default 3). The tool makes a worktree on a new branch `auto/<run_id>` from the repository's head, and opens a standing reviewer session beside it: a registry session with read-only tools, a reviewer role, and its own worktree detached at the builder's branch head.

**How a run goes.**

1. The run opens as a session does (§ 2.2, step 1), with one more session-open source: the SDD kit with its halt-and-wait steps removed, so the builder works without waiting for approvals (point 11).
2. The first `UserMessage` carries the roadmap path, the card paths and the project paragraph. The builder's model works the first card: it reads, edits, runs the tests, commits, and answers. `Returned` ends the turn.
3. Where the session would pause for a person, this topology does not pause. The trigger `end-check-on-returned` starts the `end_check` producer on every `Returned`. It reads the worktree: each card's front matter, and the git log since the base commit. Then it writes one of two events.
   - If every card says `status: closed`, or the last k turns added no commit, it writes `ReportWritten`: outcome `done` (or `failed` for no progress), the last reply, the files and commits since the base, the branch, and why it ended. The run finalises (point 7).
   - Otherwise it writes `BuildContinued`, carrying the turn count and whether a review is due (the count is a multiple of n).
4. On an ordinary turn, the trigger `auto-reply-on-build-continued` starts the `auto_reply` producer, which writes the next `UserMessage` with `slash_source: auto`, so the record tells it from a person's. Its text is fixed and answers what models usually say at the end of a turn (point 2). The text, to be finished in the build: "Continue with the next open card. If you have a question, answer it from the cards, the roadmap, the SDD kit and established practice, record the answer, and go on. When a card is done, set its `status: closed` and commit." `model-on-user-message` starts the next turn.
5. On a review turn, the trigger `review-turn-on-build-continued` starts the `review_turn` producer instead (point 3). It runs one turn on the standing reviewer (`SessionRegistry.turn_sync`, on a worker thread): the fixed review prompt and the commits since the last review. The reviewer checks for drift against the roadmap, the cards, the SDD kit, established practice and the project's conventions (point 5), and its answer comes back as `ReviewWritten`. The trigger `review-reply-on-review-written` starts `review_reply`, which writes the next `UserMessage`: the review, then "--", then "analyze, verify, apply". The builder's next turn starts on it.
6. The loop repeats from step 3 until `end_check` writes the report.

**What comes back.** The report, into the person's session at its next step: why the build ended, the last reply, the branch `auto/<run_id>`, its files and its commits. Nothing merges.

**How it stops, and how it fails.** The person (or their session's model) can stop it; the run ends `stopped`. If a reviewer turn fails, `review_turn` writes `ReviewWritten` with the error as its text, so the builder is told and the build goes on. If the turn cap is reached (default 200 turns), `end-on-turn-cap` ends the session, and the caller is told the run failed, because no report was written. The cap is an input.

**Point 6.** A second review prompt, off by default, lets the reviewer propose new cards or a new roadmap.

**Its parts.**

| | Kept from the session | New |
|---|---|---|
| Producers | all of § 2.2 | `end_check` (writes `ReportWritten` or `BuildContinued`), `auto_reply` (writes `UserMessage`), `review_turn` (writes `ReviewWritten`), `review_reply` (writes `UserMessage`) |
| Triggers | all of § 2.2 | `end-check-on-returned`, `auto-reply-on-build-continued` (review not due), `review-turn-on-build-continued` (review due), `review-reply-on-review-written` |
| Termination | the pause on `Returned` is removed | `any_of(finalise_on(ReportWritten), finalise_on(SessionEnded))` |

The two triggers on `BuildContinued` ask one yes-or-no question and its opposite, so exactly one fires on each. The build's test checks that every `Returned` is followed by exactly one of a report, an automatic reply or a review.

### 3.2 Pair coding

**What it is for.** The person drives the builder by hand, turn by turn, and wants a second model to read every change as it lands. Today's pair coding (`applications/pair_coding_composite.py`) asks the builder's model to remember to call `delegate` after each change. Here the review happens on every turn whether the model remembers or not.

**What the person gives it.** They open it in the app like a session, naming two models: the builder's and the reviewer's. The app opens two sessions: the builder, and the reviewer as a registry session with read-only tools and the builder as its parent.

**How a run goes.**

1. The person writes a message. The builder works the turn as any session does, and `Returned` ends it.
2. The trigger `review-turn-on-returned` starts `review_turn`, which runs one turn on the reviewer with the fixed review prompt and the commits since the last review. The reviewer's answer lands as `ReviewWritten` on the builder's record.
3. The run pauses on `ReviewWritten`, waiting for the person. The review shows in both panes. The copy adds `ReviewWritten` to the kinds its prompt builder reads, so the builder's next prompt includes it.
4. The person reads the review and writes the next message, which resumes the run at step 1.

**What comes back.** Nothing to a caller: the person is driving. The builder's record holds every turn and every review.

**How it stops, and how it fails.** The person ends it like a session. A failed reviewer turn writes `ReviewWritten` with the error, and the run still pauses for the person.

**Its parts.** It is copied from the autonomous build once that exists. `end_check`, `auto_reply` and `review_reply` are removed, and `review_turn` listens to `Returned` directly. The policy is `any_of(pause_await_input(on ReviewWritten, resume on UserMessage), finalise_on(SessionEnded))`. With `review_reply` gone nothing listens to `ReviewWritten`, which is what lets the pause fire (§ 2.4, rule 2). It runs on the person-driven path, so the app must be able to open a session of this topology (Part 4).

### 3.3 Best-of-N

**What it is for.** One change, tried several ways at once, often by different models, each in its own worktree. A real check (the tests, a build, a linter) judges each attempt, and the first that passes is kept. If none passes, every failure goes back into a fresh round. `coding_flow` and `best_of_n` already wire this loop, but their drafters are single model calls that return text. Here each attempt is a whole session that edits, runs and commits.

**What the person gives it.** From their session, through a tool call: the task, the check command, how many attempts per round (n, default 3), how many rounds (default 2), and optionally one model per attempt.

**How a run goes.**

1. The task arrives as the run's first `UserMessage`. The trigger `seed` starts the `seeder`, which writes n `Draft` events: round 1, one per slot, with no context. The copy removes `model-on-user-message`, so the topology's own model does not try the task itself.
2. The trigger `draft` starts one `drafter` per `Draft`. Each drafter is an inner run: a session in run mode, in its own worktree on branch `bon/<run_id>/<round>-<slot>`, on that slot's model. Its first message is the task and, from round 2, the previous round's failures. It works one turn, commits, and writes `ReportWritten` on its own record. The drafter exports that report onto this record as a `Candidate`: round, slot, branch, worktree, the report.
3. The trigger `validate` starts a `validator` for each `Candidate`. It runs the check command in the candidate's worktree and writes a `Verdict`: passed or not, the exit code, and the output, normalized (`source: gate`). With no command given, the validator is instead a read-only session on a model the person names, and the verdict says `source: model`.
4. When a round's verdicts number n, the trigger `judge` starts the `judge`. If any candidate passed, it writes `Solved` with that slot. If none did and rounds remain, it writes n new `Draft` events for the next round, carrying every failure. Otherwise it writes `Exhausted`.
5. The trigger `report-on-judge` (on `Solved` or `Exhausted`) starts the `report` producer, which writes `ReportWritten`: outcome `done` with the selected branch, or `failed`, and every candidate's branch and verdict in the reply. The run finalises.

**What comes back.** The selected branch, if one passed, and the list of every attempt and its verdict. Nothing merges.

**How it stops, and how it fails.** A drafter whose inner run fails writes nothing. The `drafter_failed` producer listens for its `ProducerFailed` and writes a `Candidate` with no branch and the error, so the validator writes a failing `Verdict` and the round still reaches n (§ 2.4, rule 4). Stopping the run ends it `stopped`.

**Its parts.** From `best_of_n`: the `seeder`, `drafter`, `validator` and `judge` producers, the `verdicts` view, and the `seed`, `draft`, `validate` and `judge` triggers, all through `best_of_n_correction(seed_on="UserMessage", termination=...)`. New: `drafter_failed`, `report`, `report-on-judge`. The copy's own policy is deleted; the only policy is `any_of(finalise_on(ReportWritten), finalise_on(SessionEnded))`. `coding_flow` becomes this topology, and its key-value-store task stays as a test.

### 3.4 Document reviewer

**What it is for.** A design document, a spec or a plan gets better when a second model, told only to find its worst flaws, reads each draft and the writer answers each challenge. `adversarial_pair` wires this loop today with a 200-character writer and a 120-character finder.

**What the person gives it.** The document's path, or a request to draft one; a writer model; a finder model (different from the writer's, so the finder is not grading its own family's work); and the number of rounds (default 3).

**How a run goes.**

1. The first `UserMessage` starts the `writer` at version 0. The writer is an inner run: a session in a worktree on branch `doc/<run_id>`, whose first message is the document's path and the request. It drafts or revises the document, commits, and reports. Its report arrives on this record as an `Artifact`: version, branch, commit, path.
2. The trigger `to-finder` starts the `finder` for each `Artifact`: a read-only inner session on a worktree detached at that commit, told to name the document's worst flaws. Its report arrives as a `Challenge`: the version and the finder's text.
3. The route `stage-challenge` stages the challenge for the writer's next run. While the version is below the round count, the trigger `refine` starts the writer again at the next version, with the challenge in its first message.
4. When the challenge for the last version lands, the trigger `report-on-last-challenge` starts the `report` producer. It writes `ReportWritten`: the branch with the final document, its last commit, and the last challenge, so the person sees what remains. The run finalises.

**What comes back.** The final document on its branch, and the challenge it last answered.

**How it stops, and how it fails.** If the writer or the finder fails, `writer_failed` or `finder_failed` writes `ReportWritten` with outcome `failed`, the version reached and the error. The run ends with a reason, not by going idle.

**Its parts.** From `adversarial_pair`: the `writer` and `finder` producers, the `artifacts` view, the `to-finder` and `refine` triggers and the `stage-challenge` route. New: `report`, `writer_failed`, `finder_failed`, `report-on-last-challenge`. Policy: `any_of(finalise_on(ReportWritten), finalise_on(SessionEnded))`. The roadmap's "information flows compose" example is this topology.

### 3.5 Swarm

**What it is for.** A roadmap whose cards are mostly independent. Each card goes to the smallest model that can do it, in its own worktree, at the same time as the others. After each wave the main model merges the wave's branches and runs the tests, so a conflict or a failure stops the swarm before the next wave builds on it.

**What the person gives it.** The roadmap's path and the cards' paths (or a problem statement, from which a first session on a large model writes the cards), the model for cards, the model for merging, and the project's test command.

**How a run goes.**

1. The first `UserMessage` carries the paths. The `plan` producer reads every card's `files` and `depends_on`. A card waits for the cards it depends on and for any card that shares a file; shared files go first, in a card of their own. A card that names no files is refused, by name, and the run reports it. `plan` writes the first `WavePlanned`, which carries the parsed cards, so a replay reads the plan from the record and not from the files.
2. The trigger `card-on-wave-planned` starts one `card` for each card in the wave. Each is an inner build session (as `start_build` makes one): its own worktree on branch `swarm/<run_id>/<card>`, the card as its first message. Its report arrives as `CardReported`: the card, the outcome, the branch.
3. When the wave's reports equal its card count, the trigger `integrate-on-card-reported` starts `integrate`: an inner session on the merging model, on an integration branch `swarm/<run_id>`. It merges the wave's successful branches, runs the tests, commits, and reports. Its report arrives as `WaveIntegrated`: merged, conflicts, test outcome.
4. The trigger `plan-on-wave-integrated` starts `plan` again. If the wave merged cleanly, its tests passed, and cards remain, `plan` writes the next `WavePlanned` and the run goes back to step 2. Otherwise it writes `ReportWritten`: the integration branch, the cards done, and, if it stopped early, the conflict, the failed test or the failed card by name. The run finalises.

**What comes back.** The integration branch with every merged wave, and the list of cards done and not done.

**How it stops, and how it fails.** A card whose inner run fails is reported by `card_failed` as a `CardReported` with outcome `failed`, so the wave's count is still reached; `integrate` does not merge it, and `plan` ends the run after that wave. A failed integration is reported by `integrate_failed` as a `WaveIntegrated` with the failure, and `plan` ends the run.

**Its parts.** All new: producers `plan`, `card`, `card_failed`, `integrate`, `integrate_failed`; the view `reports` (the current wave's `CardReported`); triggers `plan-on-user-message` (the session's `model-on-user-message` is removed), `card-on-wave-planned`, `integrate-on-card-reported`, `plan-on-wave-integrated`. Policy: `any_of(finalise_on(ReportWritten), finalise_on(SessionEnded))`. Every card's session is known only once its wave is planned, so the app must learn of sessions after the run has started (Part 4).

### 3.6 Review panel

**What it is for.** A change is read in several styles at once (defects, design, security), and a judge reads the reviews and gives one verdict. Today `review` starts one held run per style, each reporting on its own, and the caller reads three separate reviews. `code_review` has the judge, but its five reviewers are one-line prompts on a hard-coded snippet.

**What the person gives it.** The target (a branch, a range or files), the styles (any of `defects`, `design`, `security`), a focus sentence, and the quorum: how many reviews the judge waits for (default: all of them).

**How a run goes.**

1. The first `UserMessage` starts one `reviewer` per style. Each is an inner run-mode session on a worktree detached at the target, with read-only tools, given the style's text, the focus and the diff, exactly as `review` builds one (`runs/review.py`, `first_message`). Its report arrives as a `Critique`: the style and the review.
2. When the critiques reach the quorum, the trigger `adjudicate` (fires once) starts the `judge`: an inner read-only session given every critique and the diff, told to name the most serious problem and end with one verdict word: block, request-changes or approve. Its report arrives as a `Verdict` with that word.
3. When the judge completes, the policy cancels the reviewers still running, which matters only when the quorum is below the number of styles. The trigger `report-on-verdict` starts `report`, which writes `ReportWritten` with the verdict and every critique. The run finalises.

**What comes back.** One verdict, and the reviews behind it.

**How it stops, and how it fails.** A failed reviewer is reported by `reviewer_failed` as a `Critique` saying it failed, so the quorum is still reached. A failed judge is reported by `judge_failed` as `ReportWritten` with outcome `failed` and the critiques it would have read.

**Its parts.** A new package, `topologies/review_panel/`, copied from `session/`, with `code_review`'s quorum trigger and cancel-all-others policy copied in. Producers `reviewer`, `reviewer_failed`, `judge`, `judge_failed`, `report`. Views `critiques` (`KindBuffer(Critique)`). Triggers `reviewer-on-user-message` (one per style), `adjudicate` (`Once`), `report-on-verdict`. Policy: `any_of(cancel_all_others(when the judge completes), finalise_on(ReportWritten), finalise_on(SessionEnded))`. `review` with one style stays as it is.

**Decision: three styles, not five roles.** The panel uses review's three styles, whose texts cite published review practice (`runs/review_styles/README.md`), and drops `code_review`'s five roles (security, performance, style, correctness, clarity), which are one-line prompts. Performance and clarity can return as styles of their own: each is one new text in `review_styles/`.

### 3.7 Research sweep

**What it is for.** A question that needs many sources read in full: a codebase's history, a set of papers, a folder of notes. Each source gets its own reader; a critic names what the findings still miss; a synthesizer writes the answer. `research_sweep` wires this today, but each reader is one model call given the source's text in its prompt, and the CLI cuts each source at 8,000 characters.

**What the person gives it.** The question, the sources (paths or URLs), and the models for readers, critic and synthesizer.

**How a run goes.**

1. The first `UserMessage` starts the `seeder`, which writes one `ReadRequest` per source. The request carries the source's path or URL, not its text.
2. The trigger `read` starts a `reader` per request: a read-only inner session with `read_file` and `web_fetch`, whose first message is the question and the source. It opens and reads the whole source with its own tool calls during its turn, so nothing is cut. Its report arrives as a `Finding`: the source and what it says about the question.
3. When the findings number the sources, the trigger `critique` (fires once) starts the `critic`, an inner session given every finding and told to name what is still missing. Its report arrives as `Gaps`.
4. The trigger `synthesize` (fires once) starts the `synthesizer`, an inner session given the findings and the gaps, told to answer the question and say where the gaps limit the answer. Its report arrives as `Synthesis`.
5. The trigger `report-on-synthesis` starts `report`, which writes `ReportWritten` with the answer, the gaps and the sources. The run finalises.

**What comes back.** The answer, what it could not cover, and which source said what.

**How it stops, and how it fails.** A failed reader is reported by `reader_failed` as a `Finding` naming the failure, so the critique still fires and the gap is named. A failed critic or synthesizer is reported as `ReportWritten` with outcome `failed` and the findings so far.

**Its parts.** From `research_sweep`: the `seeder`, `reader`, `critic` and `synthesizer` producers, the `findings` view, and the `read`, `critique` and `synthesize` triggers. New: `reader_failed`, `critic_failed`, `synthesizer_failed`, `report`, `report-on-synthesis`. Policy: `any_of(finalise_on(ReportWritten), finalise_on(SessionEnded))`.

### 3.8 Debate

**What it is for.** Before a design decision, two models argue opposite sides of it, each keeping its own context and tools across rounds, so the person sees the strongest case on each side. `debate` today argues one fixed claim with two bare model calls, each turn cut at 700 characters (`conversation.py`, `_speaker_factory`, `text[:700]`).

**What the person gives it.** The claim, the two sides, the speakers' models, and the number of rounds (default 3).

**How a run goes.**

1. The tool opens two standing registry sessions, one per side, each told its side and the debate's rules (steelman the other side first, then answer it, with concrete examples).
2. The first `UserMessage` starts speaker 1. A speaker's turn is one turn on its standing session (`SessionRegistry.turn_sync`), given the transcript so far. Its answer lands as a `Turn`: speaker, round, the whole text.
3. After each `Turn`, the trigger for the next speaker (`after-1`, `after-2`) starts the other side, while rounds remain. A speaker that says the two sides have converged writes `Converged`.
4. After the last speaker's last round, or on `Converged`, the trigger `report-on-last-turn` starts `report`, which writes `ReportWritten` with each side's strongest point and the transcript. The run finalises.

**What comes back.** Both cases, argued to the end, and where they met.

**How it stops, and how it fails.** A failed speaker turn is reported as a `Turn` saying so, and the debate goes on to its end.

**Its parts.** From `conversation.py`: the speaker producers, the `after-k` triggers and the `transcript` view. New: `report`, `report-on-last-turn`. Policy: `any_of(finalise_on(ReportWritten), finalise_on(SessionEnded))`. Whether to build it is one of the Architect's two choices below.

---

## Part 4. What has to be built around them

### 4.1 Substrate UI

- **Opening a session of another topology.** Pair coding runs on the path a person drives. Today the app builds every session through one function, `_build_session_topology_from_manifest` (`server.py:653`), which always calls `session_topology(...)`. The session's manifest gains a field naming its topology's package, and that function builds the named package. A manifest without the field builds the session topology, as now.
- **Starting a topology from a session.** Every other topology is held by the session that starts it, as `build` and `review` are. Today `run_topology` goes over HTTP to `_topology_run` (`server.py:3563`), which runs one of three applications outside the run table: no `TopologyRunStarted`, no panes, no stop, no notice. `run_topology` instead starts the topology on the run table and returns at once with a run id. `list_topologies` returns the eight topologies with each one's inputs as a tool schema, as `build`'s schema is. `run_topology_poll` gives way to `run(run_id, action=events)`, which `build` and `review` already use. These three tools are named in `tool_loop/tools.py` (lines 75–78), built for every session in `server.py` (lines 703–714), and tested in `tests/test_substrate_tools_list_228.py` and `tests/test_realmodel_tool_comprehension.py`. The bundled demo registry stays for `substrate demo` and the committed records `scripts/gen_topology_records.py` writes.
- **Sessions that start after the run does.** The run table records a run's sessions once, at start (`HeldRun.sessions`), and the app opens panes from `TopologyRunStarted`. Swarm's cards and best-of-N's later rounds start later. The run table must add a session to a held run when it starts, and tell the app.

### 4.2 Vocabulary

The session vocabulary in force is v0.15. v0.16 to v0.16.3 were withdrawn on 2026-10-14, so these changes are v0.17, each proposed as one of the kit's typed proposals and recorded in `process/signals/session-vocabulary.md` before the code that writes it. Each package's own `vocabulary.py` holds v0.17's names for that package.

- New kinds: `BuildContinued`, `ReviewWritten`, `WavePlanned`, `CardReported`, `WaveIntegrated`, `Critique`.
- Changed kinds: `Candidate` (branch, worktree, report, in place of `response`), `Artifact` (branch, commit, path), `Challenge` (the finder's whole text), `ReadRequest` (source path or URL, in place of content), `Verdict` (gains the panel's verdict word; best-of-N keeps `passed`).
- New `slash_source` values: `auto` (the automatic reply), `review` (a review sent back to the builder).
- `ReviewWritten` and `ReportWritten` are different things: `ReportWritten` closes a run-mode session; `ReviewWritten` carries one turn of a standing reviewer. Each kind's note says so.

### 4.3 Order

0. The v0.17 proposals, ratified and recorded.
1. Part 4.1: topology runs on the run table, sessions added after start, the manifest's topology field, the three tools.
2. Best-of-N: the first copy of `session/`, and the first use of an inner run as a role. Its test checks that a drafter's report crosses into the outer record and its pane opens.
3. The document reviewer.
4. The autonomous build, in two sprints: the end check and the automatic reply, then the review. Then pair coding, copied from it.
5. Swarm.
6. The review panel, the research sweep, debate.
7. The cuts below.

Each package's row goes into `process/WORKING_AGREEMENT.md`'s canonical home registry when it is made. A topology ships only after it has run from a session against a real model (the local Ollama models and one cloud model) and its record has been read.

### 4.4 What is cut from what a session can see

Cut means removed from `list_topologies`, `run_topology` and the guidance; the code stays in Substrate.

| Topology | Why |
|---|---|
| `pair_coding_chunked` | Its driver returns canned chunks and ignores the model. Pair coding (3.2) replaces it. |
| `code_review`, `fanout_review` | The review panel (3.6) replaces them. |
| `best_of_n_verified` | Best-of-N (3.3) replaces it. |
| `recursive_decomposition` | Its planner writes the strings "part 0" and "part 1". `delegate`'s limits (5 deep, 16 per call, 64 per tree) already bound real recursion. |
| `prisoners_dilemma`, `intel_asymmetry`, `natural_conversation`, `natural_conversation_bare` | Fixed scenarios for measuring conversation dynamics; kept for that research. |
| `game_of_life`, `game_of_life_glider` | A simulation with no model; the glider stays the fixture of the pixel-decode harness. |
| `tool_loop` | The session topology supersedes it; its tool suite stays the session's. |
| `swebench_repair` | The benchmark solver; kept for benchmarking. |

`code_evolution` is not in the bundled registry and is not session-facing now.

### 4.5 Two choices for the Architect

- **Debate:** build it as in 3.8, or cut it with the other conversation topologies.
- **`code_evolution`:** build it alongside best-of-N, whose drafter change it needs, or after.

---

## What the earlier rounds contributed

Round 10 named the shapes and the audit. Round 11 set the build method: copy the session topology's files and change the copy. Round 12 wrote the session topology's wiring from the code, and found that a termination keyed to an event never sees an event a trigger listens to. Rounds 13 and 14 applied two reviews: a failure path for every counted role, and moving the autonomous build's file reads out of trigger predicates into one producer. This round describes each topology whole, and adds two findings from `runs/hold.py` and `runs/review.py`. A held topology must end with `ReportWritten`, or its caller is told it failed. And `review` starts one held run per style, so a panel judge cannot be added inside it: the review panel is a topology of its own.
