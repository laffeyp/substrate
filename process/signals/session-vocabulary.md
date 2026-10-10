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
