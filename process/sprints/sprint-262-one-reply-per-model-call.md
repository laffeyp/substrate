# Sprint 262 — One reply event per model call; Returned ends the turn

```yaml
---
id: 262
status: closed
opened_at: 2026-10-09
closed_at: 2026-10-09
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md
---
```

## why

A plain turn writes the same text as `ModelReply` and `FinalAnswer`, and `model_usage` is always `{}` (research F1, lens F094, F099). `Park` names the kernel's pause (F3). A hard interrupt during a tool call never ends the turn (lens F093). The termination guard refuses `all_completed` by a regex over the policy name (lens F097).

## scope

The model producer writes one `ModelReply` per model call:
- `stop_reason` is `tool_use` (followed by the `ToolCall`), `end_turn` or `wrap_up`;
- `usage` is filled from `call_responder_metered`.

The session writes no `FinalAnswer`. The `park` producer becomes `return`, writing `Returned`, with triggers:
- `return-on-reply` (a `ModelReply` whose `stop_reason` is not `tool_use`);
- `return-on-model-error`;
- `return-on-interrupt` (a cancelled `model` or `tool` producer).

Termination pauses on `Returned`, and the `all_completed` guard checks the composed policy's members, not its name string (F097).

## prerequisites

- K260, U119 and K261 closed.

## context_files

- `sdd-kit-2/AGENTS.md`
- `substrate/process/planning/RESEARCH-2026-10-09-session-topology-structure-round4.md`
- `substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md`
- `substrate/process/signals/session-vocabulary.md`
- `substrate/process/BLACKBOARD.md`
- `substrate/src/substrate/topologies/session/__init__.py`
- `substrate/src/substrate/topologies/session/vocabulary.py`
- `substrate/src/substrate/adapters/models.py` (`ModelUsage`, `call_responder_metered`)

## signal contract

### Emits

- `ModelReply` (v2 fields)
- `Returned`

### Invariants

- No `FinalAnswer` on a session record.
- tool_loop is unchanged.
- K260's readers pass on new records.

## artifact contract

### Files created

- `substrate/tests/test_reply_and_return_262.py`

### Files modified

- `substrate/src/substrate/topologies/session/__init__.py`
- `substrate/src/substrate/topologies/session/vocabulary.py`
- `substrate/src/substrate/topologies/session/records/ci_mode.record/` (regenerated)

### Content assertions

- The session's `producer_kind("model")` schemas omit `FinalAnswer`.
- `PARK` is used only in the legacy table.

### Command exit codes

- `uv run python -m pytest tests/test_reply_and_return_262.py` returns 0, and non-zero before the change.
- `uv run python -m pytest` (kernel fast suite), `ruff check`, `ruff format --check`, `mypy --strict src`, `lint-imports` return 0.
- `uv run --project ../substrate python -m pytest tests/` in substrate-ui returns 0.
- `npm run gates:electron` against the installed app returns 0.

## found before coding (2026-10-09)

- **`/context` and delegate slices filter by kind.** Callers pull a parent's answers with `kinds: ["FinalAnswer"]` (`test_server_session_turn_context.py:68`, `test_delegate_schema_six_fields.py:127`). On a v0.3 record the slice reader treats a `FinalAnswer` filter as the turn's replies (a `ModelReply` whose `stop_reason` is not `tool_use`), as the transcript already does.
- **`usage` fields.** `ModelUsage` already names them `model`, `prompt_tokens`, `completion_tokens`, `wall_ms`, `estimated`; `usage` uses those names (vocabulary K.1 said `input_tokens`/`output_tokens`; corrected in an addendum).
- **Native tool calls are unmetered.** `OllamaResponder.achat_tools` discards Ollama's counts; it gains a metered twin, as `arespond` has `arespond_metered`.
- **Scripted (CI) steps** call no model; their `ModelReply` carries `usage` with zero counts and `estimated: true`.

## predicted breaks (written before the run)

