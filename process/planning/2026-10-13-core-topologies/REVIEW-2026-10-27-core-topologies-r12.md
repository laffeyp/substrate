---
date: 2026-10-27
reviews: process/planning/RESEARCH-2026-10-27-core-topologies-r12.md
scope: SDD discipline, SE canon, terminology, code organization, kernel verification
---

# Review: RESEARCH core topologies round 12

## Kernel verification

The §1.2 termination constraint is the load-bearing claim and it checks out. `runtime.py:847–850` calls `self._cyc.cycle(item)`, then `self._flush_scheduled()`, then `self._consult_termination(st.last_event)`. The cycle's step 6 drains the control queue — each control event runs its own full cycle — so `st.last_event` after a trigger-firing event K is TriggerFired, not K. `finalise_on` (`policies.py:110–113`) checks `c.event.kind == kind`; `threshold_count` (`policies.py:95`) checks `c.counts(kind) >= n`. The doc's distinction between event-keyed and count-keyed policies follows from the code.

Every shape's termination target was traced against the session wiring and the shape's changes. In each case the finalisation kind has no trigger subscriber:

- Daily session: no trigger on Returned or SessionEnded. Correct.
- Run session: no trigger on ReportWritten (report-on-returned *emits* it, subscribes to Returned). Correct.
- Autonomous build: no trigger on BuildEnded. Correct.
- Pair coding: no trigger on ReviewWritten (review_reply is removed). Correct.
- Best-of-N: model-on-user-message removed; no remaining trigger on Returned. Correct.
- Document reviewer: no trigger on Adjudicated. Correct.
- Swarm: plan-on-wave-integrated subscribes to WaveIntegrated, not SwarmEnded. Correct.
- Research sweep: no trigger on Synthesis. Correct.

The §12 corrections to round 11 are all verified as real bugs. Pair coding's pause on Returned with a trigger subscriber would never fire. Best-of-N had no producer for Returned. The document reviewer had no producer for Adjudicated. Each fix is the minimal change.

## Findings

### 1. The end_check predicate reads the filesystem, not a View

§5.1 puts the condition "every input card has status: closed in its front matter in the worktree, or the last k returns added no commit to the branch" in the *predicate* of end-check-on-returned. The kernel's predicate contract is a callable over TriggerContext — the as-of-N Views and staged Routes. Reading the worktree and git log inside a predicate breaks Level-2 replay for that trigger decision: a replay cannot reproduce the filesystem state at the moment the predicate ran.

The topology is non-deterministic overall (model calls), so this doesn't introduce a new class of non-determinism. But it violates the predicate contract's surface. The cleaner design: the trigger's predicate is always-true, and the end_check *producer* reads the filesystem and emits BuildEnded or a no-op continuation event. The decision then lives in the producer (where non-determinism is expected), not the predicate.

### 2. ReviewWritten and ReportWritten: one-character naming distance

§9 introduces ReviewWritten (the standing reviewer's output in autonomous build and pair coding). The existing vocabulary has ReportWritten (a run session's final summary, `vocabulary.py`). Both are `*Written` Struct kinds in the same project. The semantic distinction is clear — a review vs. a run report — but the names collide at a glance. §9's vocabulary proposal should state the distinction explicitly: ReportWritten closes a run session; ReviewWritten carries a standing reviewer's turn output. A reader encountering both in the same topology (pair coding has both: the inner run sessions emit ReportWritten, the reviewer emits ReviewWritten) needs the distinction to be named, not inferred.

### 3. Swarm plan producer: determinism depends on input shape

§5.5 marks `plan` as a deterministic producer. It fires on the first UserMessage "the roadmap and cards." If the input carries full card text and roadmap content as strings in the UserMessage payload, the plan producer parses its input without side effects and the claim holds. If the input carries file paths the producer reads from the worktree, the producer is non-deterministic (filesystem reads). The doc's wording is consistent with the text-in-input reading but never states it. The sprint card should make this explicit.

### 4. threshold_count resume caveat: unstated scope

§1.2 correctly notes that `threshold_count` "is not safe across a resume (counts are restored from the whole record)." §5.8 debate uses `threshold_count(Converged, 1)`. Debate runs as a one-shot through RunTable, so the caveat does not apply. A one-line note in §5.8 would close the question: "Debate runs one-shot; the threshold_count resume caveat (§1.2) does not arise."

### 5. The three-way predicate partition on Returned (§5.1) is the invariant to test

Autonomous build registers three PerEvent triggers on Returned — end_check, auto_reply, review_turn — with predicates that partition the event space. The kernel evaluates all matching triggers and fires all whose predicates hold. If the partition has a gap, no producer fires on that Returned and the topology stalls. If the partition has an overlap, two producers fire and the topology produces conflicting events. Both failure modes are silent at registration time. The design is correct; the build sprint card should name the partition test: for each Returned, assert exactly one of the three triggers fires.

## SDD kit-4 adherence

Checked against the twelve hard rules in `sdd-kit-4/AGENTS.md` and the three procedural disciplines (vocabulary-as-contract, dual contract, resolve-and-record).

**Hard rule 2 (vocabulary is the contract).** §9 proposes every new kind, producer kind, and trigger id per package, and says "ratified before code." No inline invention: each shape names its vocabulary in the proposal section, not buried in its wiring description. The doc also specifies that each package carries its own copied `vocabulary.py`, which isolates kind strings per package. A kind-string retyped across two packages without a shared constant is the drift pattern the kit exists to prevent; per-package vocabulary files are the right countermeasure. One gap: the doc does not name which vocabulary version the proposals target. §9 says "against the session vocabulary as v0.17" but does not say what version the ratified vocabulary becomes (v0.18, or a per-package scheme). The sprint cards will need this.

