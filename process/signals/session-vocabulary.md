**Status: v0.11 IN FORCE — v0.12 to v0.13 WITHDRAWN (2026-10-14).** The code of kernel sprints K314–K324 is reverted, and the topologies are rebuilt from research round 9 (`process/planning/RESEARCH-2026-10-14-core-topologies-r9.md`), which removes the card's done-condition, the checks, the retry loop and the judge. § X (v0.12–v0.12.4) and § Y (v0.13) stay below as history; the rebuild proposes its events as a new version before any code.

**Status: RATIFIED — v0.13 (2026-10-13).** Sprint K324 adds § Y: a third control, `handoff`, for how readily the model hands work to a topology (`delegate`, `review`, `build`) instead of doing it itself (research r8 § 5), and the measure of its effect, topology calls per turn. Agent-resolved; additive.

**Status: RATIFIED — v0.12.4 (2026-10-13).** Sprint K322 adds `ChecksRun.judge` (§ X.3): the checking role's call that judged the card's statement checks, its model, prompt and reply. A statement check's `passed` is now the judge's answer and its `note` the judge's reason; `ChecksRun.passed` requires every statement to hold. r8 § 3.4 asks that checks be run by a role that did not do the work; until now statements were run by no one, and a card whose done-condition was a statement ended `done` unexamined. Agent-resolved; additive except `passed`, which now counts statements.

**Status: RATIFIED — v0.12.3 (2026-10-13).** Sprint K319b adds `RunPaused` and `RunResumed` (§ X.3) and the trigger `continue-on-resumed` (§ X.5): a caller pauses and resumes a driven run on its record. § X.8 left pause "until K319 shows otherwise"; K319 showed that an idle run whose termination says continue is failed as stuck, so a pause must be on the record for the termination to read. Agent-resolved; additive.

