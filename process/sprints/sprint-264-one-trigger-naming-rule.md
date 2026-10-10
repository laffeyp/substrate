# Sprint 264 — One trigger naming rule

```yaml
---
id: 264
status: closed
opened_at: 2026-10-09
closed_at: 2026-10-09
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md
---
```

## why

The triggers follow five naming patterns. `resume-on-composed` resumes nothing, and `end-on-cap` reports `timeout` for a turn count (research F8). Kind and producer literals sit beside their constants (lens F096, F103, F104).

## scope

- Every remaining trigger is named `<what it starts>-on-<event>`, per K259: `tool-on-tool-call`, `model-on-tool-result`, `model-wrap-up-on-tool-result`, `model-on-prompt-composed`, `end-on-exit`, `end-on-turn-cap` (`reason=turn_cap`), `end-on-end-request`.
- `SessionEndReason.TIMEOUT` becomes `TURN_CAP`; old records' `timeout` still reads.
- Kind and producer literals in the session package are replaced by constants.
- The CI records are regenerated.

## design as built (written before the run, 2026-10-09)

**Renames.** Form `<what it starts>-on-<event>`, all hyphen-case, as `first-message-on-session-prompt` already is:

| Today | New |
|---|---|
| `run-tool` | `tool-on-tool-call` |
| `continue` | `model-on-tool-result` |
| `wrap-up` | `model-wrap-up-on-tool-result` |
| `end-on-cap` (`reason=timeout`) | `end-on-turn-cap` (`reason=turn_cap`) |
| `end-on-user-end` | `end-on-end-request` |
| `emit-interrupt-fragment` | `interrupt-fragment-on-interrupt-request` (K.5 spelled it `interrupt_fragment-on-…`, mixing the producer's underscore into a hyphenated name) |
| `advance-on-park` (CI wrapper) | `driver-stepper-on-returned` (it fires on the turn's end, `Returned` or an old `Park`; K.5 does not list it) |

Unchanged: `return-on-reply`, `return-on-model-error`, `return-on-interrupt`, `end-on-exit`, `model-on-user-message`, `first-message-on-session-prompt`. K.5's `model-on-prompt-composed` was retired by § L. The constants take the new names (`TRIGGER_ID_TOOL_ON_TOOL_CALL`, …).

**Outside scope:** `tool_loop` has its own `run-tool`, `continue` and `wrap-up`. It is a separate topology with its own CI record, and the benchmarks read it; it keeps its names.

**Turn cap.** `SessionEndReason.TIMEOUT` becomes `TURN_CAP = "turn_cap"`. Old records keep `timeout`; `LEGACY_SESSION_END_REASONS` in `vocabulary.py` maps it, and the UI's "session ended (…)" row reads through the same mapping.

**Literals.** `ToolCall`, `ToolResult` and `InterruptRequested` in `__init__.py` subscriptions and views give way to `TOOL_CALL`, `TOOL_RESULT` (`tool_loop/kinds.py`) and a new `INTERRUPT_REQUESTED`. The card's grep also matches `"model"` at `_usage_of`, which is the `ModelUsage.model` field key, not a producer kind; it stays.

### Predicted breaks

- `test_session_vocabulary_constants.py`: renamed constants and `TIMEOUT`.
- `test_session_topology_e2e.py`: names `advance-on-park` in its trigger set.
- `test_session_topology_failure_modes.py::test_end_on_cap_finalises_with_timeout_reason`: asserts `reason == "timeout"`.
- `test_session_topology_bundled.py` and the `session` and `daily` CI records: trigger ids sit in RunStarted's topology and every TriggerFired. No other record moves.
- Unchanged: every UI test and gate (none names a session trigger id).

## prerequisites

- K263 closed.

## context_files

- `sdd-kit-2/AGENTS.md`
- `substrate/process/planning/RESEARCH-2026-10-09-session-topology-structure-round4.md`
- `substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md`
- `substrate/process/signals/session-vocabulary.md`
- `substrate/process/BLACKBOARD.md`
- `substrate/src/substrate/topologies/session/__init__.py`, `vocabulary.py`, `views.py`, `ci.py`

## signal contract

### Emits

- `SessionEnded` (`reason=turn_cap` for the cap)

### Invariants

- Trigger behavior is unchanged; only names and the cap's reason change.

## artifact contract

### Files created

- `substrate/tests/test_trigger_names_264.py`

### Files modified

- `substrate/src/substrate/topologies/session/__init__.py`
- `substrate/src/substrate/topologies/session/vocabulary.py`
- CI records under `topologies/session/records/` and `topologies/daily/records/` (regenerated)

### Content assertions

- `grep -nE '"(ToolResult|ToolCall|FinalAnswer|PromptComposed|InterruptRequested|Park|model)"' substrate/src/substrate/topologies/session/*.py` returns nothing outside `vocabulary.py`.

### Command exit codes

- `uv run python -m pytest tests/test_trigger_names_264.py` returns 0.
- `uv run python -m pytest` (kernel fast suite), `ruff check`, `ruff format --check`, `mypy --strict src`, `lint-imports` return 0.
- `uv run --project ../substrate python -m pytest tests/` in substrate-ui returns 0.

## observation contract

### Driving steps

- Open the structure view of a session in the installed app.

### Expected

- Every trigger name listed is one of K259's names.

## done criteria

Every session trigger is named for what it starts and what starts it.

## result

- **Names.** The session declares 13 trigger ids, each `<what it starts>-on-<event>` in hyphen-case (table above; vocabulary § O). The `session_started` instrument's trigger keeps the kernel's name. `tool_loop` keeps its own three names.
- **Turn cap.** `end-on-turn-cap` ends the session with `reason=turn_cap`. `LEGACY_SESSION_END_REASONS` maps an old `timeout`, and the UI's "session ended (…)" row reads through the same table.
- **Literals.** `ToolCall`, `ToolResult` and `InterruptRequested` in subscriptions and views now come from constants (`TOOL_CALL` and `TOOL_RESULT` from `tool_loop/kinds.py`, plus a new `INTERRUPT_REQUESTED`). `test_trigger_names_264.py` scans the package for raw kind strings outside docstrings, comments and `__all__`. The card's own grep also matches `"model"` in `_usage_of`, which is the `ModelUsage.model` field key; it stays.
- **Checks:**
  - Kernel suite: 1,354 passed, 4 skipped, 2 failed. Both failures are real-model sampling, not K264:
    - `test_realmodel_background_bash_103`: the known flaky test.
    - `test_realmodel_demos.py::test_ensemble_real_disagreement_and_cancel`: it needs three `llama3.2:1b` samples at temperature 0.9 to give two different one-word answers. In 10 solo runs it failed twice, both times with all three answering "integrity.". The test fails about one run in five whatever the code does; the ensemble topology is untouched here.
  - UI suite: 215 passed. Ruff, format, `mypy --strict`, `lint-imports` and `tsc` are clean.
  - Installed app, rebuilt with the K264 kernel: `vm_smoke` 12 of 12; shakeout 3 runs, 0 bugs; all ten gates pass. `structure_lists_producers.ts` now also checks that every trigger row in the structure view has the form; the app lists 13 triggers.
  - CI records: `session` and `daily` move. `natural_conversation` still differs from HEAD only by K267's seq-39 change; the other 15 were restored.
- **Prediction miss:** the first suite run stopped at collection. `test_prompt_fragment_interrupt.py` imports `TRIGGER_ID_EMIT_INTERRUPT_FRAGMENT`, and the prediction search looked for the old id strings, not the old constant names. A first fix with BSD `sed` and `\b` changed nothing; it was redone in Python.