**Hard rule 6 (sprint sweet spot ≤ 2 files / one concept).** The build order (§10) sequences seven steps. Each topology is one concept. The doc does not break these into sprint cards — it is a research document, not a sprint plan — but the granularity is right: best-of-N is one concept (embedded session drafters replacing bare calls), swarm is one concept (wave-planned parallel builds), and each can be scoped to ≤ 2 files in a sprint card. The autonomous-build shape is the largest, with five new producers; it may need two sprints (the auto-reply/end-check partition, then the review-turn/review-reply chain).

**Hard rule 7 (canonical home registry).** Each shipping topology gets a named package under `topologies/`. The doc names every package: `autonomous_build/`, `pair_coding/`, `best_of_n/`, `document_review/`, `swarm/`, `research_sweep/`, `debate/`. This is the canonical home for each shape's wiring, vocabulary, and producers. The WORKING_AGREEMENT's registry should gain these entries when the packages are created.

**Hard rule 11 (originals over summaries).** §4 says each topology is "made by copying the files of `session/`." Literal file copy, not a summary or abstraction. The doc's §2 writes out the session topology's full wiring — producers, triggers, views, termination — so every §5 change is a change to a named part of a known whole. Round 11 stays on disk; round 12 names its corrections in §12. The round-N versioning follows kit-4's audit trail discipline.

**Hard rule 12 (sprint-0 vocabulary materialization).** §9's vocabulary proposals come before the build order in §10. The doc says "ratified before code" — the vocabulary for each package exists before the package is built. This is the sprint-0 discipline applied per topology.

**Resolve-and-record.** §11 names two choices for the Architect: whether to build debate, and when to build code_evolution. Both are genuine intent questions the project's artifacts do not settle — the grounds (project decisions, SDD practice, engineering practice) do not determine whether debate is worth the build cost or when code_evolution fits the schedule. The doc does not manufacture choices elsewhere; every other design decision is settled in the text on stated grounds (the kernel's termination constraint, the session topology's wiring, the existing run infrastructure).

**Dual contract applicability.** The research document is not a sprint and has no signal or artifact contract of its own. But it sets up the conditions for contracts on the sprints it implies: each shape names its termination, its producers, and its vocabulary, which gives a sprint card enough to write a signal contract (emits) and an artifact contract (files created). The §10 acceptance criterion — "run from a session against a real model and its record read" — is the observation contract principle stated at the topology level: a topology is not accepted on a passing build alone, but on observed behavior in its record.

**Signal-driven, not description-driven.** The doc's §2 describes the session topology as a signal topology: producers emit typed events, triggers fire on subscribed kinds, views project deterministically, termination consults the last event. Every §5 shape is described as changes to this signal flow — not as prose behavior descriptions. The wiring *is* the signal discipline. A shape whose behavior cannot be stated as producer/trigger/view/termination changes is a shape the kernel cannot run, so the constraint is enforced by the representation.

**Vocabulary gap check (Rubber Duck categories applied to the research doc).** Each shape's events are either existing session vocabulary or newly proposed in §9. No shape describes behavior that would emit an unnamed event. The one case worth watching: §5.1's end_check producer, which emits BuildEnded. The BuildEnded kind is proposed in §9 with a reason field (cards done, no progress, stopped). The reason values are a closed enum; the doc names the variants. No gap.

**Context files.** The frontmatter lists 26 files read in the session that produced the document, with line counts. Every file referenced in the text appears in the list. This follows the sprint card pattern of declared context, though the research document is not a sprint card.

## Code organization

Each shipping topology as its own package under `topologies/` follows the existing structure. The session topology remains the single source of truth for the shared wiring; copies inherit it and name their divergences. The alternative — a base class with override hooks — would couple every topology to a shared interface and make the wiring implicit. The copy-and-edit method keeps each topology's wiring readable in one file. The cost is duplication; the doc's §2.5 names what the copy keeps, which bounds the maintenance surface.

§5.6 (review panel judge) is the one shape that modifies an existing module (`runs/review.py`) rather than creating a new package. This is correct: the panel judge is a mode of the existing review, not a new topology. The code_review and fanout_review packages are cut, and their pattern folds into review when multiple styles are requested.

## Terminology

"Append cycle" — project-internal, defined in kernel v15, used consistently. "Instrument" — sugar for producer_kind + trigger, matches `topology.py:instrument()`. "Composition" — `embedded_substrate`, matches `composition.py`. "FiringPolicy" — `Once | PerEvent | PerKey | WhileTrue`, matches `triggers.py`. All terms match their definitions in the kernel code.

"Standing session" (§4, §5.1, §5.8) — a session that persists across turns through `SessionRegistry`, as opposed to a run session that works one turn and ends. The term is used in `delegate.py` and established in the codebase. Consistent.

## Build order (§10)

The dependency chain: §6 (infrastructure) → best-of-N (first session copy) → document reviewer → autonomous build → pair coding (copied from autonomous build) → swarm → review/sweep/debate → cuts. Each step depends only on earlier steps. Best-of-N first is the right choice: it exercises embedded_substrate with session_topology, which every later shape (except review) also uses. A defect in the composition boundary surfaces on the first build, not the fifth.