**Status: RATIFIED — v0.12.2 (2026-10-13).** Sprint K318 adds `ChecksRun.head` (the worktree's commit at the check, so a stall is read from the record), the trigger `card-on-session-prompt` (the card waits for a session prompt, as `first_message` does), and restates the card's order rule in § X.6: `CardAccepted` precedes the first `UserMessage` (a session prompt's fragments may come first). Agent-resolved; additive except the restated rule, which loosens it.

**Status: RATIFIED — v0.12.1 (2026-10-13).** Sprint K316 adds `CardCheck.expect_exit` (§ X.3): a command check's expected exit code, 0 unless the card says otherwise. `PAYLOAD_FIELD_PROPOSED` from the SDD kit's own example card 003 ("`python -m wordcount tests/fixtures/sample_tree/` returns 2"); additive.

**Status: RATIFIED — v0.12 (2026-10-13).** Sprint K314 adds section X: the events of a topology run in its caller's record and in its own, the producers and triggers of a driven session, the ordering rules, and the report. The vocabulary session for the topology layer of `process/planning/RESEARCH-2026-10-13-core-topologies-r8.md` (approved by the Architect, 2026-10-13). Agent-resolved on the grounds in § X.8. §§ A–W byte-preserved.

**Status: RATIFIED — v0.8 (2026-10-11).** Sprint K296 adds section T: two controls a session opens with, Length and Tone, each a typed set of positions whose text reaches the model as a `control` fragment. Directed by the Architect, 2026-10-11 (substrate-ui OPEN-ITEMS 16). §§ A–S byte-preserved.

**Status: RATIFIED — v0.7 (2026-10-11).** Sprint K291 adds section S: history compaction clears old tool outputs before it drops turns, and records a cut only when it changes. Directed by the Architect, 2026-10-11; research in `process/planning/RESEARCH-2026-10-11-compaction.md`. §§ A–R byte-preserved; where S differs from D, S governs records written from v0.7 on.

**Status: RATIFIED — v0.3.1 (2026-10-09).** Sprint K261 adds section L: the model producer builds, records and sends each prompt; the composer and the per-turn chain retire. §§ A–K byte-preserved; where L differs from K, L governs.

**Status: RATIFIED — v0.3 (2026-10-09).** Sprint K259 adds section K: `ModelReply` becomes one event per model call with `stop_reason` and `usage`; `Returned` replaces `Park`; a session record no longer carries `FinalAnswer`; the producers and triggers take the names in K.4 and K.5. Decisions by the Architect, 2026-10-09; research in `process/planning/RESEARCH-2026-10-09-session-topology-structure-round4.md`. §§ A–J byte-preserved from v0.2.1; where K differs from them, K governs records written from v0.3 on.

# session — locked topology vocabulary

**Status: RATIFIED — v0.2.1 (2026-09-02).** Sprint 068 adds `SessionWarning.kind` value `"fragment_source_failed"` and optional payload field `source_name: str?`. Additive per the § H convention; §§ A-I byte-preserved from v0.2. Surfaces fragment-source Producer failures as operator-visible warnings on the record.

**Status: RATIFIED — v0.2 (2026-09-01).** Sprint 058 adds two application event kinds — `PromptFragment` and `PromptComposed` — plus the `PromptSource` enum for `PromptFragment.source`. Additive per the § H convention: §§ A-H byte-preserved from v0.1; the new material lives in § I. Ratifies the SDD entry gate for the prompt-composition arc (sprints 058-066) that rebuilds prompt composition as Producer emissions instead of inline string concatenation.

**Status: RATIFIED — v0.1 (2026-08-25).** Architect ratified in `substrate/process/BLACKBOARD.md ## Decisions` on 2026-08-25 (see the entry naming this doc + sprint 202 close). Locks the eight application event kinds the daily-driver session topology emits per `TECH-SPEC-2026-08-25-round6.md` §3 + §3a. Sprint 203 (substrate-ui side v0.6 lock + pairing) dispatches on this ratification; sprint 204 (canonical-home registry + piece-0 close) follows.

Designed BEFORE code (Sprint-0 discipline per sdd-kit-2 hard rule 12). The topology records are frozen msgspec Structs, topology-local, registered in `substrate/process/WORKING_AGREEMENT.md`; this doc locks their fields, the §G dual-contract audit against substrate-ui grader tags (sprint 203), and the cadence rules for ambient kinds. Strict validator-extras (project posture).

Design: `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §3 (topology + events), §3a (transcript renderer + cadence), §1.6.5 (seed assembler). Product-spec derivation: `PRODUCT-SPEC-2026-08-17-round12.md` §3, §4, §4a.

Home: `substrate/src/substrate/topologies/session/` (piece A of the daily driver, sprint 205 authors the Structs; this doc locks their contract).

## A. Case convention

Two shapes ride the record; two casing rules.

- **PascalCase** — msgspec Structs the topology declares via `producer_kind(schemas=[...])` at `substrate/src/substrate/kernel/topology.py:137`. Matches the kernel's own reserved lifecycle set (`substrate.RunStarted`, `substrate.TriggerFired`, `substrate.ProducerCompleted`, …). All eight kinds in v0.1 (§§ B-E) use PascalCase.
- **SCREAMING_SNAKE** — reserved for future wire events with no dedicated Struct that the kernel itself might add. Application code (the daemon at `substrate-ui/server.py`) cannot emit through `_Lifecycle` per F-API-6 (`import-linter` at `cli.py:2-8`); every application signal is a Producer emission with a Struct schema. v0.1 has no wire events; the convention is documented for future kernel additions only.

`SessionCompositeSpec` (mentioned in earlier draft rounds) is a daemon-internal dataclass returned by `pair_coding_application`; it will live at `substrate/src/substrate/topologies/applications/pair_coding_composite.py` (Sprint 225 authors it — the file does not exist yet), never lands on a substrate record, and is deliberately not in this lock.

## B. Session lifecycle records

Three kinds bracket every session record: `SessionStarted` opens at seq 1; `SessionEnded` closes the record; `SessionEndRequested` is an external injection the daemon uses on `POST /api/session/<id>/end`.

### SessionStarted

| Field | Type | Meaning |
|---|---|---|
| `session_id` | `str` | ULID prefixed `s_`; matches the manifest at `~/.substrate/sessions/<session_id>/`. |
| `seed` | `str` | Assembled per §1.6.5 (role prompt + bundle methodology + project context + task + baseline). Verbatim — every future turn reads this from the record. |
| `driver_model` | `str` | The driver's name (e.g. `"kimi-k2.6:cloud"`, `"claude"`, `"deterministic"`). |
| `driver_context_tokens` | `int` | Driver's declared context window (§3a lookup). Drives the rolling-window K. |
| `tool_suite` | `tuple[str, ...]` | Tool names the topology composed at open — deterministic order. |
| `workspace_path` | `str` | Absolute path where `edit_file`/`write_file`/`bash` operate. |
| `workspace_shape` | `str` | `"flat" \| "worktree" \| "isolate"` per §9c product spec Mode 1/2/3. |
| `bundle` | `str \| null` | Bundle name if any. |
| `baseline` | `dict[str, Any]` | The full auto-baseline dict (repo_root, branch, readme_head, git_diff, commit, cwd/user/hostname). |
| `parent_session_id` | `str \| null` | Non-null when the session was opened as a standing sub-agent from a delegate call. |
| `parent_seq_at_call` | `int \| null` | Seq on the parent's record at the moment of the delegate call. |

Stratum: **event**.

### SessionEnded

| Field | Type | Meaning |
|---|---|---|
| `reason` | `str` | One of `"user_exit"` (model saw `/exit`), `"user_end"` (daemon POST /end), `"timeout"` (200-turn cap), `"daemon_shutdown"` (SIGTERM). Four values, four distinct paths. |
| `total_turns` | `int` | Count of UserMessage kinds on the record at close. |

Stratum: **event**. Terminal for the record — followed only by `substrate.RunFinalised`.

### SessionEndRequested

| Field | Type | Meaning |
|---|---|---|
| `reason` | `str` | `"user_end"` \| `"daemon_shutdown"`. The daemon injects this via `Runtime.resume` (external event, `runtime.py:409-450`); the `end-on-user-end` trigger fires `session_end` which emits `SessionEnded` with the same reason. |

Stratum: **event**. At most one per session. Never emitted by the topology itself; always daemon-injected.

## C. Turn records

Three kinds compose each user turn: `UserMessage` opens; zero or more `ModelReply` + `ToolCall`/`ToolResult` pairs run between; `Park` closes the turn and pauses the topology awaiting the next `UserMessage`.

### UserMessage

| Field | Type | Meaning |
|---|---|---|
| `text` | `str` | What the user typed (or what the daemon injected). |
| `turn_index` | `int` | 0-based; monotonically increasing across the session. |
| `assembled_prompt` | `str` | The exact bytes the daemon fed to the model: `per_turn` prefix (from §7b bundle) + `text`. Recorded so debug is deterministic. |
| `slash_source` | `str \| null` | Provenance: `"chat"` (typed) \| `"/context"` (slice attached) \| `"delegate"` \| `"resume"`. |

Stratum: **event**. `turn_index` values are contiguous and start at 0.

### ModelReply

| Field | Type | Meaning |
|---|---|---|
| `text` | `str` | Model reply text. |
| `model_usage` | `dict[str, Any]` | From `substrate.adapters.models.ModelUsage` — prompt_tokens, completion_tokens, wall_ms, model, estimated. |
| `turn_index` | `int` | Matches the enclosing UserMessage's turn_index. |

Stratum: **event**. Zero or more per turn (tool-loop may fire model multiple times).

### Park

| Field | Type | Meaning |
|---|---|---|
| `awaiting` | `str` | `"UserMessage"` in v0.1. Leaves room for other await kinds. |
| `turn_index` | `int` | The turn that just parked. |
| `reason` | `str` | `"final_answer"` (model produced FinalAnswer) \| `"model_error"` (model producer failed) \| `"interrupt"` (POST /interrupt cancelled the model producer). |

Stratum: **event**. Exactly one after each `FinalAnswer`, `substrate.ProducerFailed{producer.kind:"model"}`, or `substrate.ProducerCancelled{producer.kind:"model"}`.

## D. Transcript compaction (ambient)

### TranscriptCompacted

| Field | Type | Meaning |
|---|---|---|
| `strategy` | `str` | `"rolling_window"` in v0.1. `"summary_tail"` in v1.5. `"semantic"` deferred. |
| `dropped_seq_range` | `tuple[int, int]` | Inclusive seq range of the events dropped from the threaded prompt. Non-empty when the event fires. |
| `kept_seq_start` | `int` | First seq threaded into the current model prompt. Always strictly greater than `dropped_seq_range[1]`. |
| `reason` | `str` | `"driver_window_exceeded"` (K forced the drop) \| `"K_bound"` (K < len(turns) even with headroom) \| `"bundle_changed"` (mid-session bundle PATCH re-assembled the seed). |
| `tokens_before` | `int` | Estimated token count of the pre-compaction prompt (word-count proxy). |
| `tokens_after` | `int` | Estimated token count of the post-compaction prompt. `tokens_after ≤ tokens_before`. |

Stratum: **ambient**.

**Cadence.** At most one per `model` producer firing. Never fires when `turns_dropped == 0` — the model producer yields it only when the renderer's `RenderedTranscript.compaction_events` is non-empty. Grader invariant: for every `TranscriptCompacted{seq=S}`, no other `TranscriptCompacted` appears in `[S-1, S]`.

## E. Session-warning event

### E.1 SessionWarning

A frozen msgspec Struct emitted by a small `session_warning` producer inside `session_topology`. The producer fires once at session-open when a condition trips (initial: `seed_alone_exceeds`) and once per subsequent condition (e.g. `bundle_changed` on a PATCH that swaps the bundle). Reaching into the kernel's private `_Lifecycle` from daemon code would break the F-API-6 discipline (`import-linter` at `cli.py:2-8`); a Producer keeps the emission inside the topology where every other application signal lives.

`session_warning` producer schema: `[SessionWarning]`. Trigger: `warn-on-condition` — subscribes to a small daemon-injected `SessionWarningRequested` kind (parallel to `SessionEndRequested`); daemon POSTs it via `Runtime.resume` at session-open when a condition trips, and again mid-session on `PATCH /api/session/<id> {bundle: <new>}` that changes the name.

Renamed from `SESSION_WARNING` (SCREAMING_SNAKE convention from an earlier draft where the record wrote it directly). PascalCase now that it is a Struct.

| Field | Type | Meaning |
|---|---|---|
| `kind` | `str` | The condition. v0.1 values: `"seed_alone_exceeds"`, `"bundle_changed"`. |
| `seed_tokens` | `int?` | Present when `kind == "seed_alone_exceeds"`. Estimated seed token count. |
| `driver_context_tokens` | `int?` | Present when `kind == "seed_alone_exceeds"`. The threshold the seed exceeded. |
| `old_bundle` | `str?` | Present when `kind == "bundle_changed"`. |
| `new_bundle` | `str?` | Present when `kind == "bundle_changed"`. |

Stratum: **ambient**. Every `SessionWarning` is a Producer emission with a subject producer ref on the envelope (`session_warning`), not a bare `_Lifecycle` frame with `producer=null`.

**Cadence.** At most one per `(session_id, kind)` pair. A second `SessionWarning{kind:"seed_alone_exceeds"}` on the same session_id is a grader violation. `bundle_changed` fires only on a PATCH that actually swaps the bundle name — a same-name PATCH emits nothing.

**§A convention update.** Section §A named `SESSION_WARNING` as the one wire event in v0.1. That was wrong per F-API-6: daemon code cannot emit into `_Lifecycle`. v0.1 has zero wire events with no Struct; every kind is PascalCase and Producer-emitted. §A's convention rule stands (SCREAMING_SNAKE reserved for genuine daemon-side wire events), but v0.1 uses none.

## F. Invariants (the `checkSessionBookends` grader)

The substrate-ui grader `checkSessionBookends` at v0.6 (sprint 203) enforces these against the record. Every session's record satisfies each rule.

1. Exactly one `SessionStarted` per record, at seq 1 (seq 0 is `substrate.RunStarted`).
2. Exactly one `SessionEnded` per record OR the record's status is `paused` at grader read time. A finalised record with no `SessionEnded` is a violation.
3. No repeated `substrate.RunStarted` on one `session_id` across resumes. `Runtime.resume` restores the run_id from the existing manifest per `runtime.py:409-450`; a second RunStarted would signal a resume bug.
4. Every `UserMessage{turn_index=N}` at seq S is followed at a seq greater than S by at least one of `FinalAnswer`, `substrate.ProducerFailed{producer.kind:"model"}`, or `substrate.ProducerCancelled{producer.kind:"model"}` before the next `UserMessage` OR the record's terminal event. Grader-checkable from seq alone; `t` is supplementary per substrate's own convention and not used here.
5. Every `Park` is preceded — at a strictly lower seq within the same `turn_index` — by exactly one terminal matching its `reason`. `Park{reason:"final_answer"}` by exactly one `FinalAnswer`; `Park{reason:"model_error"}` by exactly one `substrate.ProducerFailed{producer.kind:"model"}`; `Park{reason:"interrupt"}` by exactly one `substrate.ProducerCancelled{producer.kind:"model"}`. Matches §C's three-terminal contract.
6. `TranscriptCompacted.dropped_seq_range` is a contiguous seq range strictly below `kept_seq_start`.
7. `SessionWarning` fires at most once per `(session_id, kind)` pair.
8. `turn_index` values on UserMessage kinds are contiguous starting at 0.

## G. Dual-contract audit (paired to substrate-ui v0.6)

Per BOOTSTRAP.md § "Dual-contract audit," every behavior tag on the substrate side pairs with a view/structural target on the substrate-ui grader side. Sprint 203 (`substrate-ui/signals/versions/0.6.json`) authors the paired UI tags. Bidirectional table:

| Substrate kind | Substrate-ui pairing | Pairing shape |
|---|---|---|
| `SessionStarted` | `DRIVER_SESSION_STARTED` | named tag |
| `UserMessage` | `USER_MESSAGE_INJECTED` | named tag |
| `ModelReply` | `PANE_SCROLLED{model_reply_ref}` | structural payload on a v0.6 tag (`PANE_SCROLLED` is new in v0.6; `model_reply_ref` in `optional_payload` carries the substrate seq of the reply that caused the scroll) |
| `Park` | `PARK_LANDED` | named tag |
| `SessionEnded` | `DRIVER_SESSION_ENDED` | named tag (v0.5's `SESSION_ENDED` is browser page unload — different object; the `DRIVER_` prefix keeps v0.6 a strict superset of v0.5 per Architect ratification 2026-08-25) |
| `SessionEndRequested` | `DRIVER_SESSION_END_REQUEST_ISSUED` | named tag (ratified 2026-08-25) |
| `TranscriptCompacted` | `TRANSCRIPT_COMPACTED_LANDED` | named tag |
| `SessionWarning` | `DRIVER_SESSION_WARNING_EMITTED` | named tag |

Every row's UI target must exist in `substrate-ui/signals/versions/0.6.json` at sprint 203's close. A missing pairing is a `vocabulary_change_required` halt on piece 0.

## H. Ratification signature

- **v0.1** — Sprint 202 close, 2026-08-25. Locks the eight session-topology kinds ahead of piece A (sprint 205 authors the Structs). Architect ratifies in `substrate/process/BLACKBOARD.md ## Decisions` — the Decision entry unblocks piece A dispatch per sprint 204.
- **v0.2** — Sprint 058 close, 2026-09-01. Adds two kinds (`PromptFragment`, `PromptComposed`) and the seven-value `PromptSource` enum. Additive; §§ A-H byte-preserved from v0.1. Structs live at `substrate/src/substrate/topologies/session/__init__.py`; kind-name constants at `substrate/src/substrate/topologies/session/vocabulary.py`.

*Additions follow the swebench-solver-vocabulary pattern: bump the header status to `RATIFIED — v0.X`, add a new lettered section at the bottom, byte-preserve prior sections. Never re-flow.*

## I. v0.2 — prompt composition (2026-09-01, sprint 058)

Two Structs and one enum name the fragment / composer shape the prompt-composition arc (sprints 058-066) rebuilds around. Motivation: every existing composition site (`session/__init__.py::_model_factory` at ~L301/L334/L349, `session/transcript.py::_render`, `tool_loop/delegate.py::_prefix_context_slice`) builds prompt text via inline f-string or `"\n\n".join(parts)`. The composed prompt reaches the model but leaves zero record trace. Replay cannot reconstruct which fragment came from where; `record diff` cannot show a fragment-level change; a View cannot count fragments per session or measure tokens per source. Two typed events fix that at the primitive layer, without adding kernel vocabulary.

### PromptFragment

Emitted by each fragment-source Producer (sprints 060-064). One per source per relevant firing: session-open sources fire once at `substrate.RunStarted`; turn-scoped sources fire once per relevant turn.

| Field | Type | Meaning |
|---|---|---|
| `source` | `str` | One of the seven `PromptSource` values below. Identifies which producer emitted this fragment. |
| `text` | `str` | The fragment contents, as the model will read them. Verbatim. |
| `precedence` | `int` | Composer ordering key. Lower fires earlier in the composed text. Reserved band: `role=0`, `bundle_personality=3`, `bundle_methodology=5-9`, `per_turn=10`, `wrap_up=15`, `tools_suite=20`, `parent_context=30`, `user_message=100`. |
| `provenance` | `dict[str, Any]` | Source-specific audit trail. `role`: `{"role_name": <str>, "resolved_from": <path>}`. `bundle_*`: `{"bundle_name": <str>, "extends_chain": [<names>]}` or `{"chain_position": <int>}`. `parent_context`: `{"parent_record_root": <str>, "parent_seq_range": [lo, hi], "kinds": [...]}`. `per_turn`, `tools_suite`, `user_message`: `{}` or small source-specific dicts. Not typed further at this layer; the source's own tests pin its provenance shape. |

Stratum: **event**. Multiple per session (one per source per firing); zero when a source's input is empty (empty per_turn, no bundle, no parent context).

### PromptComposed

Emitted by the composer Producer (sprint 059) exactly once per model firing. Carries the assembled prompt plus the seq references of every fragment that composed it, so a reader can trace back through the record without re-executing the composition.

| Field | Type | Meaning |
|---|---|---|
| `text` | `str` | The assembled prompt the model receives. Bytes-identical to what the driver reads. |
| `fragment_seqs` | `tuple[int, ...]` | Seq of every `PromptFragment` that composed into `text`, in composition order (lowest precedence first). Empty tuple when the cohort was empty (`text == ""`). |
| `total_tokens` | `int` | Estimated token count of the composed text (chars/4 heuristic per `transcript.py`). |
| `strategy` | `str` | `"precedence_join"` in v0.2. Leaves room for a v0.3 template strategy. |

Stratum: **event**. Exactly one per model firing anchor (per turn in the common case; the wrap-up path may fire the composer a second time on the same turn — sprint 064 pins the choice).

### PromptSource enum

Seven string values name the initial fragment sources. Extending the enum bumps the session vocabulary version (v0.2 → v0.2.1 → v0.3 as sources land in sprints 060-064). Kind-name constants at `session/vocabulary.py`.

| Value | Meaning |
|---|---|
| `per_turn` | Manifest `per_turn` string, session-scoped, precedence 10. Sprint 060 wires. |
| `role` | Four-layer role prompt (`session/roles.py::resolve_role_prompt`), session-scoped, precedence 0. Sprint 061 wires. |
| `bundle_methodology` | Bundle methodology slot text (walking the extends chain), session-scoped, precedence 5.0-5.9. Sprint 062 wires. |
| `bundle_personality` | Bundle personality slot (caller-wins across extends chain), session-scoped, precedence 3. Sprint 062 wires. |
| `parent_context` | Delegate context slice from parent record, session-scoped, precedence 30. Sprint 063 wires. |
| `tools_suite` | `suite_describe(tools)` output, session-scoped, precedence 20. Sprint 064 wires. |
| `user_message` | Current turn's UserMessage text, turn-scoped, precedence 100. Sprint 064 wires (uniform shape). |

### Cadence

`PromptFragment` fires at its source's own trigger anchor (`substrate.RunStarted` for session-scoped sources; `UserMessage` for turn-scoped sources). `PromptComposed` fires on the model producer's input anchor, after the current turn's fragment cohort has landed. Grader invariant: every `PromptComposed{seq=S}` at model firing M has `fragment_seqs` containing only fragments whose seq is strictly less than S; the composition is causal.

### Dual-contract audit (v0.6 substrate-ui pairing not yet authored)

The § G table (v0.1) pairs every substrate session kind with a substrate-ui grader tag. The v0.2 pair extends by two rows once sprint 059 lands a live emit site: `PromptFragment` pairs with a UI tag TBD when composer telemetry surfaces in the console; `PromptComposed` pairs with a UI tag TBD when the prompt inspector surfaces. Both are companion-sprint work on the substrate-ui side; not blocking for v0.2 ratification.

## J. v0.2.1 — fragment-source failure warning (2026-09-02, sprint 068)

Additive extension to `SessionWarning`. `kind` gains one value; an optional payload field lands. The pre-arc `SessionWarning` shape stays: existing consumers reading `kind`, `seed_tokens`, `driver_context_tokens` are unaffected.

### SessionWarning — v0.2.1 additions

`SessionWarning.kind` gains value `"fragment_source_failed"`. Fires when any producer whose kind is in `FRAGMENT_SOURCE_KINDS` emits `substrate.ProducerFailed`. The set is documented at `src/substrate/topologies/session/vocabulary.py::FRAGMENT_SOURCE_KINDS`: `per_turn_fragment`, `role_fragment`, `bundle_methodology_fragment`, `bundle_personality_fragment`, `parent_context_fragment`, `tools_suite_fragment`, `user_message_fragment`.

New optional payload field:

| Field | Type | Meaning |
|---|---|---|
| `source_name` | `str?` | Present when `kind == "fragment_source_failed"`. Names the failed producer's kind (e.g., `"role_fragment"`). Absent (null) for every other kind value. |

**Cadence.** At most once per `(session_id, source_name)` pair per session. A repeated failure on the same source (e.g., a bundle whose slot ambiguity trips on every turn) fires the SessionWarning ONCE, not per turn — the trigger uses PerEvent policy but the source_name-keyed dedup lives on the reader's side. The grader invariant carries over from § F #7 (v0.1's per-kind cadence).

**Composer / model behavior after a fragment-source failure.** The per-turn composer chain (`per_turn_fragment → user_message_fragment → composer`) subscribes to `{substrate.ProducerCompleted, substrate.ProducerFailed}` from sprint 068 onward. A failed link still advances the chain; the composer's cohort simply lacks the failed fragment. `PromptComposed.text` emits truncated. Model runs. Session runs to completion. The SessionWarning is the operator-visible signal that the composed prompt was degraded.

## X. v0.12 — topology runs (2026-10-13, sprint K314)

Research: `process/planning/RESEARCH-2026-10-13-core-topologies-r8.md`; roadmap `process/planning/ROADMAP-2026-10-13-core-topologies.md`. Adds five event kinds, four producer kinds, three triggers, four enums, one message source and one end reason. The kinds name what a product user sees in plain words (a card, checks, a report); the SDD terms they carry are in § X.7.

### X.1 A run

A topology run is started by a session, its caller, through a topology's tool. It is one or more sessions, each with its own record, under one `run_id`. A session in a run is driven when its topology writes its next `UserMessage`, and interactive when a person does. The caller's record holds the run's start and end; each session's record holds its card, its checks and its report.

### X.2 Events in the caller's record

`TopologyRunStarted` — written when the topology's tool starts the run:

| Field | Type | Meaning |
|---|---|---|
| `run_id` | str | the run |
| `topology` | str | the topology's name |
| `call_seq` | int | the seq of the caller's `ToolCall` that started it |
| `sessions` | list of `RunSession` | each session in the run: `session_id`, `role` (`RunRole`), `record_root`, `driven` (bool) |

`TopologyRunEnded` — written when the run ends, before the caller's next model step, and told to the model once:

| Field | Type | Meaning |
|---|---|---|
| `run_id`, `topology` | str, str | as at the start |
| `outcome` | `RunOutcome` | how it ended |
| `report_seq` | int or null | the seq of the run's `ReportWritten`; null when the run ended without one |
| `report` | `ReportWritten` or null | a copy of that report, for the caller's model |

### X.3 Events in a run session's record

`CardAccepted` — the run's input, the first application event of a driven session:

| Field | Type | Meaning |
|---|---|---|
| `form` | `CardForm` | `plain` (what, where, how to tell it is done) or `sdd` (the kit's sprint card) |
| `what` | str | the work |
| `where` | list of str | the files or parts of the project it touches, and what to read first |
| `checks` | list of `CardCheck` | how to tell it is done: `kind` (`CheckKind`), `text`, and for a `command` its `expect_exit` (int, 0 unless the card names another; v0.12.1) |
| `text` | str | the card as given |
| `limits` | `RunLimits` | `max_stops`: turn ends before the run stops; `stall_stops`: turn ends in a row with no new commit and no change in the checks before it counts as stuck |

`ChecksRun` — the checks after a turn ends:

| Field | Type | Meaning |
|---|---|---|
| `after_seq` | int | the `Returned` they follow |
| `results` | list of `CheckResult` | per card check: `index`, `kind`, `passed` (bool, or null when not run), `exit` (int or null), `output_tail`, `note` |
| `record_problems` | list of str | what the check of the session's own events against this vocabulary found |
| `passed` | bool | every command check passed, every statement check holds (v0.12.4), and `record_problems` is empty |
| `head` | str or null | the worktree's commit at the check (v0.12.2); a stall is read from it |
| `judge` | `JudgeCall` or null | v0.12.4: the call that judged the statement checks — `model` (str), `prompt` (str), `reply` (str); null when the card has none |

A `statement` check is judged, not run (v0.12.4): after each turn one model call apart from the worker reads the card, the worktree's diff since the run's base and the worker's last reply, and answers each statement "holds" or "does not hold" with a reason. Its `passed` is that answer and its `note` the reason. A statement the reply leaves unanswered does not hold, and its note says so.

`ReportWritten` — the run's report, its last application event:

| Field | Type | Meaning |
|---|---|---|
| `outcome` | `RunOutcome` | how it ended |
| `asked` | str | what the card asked for, as the worker understood it |
| `done` | str | what was done |
| `files` | list of str | the files changed |
| `checks` | list of `CheckResult` | the last checks |
| `left` | str | what is left and why; empty when nothing is |
| `branch` | str or null | the branch the work is on |
| `commits` | list of str | its commits |

`RunPaused` and `RunResumed` (v0.12.3) — injected into a driven run's record by its caller (`by`: str, who asked). A run with more `RunPaused` than `RunResumed` takes no next turn; when it goes quiet it pauses (the kernel's `pause_await_input`) until a `RunResumed` resumes it. A pause asked for mid-turn takes effect when the turn's checks have run; a run whose checks end it still reports. A stop ends a run at once.

A `UserMessage` the `continue` producer writes carries `slash_source` `driven`. `SessionEnded.reason` gains `caller_stop`, for a run its caller stopped.

### X.4 Enums

- `RunOutcome`: `done`, `partly_done` (done, with something deferred), `needs_user` (stopped on a question only the user can answer), `stuck` (out of its limits without passing), `failed` (an error it could not continue past), `stopped` (its caller stopped it).
- `RunRole`: `worker`, `reviewer`.
- `CardForm`: `plain`, `sdd`.
- `CheckKind`: `command` (a command that must exit 0), `statement` (a thing that must be true, judged by a reviewer).

### X.5 Producers and triggers of a driven session

| Producer | Writes |
|---|---|
| `card` | `CardAccepted`, then the first `UserMessage`, composed from the card |
| `checks` | `ChecksRun` |
| `continue` | the next `UserMessage` (`slash_source` `driven`), carrying what failed |
| `report` | `ReportWritten` |

| Trigger | Fires on | Starts |
|---|---|---|
| `card-on-session-prompt` (v0.12.2) | the session prompt ending, on a fresh record, in a driven session that has one | `card` (without a session prompt, `card` starts with the run) |
| `checks-on-returned` | `Returned` in a driven session | `checks` |
| `continue-on-checks` | `ChecksRun` not passed, within the card's limits | `continue` |
| `report-on-checks` | `ChecksRun` passed, or the limits reached | `report` |
| `continue-on-resumed` (v0.12.3) | `RunResumed`, when the run awaits its next turn and has not ended | `continue`, with the last checks' failures |

A driven session finalises on `ReportWritten`, or on `SessionEnded`, and pauses when it goes quiet with a pause asked for (v0.12.3). An undriven session is v0.11 unchanged.

### X.6 Order

- In the caller's record, a run's `TopologyRunEnded` follows its `TopologyRunStarted`, and each appears once per `run_id`.
- In a driven session, `CardAccepted` precedes the first `UserMessage` (v0.12.2; a session prompt's fragments may come before it); every `ChecksRun` follows a `Returned`; `ReportWritten` appears once, and nothing but `SessionEnded` and the kernel's finalisation follows it.

### X.7 The report and the kit

The report carries the SDD kit's Signal Report (`sdd-kit-3/templates/SIGNAL_REPORT.md`) under plain names: `asked` is its `scope_confirmation`; `done` and `files` its `work_performed` and `artifact_payloads` by reference; `checks` its `dual_contract_self_grade`; `outcome` and `left` its `status_and_blockers` (`done` = complete, `partly_done` = complete-partial, `needs_user` = blocked-on-user, `stuck` and `failed` = failed). Its `signal_trace` is the session's record itself, read by `record_root`. The card's `command` checks are the kit's command exit codes; `statement` checks its content assertions and observations; `record_problems` the signal contract and the review of the run.

### X.8 Decisions and candidates not adopted

Agent-resolved on the grounds (project: the research r8 and its approval; SDD: `grammar/PRINCIPLES.md` commitments 1–3 and BOOTSTRAP Step 2's over-decomposition check; practice: the session topology's existing kinds), and recorded in the kernel board's Decisions:

- **No `CardRefused`.** A refused card is the tool call's `ToolResult` with `ok: false` naming what is missing; the record already holds it. A second event would say the same fact twice.
- **No `RunStopped`.** A stop is `SessionEnded` with reason `caller_stop` in the run's record, and `outcome` `stopped` in the caller's. Pause, resume and step are operations on the record and need no events of their own until K319 shows otherwise.
- **Two roles, not five.** Foundation 03 names five roles; the cards through K321 need a worker and a reviewer. The others (checker, integrator, planner) are added by proposal when a shape needs them; the checks of K317 are a deterministic producer, not a session.
- **Plain kind names.** The product shows these events; `CardAccepted` and `ReportWritten` say what happened in words a user reads, per r8 § 3.10.

## W. v0.11 — language measured live (2026-10-13, sprints K309–K311)

Research: `process/planning/RESEARCH-2026-10-13-language-metrics-r5.md`. Library: `substrate.language` 0.2.0. Adds two event kinds, one producer kind, two triggers; narrows `return-on-reply`.

### W.1 What is measured live, and when

With `session_topology(language=True)`, each turn that ends in a reply is measured before it returns: the user's message (stream `user`, or `delegate` for a message a parent model wrote), each of the turn's replies (stream `model`), and the turn's relation twice (stream `relation`, pairing `final`: the message with the final reply; `turn`: with all the turn's replies joined). Then the change detector runs on the session's series and records any change it finds.

The measurement sits in the turn's chain, between the final reply and `Returned`. The session pauses on `Returned`, and a pause cancels every producer still running (`Runtime.run` cancels the remaining tasks on exit), so a measurement running beside the turn would sometimes be cut off.

Measured later from the record, not live: a turn that ends in a model error or an interrupt (it has no final reply); composed prompts; trailing windows across messages and sessions. `substrate language <record>` and the app's process do these.

### W.2 Events

`LanguageProfile` — one text's measures, or one turn's relation:

| Field | Type | Meaning |
|---|---|---|
| `stream` | `LanguageStream` | `user`, `delegate`, `model` or `relation` |
| `turn_index` | int | the turn |
| `source_seq` | int | the seq of the measured `UserMessage` or `ModelReply`; for `relation`, of the final reply |
| `step` | int or null | the reply's step (`model` only) |
| `pairing` | `Pairing` or null | `final` or `turn` (`relation` only) |
| `library` | str | `substrate.language` version |
| `preprocessing` | str | `substrate-text-1` |
| `instrument_sha256` | str | SHA-256 of the canonical JSON of the parameters, window minimums, lexicon versions and compressor |
| `measures` | map of str to number or null | the profile's measures (`values.text` of a `substrate language` line for the same text), or the relation's |

`LanguageDrift` — a change found on the newest value of one series:

| Field | Type | Meaning |
|---|---|---|
| `stream` | `LanguageStream` | `user` or `model` |
| `measure` | str | one of `drift.WATCHED` |
| `direction` | `Direction` | `up` or `down` |
| `statistic` | number | the Page–Hinkley value, in warm-up standard deviations |
| `source_seq` | int | the seq of the text whose value raised it |
| `series_length` | int | values in the series, this one included |
| `delta`, `threshold`, `warmup` | number, number, int | the detector's parameters |

The series of a stream is its `LanguageProfile` measures in record order: user messages, and model replies whose stop reason is not `tool_use`. The detector starts again after a change, as in research round 5.

### W.3 The producer

`language` (deterministic): one run per measured turn. Its input is the turn's seq range (from the turn's `UserMessage` to its final `ModelReply`) and nothing else; it reads the turn's events, and the session's earlier `LanguageProfile` events, from its own record with `api.read_range`, as the model step reads its history (§ L). It emits the `LanguageProfile` events in the order of § W.1, then any `LanguageDrift`.