Tests that assert the session's old kinds or names, each to be updated to the v0.3 shape (the check stays the same):
- `test_session_topology_e2e.py` (FinalAnswer and Park counts, kind order), `test_session_topology_end_to_end.py` (FinalAnswer text, Park reason), `test_session_topology_failure_modes.py` (Park reasons, FinalAnswer counts), `test_background_notice_104.py` (index of FinalAnswer), `test_delegate_via_standing_session.py` (reviewer FinalAnswers), `test_session_vocabulary_constants.py` (ParkReason, park trigger and producer names), `test_session_shapes_both_read_260.py` (if it builds new-shape events with `model_usage`).
- UI: `test_server_session_sse.py` and `test_server_session_turn.py` (FinalAnswer, Park), `test_server_session_interrupt.py` (Park).
- CI records `session` and `daily` move (schemas and events change).
- Real-model tests that read FinalAnswer from a session record (`test_realmodel_tool_*`, `test_realmodel_delegate_standing.py`): they read through helpers or directly; any direct read is updated.
- Not expected to break: tool_loop and its tests, `test_kind_constants_match_structs_107.py` (tool_loop's `FinalAnswer` is unchanged), `test_cli_repl_219.py` (asserts FinalAnswer is not printed).

## prediction for the full kernel run (written before it, after the targeted runs)

Targeted runs so far: 16 of the 22 files naming the old kinds failed. 14 were on the list above; `test_session_topology_bundled.py` (2) was not. One of the two asserts `Park` directly, which the list missed. The other compares against the session CI record, whose move was predicted without naming this test. All 16 pass after the update and the record regeneration.

Full run prediction: everything passes except the real-model demo tests already set aside (coding_flow, code_review, recursion, pair_coding, bash escape) and the known flaky `test_realmodel_background_bash_103`. The six real-model session tests that read `FinalAnswer` now read `turn_replies`; they pass if the model answers as before.

## observation contract

### Driving steps

- A plain turn and a two-tool turn on the deterministic driver.
- A turn on Ollama.
- A `bash sleep 30` interrupted with the hard tier.

### Expected

- Plain turn: `UserMessage, PromptComposed, ModelReply(end_turn), Returned(replied)`, plus kernel framing.
- Tool turn: `ModelReply(tool_use)` before each `ToolCall`.
- Ollama: `usage.input_tokens > 0`.
- Interrupted turn: `Returned(interrupted)`, and the app shows the session parked.

## done criteria

Each model call is one `ModelReply` with its stop reason and token counts, and `Returned` ends every turn, interrupted tools included.

## result

- **Session.** The model step writes one `ModelReply(text, stop_reason, usage, turn_index, step)` per call: `tool_use` before each `ToolCall`, `end_turn` or `wrap_up` for the answer. No `FinalAnswer`. Native calls go through `OllamaResponder.achat_tools_metered`; text and plain calls through `call_responder_metered`; a scripted CI step records zero counts with `estimated: true`. The `return` producer writes `Returned`; `return-on-reply`, `return-on-model-error` and `return-on-interrupt` (a cancelled `model` or `tool`, F093) start it, each only while the turn has no `Returned` yet. Termination pauses on `Returned`. The `all_completed` guard walks `TerminationPolicy.leaves()` (F097).
- **Prompt wording unchanged.** A `tool_use` reply is not rendered into the history; the `ToolCall` line stands for it, as before.
- **Readers.** The `/context` and delegate slice treats a `FinalAnswer` filter as the turn's replies. `Park` is kept as a struct for old records; the `park` producer constant and the three `park-on-*` trigger constants are gone. Vocabulary addendum M (usage fields are `ModelUsage`'s: `prompt_tokens`, `completion_tokens`; K.1's names were never written).
- **Checks.** `test_reply_and_return_262.py` (5): a plain turn, a two-tool text-mode turn, a model failure, a hard interrupt of `bash sleep 30` ending the turn, the structural guard. `test_realmodel_reply_usage_262.py` on `qwen2.5:7b-instruct`: a `tool_use` reply (263 prompt tokens, 27 completion, 319 ms) and an `end_turn` reply (308, 16, 235 ms), both `estimated: false`. Kernel suite: 1,344 passed, 5 skipped, 2 failed (the known flaky `test_realmodel_background_bash_103`, and `test_api_docs_cover_the_surface`, below). UI suite 215 passed. All nine Electron gate scripts pass against the installed `/Applications/Substrate.app`, rebuilt with the K262 kernel.
- **Prediction misses.**
  - `test_session_topology_bundled.py` (2): one asserts `Park`; the other compares against the session CI record, whose move was predicted without naming the test.
  - `docs/api.md` was stale beyond K262: it lacked K267's input wording and K268's `read_range` and `current_record_root`, though K268's result says it was regenerated. Regenerated; the docs test passes.
  - UI harness: `both_session_shapes`' fixture built the old `ModelReply` with the session's struct; `transcript_follow`, `cli_version_picker` and `vm_smoke` waited on `Park`. All now accept `Returned`.
  - `test_server_session_interrupt.py` was predicted to break and did not: it runs its own topology that writes `Park`.
- **Found while gating.** `transcript_follow` read `SCROLL_APP`, `lifecycle_gates` read `LIFECYCLE_APP`, and `gates:electron` ran `resume_ended_session` with `SMOKE_TARGET=source`. Those three gates ran Electron from source in every earlier "all gates against the installed app" run this round; four of seven had run against the app. Each now also reads `SHAKEOUT_APP`, and `gates:electron` no longer forces source. The app build used for those runs had also skipped `pack:runtime`; the bundled kernel then held K268, so earlier runs tested their own sprint's kernel, but this round's first rebuild did not carry K262 until `pack:runtime` ran.