### W.4 Triggers

| Trigger | Fires on | Starts |
|---|---|---|
| `language-on-reply` (added) | a `ModelReply` whose stop reason is not `tool_use`, while the turn is open, with `language` on | `language` with the turn's seq range |
| `return-on-language` (added) | `language` ending (`ProducerCompleted` or `ProducerFailed`) while the turn is open | `return`, reason `replied` |
| `return-on-reply` (narrowed) | as before, with `language` off | `return` |

A failed measurement still returns the turn: the failure is on the record as `substrate.ProducerFailed`.

### W.5 The turn's record

With `language` on: … `ModelReply` (final), `LanguageProfile` (the message), `LanguageProfile` (each reply), `LanguageProfile` ×2 (relation), `LanguageDrift` ×0 or more, `Returned`.

### W.6 The switch

`session_topology(language=False)` is v0.10 unchanged. The app's sessions turn it on (`SessionRegistry`). The record names it: the topology registration in `substrate.RunStarted` lists the `language` producer and its triggers.

### Ratification signature

- **v0.2.1** — Sprint 068 close, 2026-09-02. Additive extension for fragment-source failure surfacing. § A-J byte-preserved from prior locks.

## K. v0.3 — one reply per model call, Returned, plain names (2026-10-09, sprint K259)

Why: a turn wrote the same text twice (`ModelReply`, then `FinalAnswer`), `model_usage` was always `{}`, `Park` named the kernel's pause rather than what happened, and the trigger names followed five patterns. Each fact about a turn is now on the record once, under a name that says what it is.

### K.1 ModelReply (v2)

One per model call, including a call that ends in a tool call.

| Field | Type | Meaning |
|---|---|---|
| `text` | `str` | What the model said. Empty when the call only requests a tool. |
| `stop_reason` | `str` | `"end_turn"` (the model answered), `"tool_use"` (a `ToolCall` follows), `"wrap_up"` (the step budget or repeated tool failures forced a plain answer). |
| `usage` | `dict[str, Any]` | `input_tokens: int`, `output_tokens: int`, `wall_ms: int`, `model: str`, `estimated: bool` (true when the responder reports no counts and the numbers are a chars/4 estimate). |
| `turn_index` | `int` | Matches the enclosing `UserMessage`. |
| `step` | `int` | 0-based model call within the turn. |

Stratum: **event**. `model_usage` (v0.1) is replaced by `usage`.

### K.2 Returned

Replaces `Park`. The turn is over and control is back with the user.

| Field | Type | Meaning |
|---|---|---|
| `turn_index` | `int` | The turn that ended. |
| `reason` | `str` | `"replied"` (a `ModelReply` with `stop_reason` other than `tool_use`), `"model_error"` (`substrate.ProducerFailed` on the `model` producer), `"interrupted"` (`substrate.ProducerCancelled` on the `model` or `tool` producer). |
| `detail` | `str` | The error text on `model_error`; empty otherwise. |

Stratum: **event**. Exactly one per turn.

### K.3 Retired on session records

- `Park` — replaced by `Returned`.
- `FinalAnswer` — a session record no longer carries it. tool_loop keeps `FinalAnswer` unchanged; benchmarks grade it.
- `UserMessage.assembled_prompt` — the exact prompt rides `PromptComposed.text` (§ I), once per model call.

Records written before v0.3 keep these kinds. Every reader of session records accepts both shapes: an old `Park` reads as `Returned` (`final_answer` → `replied`, `interrupt` → `interrupted`); an old `FinalAnswer` that repeats the `ModelReply` before it adds nothing; an old `ModelReply` followed by a `FinalAnswer` reads as `stop_reason: "end_turn"`.

### K.4 Producer names

| Producer | Emits | Replaces |
|---|---|---|
| `model` | `ModelReply`, `ToolCall`, `TranscriptCompacted`, `BackgroundTaskEnded` | — (no longer emits `FinalAnswer`) |
| `tool` | `ToolResult` | — |
| `return` | `Returned` | `park` |
| `session_end` | `SessionEnded` | — |
| `session_started` (instrument) | `SessionStarted` | — |
| `first_message` | `UserMessage` | `session_open` |
| `session_prompt` | `PromptFragment` (one per session-open source) | `role_fragment`, `bundle_methodology_fragment`, `bundle_personality_fragment`, `tools_suite_fragment`, `parent_context_fragment` |
| `prompt_composer` | `PromptComposed` | — (fires on `UserMessage`; `per_turn_fragment` and `user_message_fragment` retire) |
| `interrupt_fragment` | `PromptFragment` | — |
| `warning` | `SessionWarning` | `session_warning`, `fragment_error_warning` |

### K.5 Trigger names

Form: `<what it starts>-on-<event>`.

| Trigger | Subscription | Starts | Replaces |
|---|---|---|---|
| `tool-on-tool-call` | `ToolCall` | `tool` | `run-tool` |
| `model-on-tool-result` | `ToolResult` (step budget left) | `model` | `continue` |
| `model-wrap-up-on-tool-result` | `ToolResult` (budget spent) | `model` | `wrap-up` |
| `model-on-prompt-composed` | `PromptComposed` | `model` | `resume-on-composed` |
| `prompt_composer-on-user-message` | `UserMessage` | `prompt_composer` | `emit-per-turn-fragment`, `emit-user-message-fragment`, `compose-on-cohort-complete` |
| `prompt_composer-on-interrupt` | `ToolResult` with an interrupt fragment pending | `prompt_composer` | `compose-on-interrupt-tool-result` |
| `interrupt_fragment-on-interrupt-request` | `InterruptRequested` | `interrupt_fragment` | `emit-interrupt-fragment` |
| `return-on-reply` | `ModelReply` with `stop_reason` ≠ `tool_use` | `return` | `park-on-final` |
| `return-on-model-error` | `substrate.ProducerFailed` (model) | `return` | `park-on-model-error` |
| `return-on-interrupt` | `substrate.ProducerCancelled` (model or tool) | `return` | `park-on-interrupt` |
| `warning-on-fragment-error` | `substrate.ProducerFailed` (a prompt source) | `warning` | `warn-on-fragment-error` |
| `end-on-exit` | `UserMessage` text `/exit` | `session_end` | — |
| `end-on-turn-cap` | `UserMessage` past `max_turns` | `session_end` | `end-on-cap` |
| `end-on-end-request` | `SessionEndRequested` | `session_end` | `end-on-user-end` |

`SessionEnded.reason` value `"timeout"` becomes `"turn_cap"`; old records' `"timeout"` reads as `"turn_cap"`.

### K.6 Termination

`any_of(pause_await_input(on Returned, resume on UserMessage), finalise_on(SessionEnded))`. The `all_completed` refusal checks the policy's members, not its name string.

### K.7 Invariants (replace § F 4–5 for v0.3 records)

1. Every `UserMessage{turn_index=N}` is followed, before the next `UserMessage`, by exactly one `Returned{turn_index=N}`.
2. `Returned{reason:"replied"}` is preceded within its turn by a `ModelReply` whose `stop_reason` is `end_turn` or `wrap_up`; `model_error` by a `substrate.ProducerFailed` on `model`; `interrupted` by a `substrate.ProducerCancelled` on `model` or `tool`.
3. Every `ModelReply{stop_reason:"tool_use"}` is followed by a `ToolCall` in the same step.
4. Every model call writes exactly one `PromptComposed` before its `ModelReply`, and that `PromptComposed.text` is the driver's whole input (§ I, now enforced).
5. A session record written under v0.3 holds no `FinalAnswer`, no `Park`.

### Ratification signature

- **v0.3** — Sprint K259 close, 2026-10-09. Decisions by the Architect, 2026-10-09. §§ A–J byte-preserved.

## L. v0.3.1 — the model builds and records its own prompt (2026-10-09, sprint K261)

Why: the record must hold exactly what the model read, once per model call. A composer that ran before the model could not see each step's tool results, and the model added text after it; the record and the call disagreed. The prompt is now recorded where the call happens.

### L.1 PromptComposed

- Written by the `model` producer, once per model step, immediately before the call (and in a scripted CI run, where the script stands in for the model's choice).
- `text` is the driver's whole input. Order: the seed; the session fragments and `per_turn` by precedence (the tool list under "Tools you MAY use:" for a text-only driver); the kept turns, the current one last; any interrupt fragment; background-task notices; the step's directive.
- `fragment_seqs` names the fragments the text used. `strategy` is `"model_input"`.

### L.2 UserMessage.assembled_prompt

Set only when a `/context` slice is attached to the message; empty otherwise. `per_turn` is no longer prefixed into it. K.3's retirement of the field is withdrawn: the field carries the attached slice.

### L.3 Producers and triggers (replaces the matching rows of K.4 and K.5)

- Retired: producers `prompt_composer`, `per_turn_fragment`, `user_message_fragment`; triggers `emit-per-turn-fragment`, `emit-user-message-fragment`, `compose-on-cohort-complete`, `compose-on-interrupt-tool-result`, `resume-on-composed`.
- New: trigger `model-on-user-message` (`UserMessage` → `model`, step 0).
- `model-on-tool-result` and `model-wrap-up-on-tool-result` start the model on every `ToolResult`; a pending interrupt fragment reaches the model through the fragment cohort on that step.
- K.5's rows `prompt_composer-on-user-message`, `prompt_composer-on-interrupt` and `model-on-prompt-composed` do not exist.

### L.4 Invariant (replaces K.7 #4)

Every model step writes exactly one `PromptComposed` before its `ModelReply` or `ToolCall`, and that text is the driver's whole input for the step.

### Ratification signature

- **v0.3.1** — Sprint K261 close, 2026-10-09. §§ A–K byte-preserved.

## M. v0.3.2 — reply and return as built (2026-10-09, sprint K262)

Why: K262 implemented K.1, K.2, K.6 and the three `return-on-*` rows of K.5. Building them settled four points that K left open or stated wrongly.

### M.1 ModelReply.usage (corrects K.1)

The fields are the ones `ModelUsage` already carries on every other Substrate record: `model: str`, `prompt_tokens: int`, `completion_tokens: int`, `wall_ms: int`, `estimated: bool`. K.1's `input_tokens` and `output_tokens` were never written. With no provider counts, `estimated` is true and the counts are word counts of the prompt and the reply (`call_responder_metered`), not chars/4. A scripted CI step calls no model: `model` is `"script"`, every count is 0, `estimated` is true.

### M.2 ModelReply.text on a tool call

A native tool call's reply carries whatever prose the model wrote beside the call; a text-mode call's reply is empty, since the reply is the JSON call itself. Neither is rendered into the model's history: the `ToolCall` line stands for the call, as before v0.3, so the model's prompt wording is unchanged.

### M.3 One Returned per turn

Each `return-on-*` trigger fires only while the turn has no `Returned` yet (`returned_turns < user_turns`). A hard interrupt can cancel the model and a tool together, and a failure can race a reply; without the check either writes two `Returned` for one turn, breaking K.7 #1.

### M.4 What remains of Park

The `Park` struct stays so readers and fixtures can decode records written before v0.3. The `park` producer and the `park-on-final`, `park-on-model-error` and `park-on-interrupt` trigger ids no longer exist in code; an old record names them in its RunStarted topology, and readers match the event kind, not the trigger id.

### M.5 Slices filtered by kind

A `/context` or delegate slice whose `kinds` names `FinalAnswer` also takes a session record's replies: each `ModelReply` whose `stop_reason` is not `tool_use`.

### Ratification signature

- **v0.3.2** — Sprint K262 close, 2026-10-09. §§ A–L byte-preserved.

## N. v0.3.3 — one producer for the session prompt (2026-10-09, sprint K263)

Why: K.4 named a `session_prompt` producer for the five session-open sources and a `warning` producer for both warning kinds. Merging the sources into one producer merges their failure domains; the merged producer records a failed source itself, which leaves `warning` with no job.

### N.1 Producers (replaces the matching rows of K.4)

| Producer | Emits | Replaces |
|---|---|---|
| `session_prompt` | `SessionWarning` (`seed_alone_exceeds`, first, when the seed and `per_turn` pass the driver's headroom); one or more `PromptFragment` per source; `SessionWarning` (`fragment_source_failed`) for each source that raised | `role_fragment`, `bundle_methodology_fragment`, `bundle_personality_fragment`, `parent_context_fragment`, `tools_suite_fragment`, `session_warning`, `fragment_error_warning` |
| `first_message` | `UserMessage` | `session_open` |

K.4's `warning` row is not built. `session_prompt` is registered only when the session names a prompt source or its seed passes the headroom.

### N.2 Triggers (replaces the matching row of K.5)

- `warning-on-fragment-error` (`warn-on-fragment-error` in code) is retired: a failed source never raises out of `session_prompt`.
- `first-message-on-session-prompt` fires on `substrate.ProducerCompleted` or `substrate.ProducerFailed` of `session_prompt`, once, on a fresh record. It is the one session trigger that waits on a producer's end.

### N.3 SessionWarning (adds to § J)

| Field | Type | Meaning |
|---|---|---|
| `source_name` | `str?` | For `fragment_source_failed`: the `PromptSource` that raised (`role`, `bundle_methodology`, `bundle_personality`, `parent_context`, `tools_suite`). Records before v0.3.3 hold a producer kind here (`role_fragment`, …). |
| `detail` | `str?` | For `fragment_source_failed`: the error, as `repr(exc)`. Absent on every other kind and on records before v0.3.3. |

A failed source contributes no fragment; the sources after it still run.

### N.4 Parent-context slices

A session's `parent_context` source and delegate's per-call context call one extractor (`session/context_slice.py`), so § M.5 holds for both. Caps differ: 64 KiB for `parent_context`, 8 KiB for delegate.

### Ratification signature

- **v0.3.3** — Sprint K263 close, 2026-10-09. §§ A–M byte-preserved.

## O. v0.3.4 — trigger names as built (2026-10-09, sprint K264)

Why: K.5 set the form `<what it starts>-on-<event>`. Building it settled the spelling of two names K.5 got wrong or left out.

### O.1 Trigger ids (replace K.5's rows; K.5's `model-on-prompt-composed` was retired by § L, `warning-on-fragment-error` by § N)

| Trigger | Starts | Was |
|---|---|---|
| `tool-on-tool-call` | `tool` | `run-tool` |
| `model-on-user-message` | `model` | — (§ L) |
| `model-on-tool-result` | `model` | `continue` |
| `model-wrap-up-on-tool-result` | `model` | `wrap-up` |
| `return-on-reply`, `return-on-model-error`, `return-on-interrupt` | `return` | — (§ M) |
| `interrupt-fragment-on-interrupt-request` | `interrupt_fragment` | `emit-interrupt-fragment` |
| `first-message-on-session-prompt` | `first_message` | — (§ N) |
| `end-on-exit` | `session_end` | — |
| `end-on-turn-cap` | `session_end` | `end-on-cap` |
| `end-on-end-request` | `session_end` | `end-on-user-end` |
| `driver-stepper-on-returned` (CI wrapper) | `driver_stepper` | `advance-on-park` |

Every id is hyphen-case. K.5's `interrupt_fragment-on-interrupt-request` put the producer's underscore into a hyphenated name and is corrected. `driver-stepper-on-returned` fires on any turn end, `Returned` or an old record's `Park`. The `session_started` instrument's trigger is named by the kernel after its producer and is outside this rule. `tool_loop` keeps its own `run-tool`, `continue` and `wrap-up`.

### O.2 SessionEnded.reason

`turn_cap` replaces `timeout`. Readers map an old `timeout` to `turn_cap` (`LEGACY_SESSION_END_REASONS`).

### Ratification signature

- **v0.3.4** — Sprint K264 close, 2026-10-09. §§ A–N byte-preserved.

## P. v0.4 — default guidance (2026-10-10, sprint K270)

Why: `ROADMAP-2026-10-10-default-guidance.md` gives every driver this machine's working and writing standard, on top of Substrate's harness rules, through each driver's own channels. It needs a system channel, three new prompt sources, two injected events, and two renames. Research: `RESEARCH-2026-10-10-substrate-default-guidance-r7.md`.

### P.1 Renames

| Old | New | Legacy reading |
|---|---|---|
| `PromptSource.BUNDLE_PERSONALITY` = `bundle_personality` | `PromptSource.BUNDLE_STYLE` = `bundle_style` | Records before v0.4 keep `bundle_personality`; readers map it to `bundle_style` (`LEGACY_PROMPT_SOURCES`). |
| bundle slot `personality.md` / `personality/`, field `Bundle.personality` | `style.md` / `style/`, `Bundle.style` | The loader reads a `personality.md` when no `style.md` exists. |
| shipped bundle `session` | `harness` | `load_bundle("session")` resolves to `harness` (`LEGACY_BUNDLE_NAMES`); manifests and `SessionStarted.bundle` values of `session` load. |

### P.2 Prompt sources (adds to § I)

| Value | Scope | Precedence | Channel | Meaning |
|---|---|---|---|---|
| `bundle_style` | session-open | 3 | system | One fragment per link of the bundle's `extends` chain with a non-empty style, ancestor first. Replaces § I's caller-wins rule. |
| `baseline` | session-open | 4 | system | The environment computed at session open: workspace path; in a git repo root, branch, commit, README head (8 KiB), `git diff HEAD` (32 KiB); outside one, cwd and hostname; platform; driver and model ID; date; `<repo>/.substrate/context.md`. The same dict is `RunStarted.baseline` and `SessionStarted.baseline`. |
| `bundle_methodology` | session-open | 5 | user | One fragment per link, every link at 5; `seq` gives ancestor-first order. Replaces the code's 50 + position. |
| `memory` | session-open | 8 | user | One fragment per memory index (`~/.substrate/memory/MEMORY.md`, `<repo>/.substrate/memory/MEMORY.md`), each capped at 200 lines or 25 KB. Provenance: `{"path", "lines", "truncated"}`. |
| `per_turn` | session-open (moved from turn-scoped) | — | user | Written once at session open, and again after a `SessionChanged` of `per_turn` or `bundle`. Default: the bundle chain's `per_turn` slots joined ancestor first; a manifest value overrides. Placed directly after the current turn's `USER:` line on every step, not in the head. Provenance: `{"from": <bundle path> or "manifest"}`. |
| `skill` | session-open | 40 | user | A skill body loaded by `SkillRequested`. Kept for the rest of the session. Provenance: `{"name", "resolved_from", "model_class"}`. |

`SESSION_OPEN_SOURCES` gains `bundle_style`, `baseline`, `memory`, `skill` and `per_turn`. `TURN_SCOPED_SOURCES` keeps `user_message` and `interrupt`.

`SYSTEM_SOURCES = {bundle_style, baseline}`. Their fragments compose into `PromptComposed.system`; every other fragment composes into `.text`.

### P.3 PromptComposed.system (adds to § I and § L.1)

| Field | Type | Meaning |
|---|---|---|
| `system` | `str` | The text sent on the driver's system channel: an Ollama `{"role":"system"}` message, or the driver profile's flag for a CLI (`--system-prompt` for `claude`). Empty when the session has no system-channel fragment. Records before v0.4 have no field and read as `""`. |

The invariant of § L becomes: `system` and `text` together are the bytes the driver reads. A CLI with no system flag receives `system`, a blank line, then `text`, as one prompt.

With `driver_params.cache_layout = true` (`claude` only, default false), `role`, `bundle_methodology`, `memory` and `tools_suite` also compose into `system`. The record shows which layout a step used.

### P.4 Injected events

| Struct | Fields | Written by | Effect |
|---|---|---|---|
| `SessionChanged` | `field: str` (`driver` \| `bundle` \| `per_turn` \| `date`), `old: str`, `new: str` | the daemon, on a PATCH of that field or on `/model`; the model step, when the date differs from the baseline's | The next model step carries one line directly after the current message: `Environment update: <field> changed from <old> to <new>.` For `bundle` or `per_turn`, the session prompt writes that source again and `FragmentCohort` drops the earlier fragments of the same source. |
| `SkillRequested` | `name: str`, `source: str` | the daemon, on `/dellm` | Starts `skill_fragment`, which writes `PromptFragment(skill)`. |

Both reach a live run through `Runtime.inject_event`, as `InterruptRequested` does. A parked session receives them ahead of the next turn's `UserMessage`.

### P.5 Producers and triggers (adds to N.1 and O.1)

| Trigger | Starts | Emits |
|---|---|---|
| `skill-fragment-on-skill-request` | `skill_fragment` | `PromptFragment(skill)`, or `SessionWarning(kind=fragment_source_failed, source_name=skill)` when the name resolves nowhere |

`session_prompt` gains the `bundle_style` (per link), `baseline`, `memory` and `per_turn` sources.

### P.6 Tool

`skill(name)`: returns the resolved body of a named skill as `ToolResult.output`. Its description lists each available skill's name and one-line description. Resolution: `<repo>/.substrate/skills/<name>/`, `~/.substrate/skills/<name>/`, shipped `topologies/session/skills/<name>/`; the model class picks `<name>-small` when it exists.

### P.7 Shipped names

| Kind | Names |
|---|---|
| Bundles | `harness` (today's `session` text, unchanged), `standard` (`extends = ["harness"]`), `standard-small` (`extends = ["harness"]`), and the four application bundles with `extends = ["standard"]` |
| Roles | `default` (unchanged), `default-small` |
| Skills | `dellm`, `dellm-small` |
| Model classes | `harness_agent`, `large`, `small`, recorded as `SessionStarted.model_class` |

### P.8 SessionStarted.driver_command (added with U120, 2026-10-10)

| Field | Type | Meaning |
|---|---|---|
| `driver_command` | `tuple[str, ...]` | For a CLI driver, the argv it runs before the system text and prompt: the command, the profile's isolation flags, the version pin. Empty for any other driver and on records before v0.4. |

### P.9 SessionChanged as built (K274, 2026-10-10; amends P.4)

- **Writer.** The model step writes `SessionChanged`, not the daemon. A parked session resumes only on a `UserMessage`, so an injected event could not reach one. On a turn's first step the model step compares the session's current driver, bundle, `per_turn` and date with the `session_settings` view, which folds `SessionStarted`, the newest `per_turn` fragment and earlier changes. It writes one event per difference. A field never recorded is not compared. `SessionStarted.bundle` is compared as written, so a manifest that still says `session` against a topology built with `harness` would count as a change.
- **Line.** `Environment update: <field> changed from <old> to <new>.` goes right after the current message on that step. For `per_turn` the line is `Environment update: the reminder line beside each message changed.`, since the new text itself follows on the next step. `SessionChanged` is a turn event, so later steps render the line in history where it happened.
- **Rewrite.** `session-prompt-on-session-changed` starts `session_prompt` with `only` set to the changed field's sources: `bundle` rewrites `bundle_style`, `bundle_methodology` and `per_turn`; `per_turn` rewrites `per_turn`. Each new fragment's provenance carries `generation`, the change's seq. `FragmentCohort` keeps only each source's newest generation; fragments written at session open are generation −1.
- **Placement.** The `per_turn` fragment's text sits on the line after the current turn's `USER:` line, on every step, with no precedence slot in the head. A bundle's change also changes the `per_turn` it supplies, and both changes are recorded.

### P.10 Skill requests as built (K277, 2026-10-10; replaces SkillRequested in P.4 and its trigger in P.5)

`SkillRequested` is not built. A parked session resumes only on a `UserMessage`, so the daemon could not write a separate event ahead of the turn. The request rides the turn's own `UserMessage`, in the field made for slash commands: `slash_source = "skill:<name>"` (`SKILL_SLASH_PREFIX`). Then:

1. `skill-fragment-on-user-message` starts `skill_fragment` on such a message. It writes `PromptFragment(source=skill, precedence=40)`, with provenance `{name, resolved_from, model_class}`, or a `SessionWarning(fragment_source_failed, source_name=skill)` when no layer has the skill.
2. `model-on-user-message` skips such a message. `model-on-skill-fragment` starts the model when `skill_fragment` completes or fails, so the turn's first step reads the skill. This is the ordering `first-message-on-session-prompt` uses.
3. `skill` is session-open, so the fragment stays for the rest of the session.

The `skill` tool (P.6) lives in `topologies/session/skills.py` as a `Tool` with its own schema; the daemon adds it to a session's suite.

### P.11 Driver slash commands (UI sprint 123, 2026-10-10)

The operator's `//<command>` reaches the driver as `/<command>`.

1. **The message.** It rides the turn's `UserMessage` with `slash_source = "driver"` (`DRIVER_SLASH_SOURCE`). The daemon accepts one only for a driver whose profile sets `slash_commands`; any other driver gets a 400, "This driver has no slash commands."
2. **The model step.** It sends the text as written, with no head, history or system text. It records that text as `PromptComposed` (`system` empty, no fragments) and the driver's answer as `ModelReply(end_turn)`, and the turn returns as usual.
3. **History.** `compose_model_prompt` leaves a driver turn out, and the history window prices it at zero, so later steps never see the command or its output.

No new kind is needed: the card's `DriverCommand` and `DriverCommandResult` are not built.

## Q. v0.5 — a harness driver's tool calls (2026-10-10, sprint K282)

A harness driver (claude, codex, cursor-agent) runs its own agent loop inside one model step. Every tool call it makes during that step is recorded, whichever tool set it used. Roadmap: `process/planning/ROADMAP-2026-10-10-harness-tool-calls.md`.

### Q.1 Kinds

| Kind | Fields | Written by |
|---|---|---|
| `HarnessToolCall` | `call_id: str`, `tool: str`, `args: dict`, `via: str`, `step: int`, `turn_index: int` | the model step, as the call starts |
| `HarnessToolResult` | `call_id: str`, `ok: bool`, `output: str` | the model step, as the call ends |

`call_id` pairs a result with its call. It is the harness's own id for `via = harness`, and Substrate's for `via = mcp`.

### Q.2 Routes (`via`)

- **`harness`.** The driver's own tool (Claude Code's `Bash`, Codex's `command_execution`, cursor-agent's `shellToolCall`), read from the driver's event stream. Substrate did not run it and records what the stream reports.
- **`mcp`.** One of the session's own tools, which the driver called through Substrate's MCP server. Substrate ran it.

### Q.3 Neither starts a producer

`ToolCall` starts the session's tool producer and, through its `ToolResult`, the next model step. A harness call happens inside a model step that is still running, so `HarnessToolCall` and `HarnessToolResult` subscribe nothing. The step that wrote them ends with its `ModelReply` as before.

### Q.4 History

Both are turn events. History renders them in record order, between the turn's `USER:` line and its reply:

- `HARNESS TOOL <tool> (<via>): args=<args>`
- `HARNESS RESULT: <output>`, or `HARNESS RESULT(fail): <output>`

### Q.5 The `mcp` tool mode

A model step runs in one of four tool modes: `none`, `native` (Ollama's tool calls), `text` (the tool list and JSON directive in the prompt), and from v0.5 `mcp`. In `mcp` the driver receives the session's tools as registered MCP tools, and the prompt carries no text tool list and no JSON directive.

### Ratification signature

- **v0.4** — Sprint K270, 2026-10-10. §§ A–O byte-preserved.

### Q.6 Substrate's tools stay Substrate's (K286, 2026-10-10; amends Q.1, Q.2, Q.3)

Q.1 and Q.2 recorded a harness driver's call to one of Substrate's tools over MCP as `HarnessToolCall` with `via = mcp`, and the model step ran the tool. That conflated the two tool sets and bypassed the tool producer. As built from K286:

- **`HarnessToolCall` / `HarnessToolResult` are the harness's own tools only**, read from its stream. `HarnessToolCall` loses `via`; `ToolRoute` is gone.
- **An MCP call is Substrate's own `ToolCall`.** `ToolCall` and `ToolResult` gain `origin`: `reply` (the default, so earlier records read) or `mcp`. The model step writes `ToolCall(origin = mcp)` and does not run it. `tool-on-tool-call` starts the tool producer as for any call, so its argument checks and its repeated-write guard apply. The producer writes `ToolResult(origin = mcp)`, and the session hands that result to the waiting MCP request.
- **An MCP call's result starts no model step.** `model-on-tool-result` and `model-wrap-up-on-tool-result` skip `origin = mcp`. The harness that asked is still running in the current step and reads the result over MCP. A new step would start a second CLI process on the same turn.
- **History** renders an MCP call as any `ToolCall`, with `TOOL <tool>: args=…` and `RESULT: …`. A harness's own tool renders as `HARNESS TOOL <tool>: args=…`.

## R. v0.6 — guidance levels (2026-10-10, sprints K287, K288)

Roadmap: `process/planning/ROADMAP-2026-10-10-guidance-levels.md`.

### R.1 Levels

`GuidanceLevel` (`topologies/session/model_class.py`) has four values. Each is carried by one bundle:

| Level | Bundle | Head, measured 2026-10-10 |
|---|---|---|
| `harness` | `harness` | 291 tokens: Substrate's loop rules only |
| `low` | `standard-low` (was `standard-small`; the old name resolves through `LEGACY_BUNDLE_NAMES`) | 562 tokens |
| `medium` | `standard-medium` | 1,218 tokens |
| `high` | `standard` | 2,995 tokens |

Every level's text is generic: no model, vendor or person named, no operator's memory index, and the user referred to in the third person (K287).

### R.2 Classes and default levels (amends § P.7)

`classify` has four classes. `harness_agent` (a CLI) and `large` (an Ollama model of 70B parameters or more, or of unreported size) default to `high`. `medium` (14B to under 70B) defaults to `medium`. `small` (under 14B; was under 30B) defaults to `low`. `guidance_level(model_class)` gives the default, and `guidance_bundle(level)` the bundle. A level the operator chooses always wins. `class_variant` now picks only the role prompt and skill variants (`default-small`, `dellm-small`, for `small`).

## S. v0.7 — compaction clears tool output first (2026-10-11, sprint K291)

Roadmap: `process/planning/ROADMAP-2026-10-11-compaction.md`. The record never changes: compaction decides only how the record renders into the prompt, and every decision is computed from recorded events, so replay rebuilds the same prompt.

### S.1 Order of cuts

When the history's estimate passes the budget (`driver_context_tokens × 0.6 − head`, as before):
1. **Tool outputs clear first.** The bodies of `ToolResult` and `HarnessToolResult` events clear oldest first, the current turn's included. The newest 3 tool results always render whole. Call lines (`TOOL …`, `HARNESS TOOL …`), user messages and model replies never clear.
2. **Whole turns drop only after that.** When the history still passes the budget with every clearable output cleared, the oldest whole turns drop as in § D. The current turn never drops.

### S.2 Clearing holds still

A clearing pass moves the boundary far enough that the history fits within half the budget, then holds it until the history passes the budget again. The prompt's start therefore stays the same across steps, and prefix caches keep working. The boundary is read back from the record's latest `TranscriptCompacted`, so it only moves forward.

### S.3 The placeholder

A cleared body renders as one line in place of its output:

- `RESULT [cleared: <tool>, seq <n>, <chars> chars]`
- `HARNESS RESULT [cleared: <tool>, seq <n>, <chars> chars]`

`<tool>` is the call's tool, `<n>` the result's seq, `<chars>` the output's length. The record keeps the output whole.

### S.4 TranscriptCompacted (amends § D)

| Field | Type | Meaning |
|---|---|---|
| `strategy` | `str` | `"tool_output_cleared"` when only tool outputs cleared; `"rolling_window"` when whole turns also dropped. |
| `cleared_through_seq` | `int \| None` | Every `ToolResult` and `HarnessToolResult` at or below this seq, outside the newest 3, renders as a placeholder. `None`: nothing cleared (all records before v0.7). |
| `dropped_seq_range` | `tuple[int, int] \| None` | As § D, now `None` when no turn dropped. |
| `kept_seq_start` | `int` | First seq of the oldest kept turn. |
| `reason` | `str` | `"driver_window_exceeded"`. |
| `tokens_before`, `tokens_after` | `int` | Estimated tokens of the history before and after the cut, after the scale in S.5. |
| `token_scale` | `float` | The factor the estimate was multiplied by (S.5); 1.0 in records before v0.7. |

**Cadence (replaces § D's).** At most one per model step, and only when `(cleared_through_seq, dropped_seq_range)` differs from the latest `TranscriptCompacted` in the record. A step that keeps the previous cut records nothing.

### S.5 The estimate's scale

The characters ÷ 4 estimate is multiplied by the driver's measured ratio: the latest `ModelReply` whose `usage.estimated` is false, divided by the `total_tokens` of the `PromptComposed` before it, clamped to 1.0–4.0. With no such reply the scale is 1.0. Harness drivers use 1.0: their reported counts include the harness's own prompt and tool loop, so the ratio does not measure the estimate.

### S.6 Invariants (add to § F)

9. Whole turns drop only when every tool output outside the newest 3 is already cleared.
10. `cleared_through_seq` never decreases within a record.
11. No two `TranscriptCompacted` events in a record carry the same `(cleared_through_seq, dropped_seq_range)` in a row.

### S.7 Only the current turn keeps outputs whole (K292, 2026-10-11; amends S.1)

S.1 kept the newest 3 tool results of the whole history whole. Replanning the codex session `s_b8dab6b0cfd443cdba9bc8b3` showed the flaw: its last turn's three file reads cost about 57,000 estimated tokens, the whole budget, so every earlier turn dropped. As built from K292: the newest 3 tool results **of the current turn** render whole. A finished turn ended with the model's reply, and all its outputs may clear. Invariant 9 reads the same with that set.

### S.8 Under pressure the current turn keeps only its latest result (K293, 2026-10-11; amends S.1 and S.7)

A live run on `kimi-k2.7-code:cloud` showed the gap: mid-turn, the current turn's protected results alone passed the budget, so nothing could clear and the earlier turn dropped, the user's request with it. As built from K293: when the history still passes the budget with every other output cleared, the current turn's protected set shrinks one result at a time, oldest first, down to its latest result. Whole turns drop only after that. The latest result never clears: the model's next step reads it.

### S.9 The driver's context window (K294, 2026-10-11)

Every CLI driver used to get 100,000 tokens whatever its model. The window now resolves in order (`topologies/session/context_windows.py`):

1. **Live.** A harness that reports its window on a call (Claude Code's `modelUsage.<model>.contextWindow`) has it recorded on `ModelReply.usage.context_window`; `TurnHistory` keeps the latest, and later steps budget on it.
2. **The CLI's own settings.** Codex's `model_context_window` in `$CODEX_HOME/config.toml` (default `~/.codex`).
3. **Documented.** The input limit its maker documents for the model the session names with `--model` or `-m` (or Codex's configured `model`), from a table in which every entry names its source page. Where a page states a maximum input below the context window, the input limit is used.
4. **Substrate's config.** `[driver.<name>].context_tokens` in `~/.substrate/config.toml`.
5. **Default.** 100,000.

Ollama adapters keep their probed window (`/api/show`); `deterministic` keeps 4,096.

| Field | Type | Meaning |
|---|---|---|
| `SessionStarted.driver_context_source` | `str` | Where `driver_context_tokens` came from: `probed`, `fixed`, `cli_settings`, `documented`, `config` or `default`. Empty before v0.7. |
| `ModelReply.usage.context_window` | `int`, optional | The window the harness reported on this call. Absent when it reported none. |

## T. v0.8 — Length and Tone (2026-10-11, sprint K296)

Research: `process/planning/RESEARCH-2026-10-10-guidance-controls-r4.md` §7 (size and tone), §9 (moments), §10 (composition). No measure is built; the controls are checked by reading replies.

### T.1 Controls and positions

| Control | Positions | Default |
|---|---|---|
| `length` | `terse`, `normal`, `full` | `normal` |
| `tone` | `blunt`, `neutral`, `formal`, `dry` | `neutral` |

`Control`, `LengthPosition` and `TonePosition` in `topologies/session/vocabulary.py`. Any other position is refused when the session is created or changed. Warm is not a position: in research round 4 §5, warmth tuning raised agreement with wrong beliefs.

### T.2 The texts

A position other than the default writes one `PromptFragment(source="control")`, with `provenance = {control, position}`, on the system channel after the bundle's style (`control` joins `SESSION_OPEN_SOURCES` and `SYSTEM_SOURCES`). The defaults write nothing, so a session at `normal` and `neutral` reads as before v0.8. The texts are the same on every driver (`LENGTH_TEXTS`, `TONE_TEXTS`):

| Position | Text |
|---|---|
| `terse` | Keep replies short: the answer and the facts it rests on. Leave out background, restatement and offers of more. |
| `full` | Give complete replies: the reasoning, the alternatives you weighed, and what you left out. Complete is not padded; every sentence still carries a fact. |
| `blunt` | Be blunt: state judgements plainly and name problems directly. Do not soften criticism, and hedge only where the evidence is uncertain. |
| `formal` | Write in a formal register for readers who were not in this conversation: full sentences, no slang, each term defined on first use. |
| `dry` | Keep the tone dry: understated and factual, without enthusiasm or exclamation. |

Where a text meets the guidance level's own rules, the level's rules win: a position narrows within them (research r4 §10, design 1).

### T.3 Recorded and changed

| Field | Type | Meaning |
|---|---|---|
| `SessionStarted.length`, `SessionStarted.tone` | `str` | The positions the session opened with. Empty before v0.8. |
| `SessionChanged.field` | adds `length`, `tone` | A position differs from the record at a turn's first step (§ P.4). |

A change writes the `control` source again with the change's seq as its generation (§ P.4). A rewrite that leaves a source with no text writes one empty fragment of that source, `provenance = {cleared: true}`, so the cohort's newest generation is empty and the old text stops; this holds for every rewritten source, `per_turn` included.

## Y. v0.13 — Handoff (2026-10-13, sprint K324)

Research: `process/planning/RESEARCH-2026-10-13-core-topologies-r8.md` § 5. A setting beside length and tone, written into the session prompt and changeable mid-session the way they are; its effect is read from the record.

### Y.1 The control and its positions

| Control | Positions | Default |
|---|---|---|
| `handoff` | `rare`, `normal`, `eager` | `normal` |

`Control.HANDOFF` and `HandoffPosition` in `topologies/session/vocabulary.py`; `HANDOFF_TOOLS` (`delegate`, `review`, `build`) names the tools it is about. Everything in § T holds for it: an unknown position is refused at create and change; the default writes no text; any other position writes one `control` fragment (`provenance = {control: "handoff", position}`); `SessionStarted.handoff` records the opening position (empty before v0.13); `SessionChanged.field` adds `handoff`; a change writes the `control` source again. A delegate child opens with its caller's position.

### Y.2 The texts (`HANDOFF_TEXTS`)

| Position | Text |
|---|---|
| `rare` | Do the work yourself. Use delegate, review or build only when the user asks you to. |
| `eager` | Hand work off. For any change you can check with a command, call build with a card (what to do, where, the command) instead of editing files yourself; ask review to check a finished change; give a self-contained subtask to delegate. Edit files yourself only for a one-line fix. |

The tools' own descriptions are unchanged at every position; the text says how readily to use them.

### Y.3 The measure

`handoff_calls(events)`: per turn of a session record, the number of `ToolCall`s whose tool is in `HANDOFF_TOOLS`, with the turn's `handoff` position (the opening position, then each `SessionChanged {field: "handoff"}`). `substrate handoff <record>` prints one line per turn. Read across sessions, it gives calls per turn by position and by model.

## U. v0.9 — guidance changed mid-session (2026-10-12, sprint K298)

Research: `process/planning/RESEARCH-2026-10-12-controls-mid-session-r2.md`.

### U.1 Guidance is a third control

A guidance level changes mid-session as its bundle does: the session's bundle becomes `guidance_bundle(level)` (§ R.1), recorded as `SessionChanged {field: "bundle"}`, and the bundle's sources are written again (§ P.4). `auto` is the model's default level, `guidance_level(classify(driver))` (§ R.2), resolved when the change is made, as at open. No new field: the level is the bundle.

### U.2 The line in the history

A `SessionChanged` is drawn in the history at its place (§ P.4), so the model reads a change beside the turns it governs as well as in the system text. A change between two level bundles names the levels:

| Change | Line |
|---|---|
| `bundle`, both level bundles | `Environment update: guidance changed from high to low.` |
| `bundle`, any other | `Environment update: bundle changed from <old> to <new>.` (unchanged) |
| `length`, `tone` | `Environment update: tone changed from neutral to blunt.` (unchanged) |

A bundle name that `LEGACY_BUNDLE_NAMES` resolves to a level bundle names that level.

## V. v0.10 — a change reaches the prompt for its message (2026-10-12, sprint K299)

Postmortem: `process/planning/POSTMORTEM-2026-10-12-mid-session-changes-arrive-late-r2.md`. Roadmap: `process/planning/ROADMAP-2026-10-12-changes-on-time-r2.md`. Amends § P.4 and § T.3.

### V.1 Which prompt carries a change

The prompt for the message on which a `SessionChanged` is recorded carries the new text. Before v0.10 the model step recorded the change and built that prompt from the old text; the new text reached the next message (§ P.4 named no prompt).

### V.2 Who records a change

`session_prompt` records `SessionChanged`, not `model`. A message that arrives while any setting in `SESSION_CHANGE_FIELDS` (driver, bundle, per_turn, date, length, tone) differs from the `session_settings` view starts `session_prompt` with the changes; that one run records each change in that order, then writes the sources the changes rewrite (`_REWRITTEN_ON_CHANGE`: bundle → bundle_style, bundle_methodology, per_turn; per_turn → per_turn; length and tone → control), each fragment's generation the message's seq. A driver or date change writes no text. `session_prompt` is registered in every session; with no source, its first run writes nothing.

### V.3 Triggers

| Trigger | Fires on | Starts |
|---|---|---|
| `session-prompt-on-user-message-change` (added) | a UserMessage while a setting differs | `session_prompt` with the changes |
| `model-on-session-prompt-change` (added) | `session_prompt` ending while the turn is open, the message naming no skill | `model` |
| `skill-fragment-on-session-prompt-change` (added) | the same, the message naming a skill | `skill_fragment` |
| `session-prompt-on-session-changed` (removed) | | |

`model-on-user-message` and `skill-fragment-on-user-message` fire only when no setting differs.

### V.4 The turn's record

On the message on which a change is made: UserMessage, SessionChanged (one per field), the rewritten PromptFragments, PromptComposed, the reply. The history draws each change's line beside the message (§ P.4).

### Ratification signature

- **v0.7** — Sprint K291, 2026-10-11, by the Architect's direction of the same day. §§ A–R byte-preserved.
- **v0.8** — Sprint K296, 2026-10-11, by the Architect's direction of the same day (Length and Tone rows, substrate-ui OPEN-ITEMS 16). §§ A–S byte-preserved.
- **v0.9** — Sprint K298, 2026-10-12, decided by the Architect ("let's make it happen", after research round 2), recorded by the Agent. §§ A–T byte-preserved.
- **v0.10** — Sprint K299, 2026-10-12, decided by the Architect ("let's go", after roadmap round 2), recorded by the Agent. §§ A–U byte-preserved.
- **v0.11** — Sprints K309–K311, 2026-10-13, decided by the Architect ("go… make sure we have the right design"), recorded by the Agent. §§ A–V byte-preserved.
