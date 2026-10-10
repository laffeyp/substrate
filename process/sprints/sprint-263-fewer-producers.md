# Sprint 263 — Fewer producers, each named for what it does

```yaml
---
id: 263
status: closed
opened_at: 2026-10-09
closed_at: 2026-10-09
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md
---
```

## why

Five producers each emit one session-open fragment. A three-link chain runs before every model call. Two producers emit `SessionWarning`, and `session_open` emits a `UserMessage` (research F6, F7). A plain turn writes 20 envelopes.

## scope

- `session_prompt` replaces `role_fragment`, `bundle_methodology_fragment`, `bundle_personality_fragment`, `tools_suite_fragment` and `parent_context_fragment`. It emits one `PromptFragment` per source, each keeping its `source`. The parent-context slice reuses delegate's extractor instead of a copy (lens F106).
- `prompt_composer` fires on `UserMessage` and reads `per_turn` itself; `per_turn_fragment`, `emit-per-turn-fragment` and `compose-on-cohort-complete` go.
- `warning` replaces `session_warning` and `fragment_error_warning`.
- `session_open` becomes `first_message`.

## found during K262 (2026-10-09)

- The `prompt_composer` line above is already done: K261 moved prompt building into the model step and removed `per_turn_fragment`, `emit-per-turn-fragment` and `compose-on-cohort-complete`.
- The `model_failures` view is registered and read by nothing; `return-on-model-error` filters `ProducerFailed` itself. It goes with the other unused parts.

## design as built (written before the run, 2026-10-09)

- **Measured before.** On a deterministic session with role `reviewer`, bundle `session` and the calculator tools, 22 envelopes precede the first `UserMessage`. Six producers start: `session_started`, `role_fragment`, `bundle_methodology_fragment`, `bundle_personality_fragment`, `tools_suite_fragment` and `session_open`. A later plain turn writes 10 envelopes. K261 and K262 already took the plain turn from 20 to 10, so this card's saving is at session open.
- **One producer, five failure domains.** Each of the five producers was its own failure domain: a missing role file failed `role_fragment` alone, and `warn-on-fragment-error` named it. Merged into one producer, a single raise would drop every source after it. `session_prompt` therefore catches each source's error and records it as a `SessionWarning(kind=fragment_source_failed, source_name=<the PromptSource>, detail=<repr of the error>)`, then goes on to the next source. The tool seam does the same with a tool's error (`ToolResult.ok=false`). Each source builds its fragments in full before any is yielded, so a failed source contributes none.
- **No `warning` producer.** With source failures recorded inside `session_prompt`, the one remaining warning is `seed_alone_exceeds`, which is also a fact about the session prompt and is known at the same moment. `session_prompt` emits it first. One producer then emits `SessionWarning`, which is F7's point; K.4's `warning` row and K.5's `warning-on-fragment-error` row do not get built. `interrupt_fragment` yields a constant; a failure there is a kernel fault, recorded as `substrate.ProducerFailed`.
- **`SessionWarning.detail`** (optional string) carries the error text that `substrate.ProducerFailed.error` carried before. `source_name` holds the source (`role`, `tools_suite`, …), not a producer kind.
- **The first message still waits.** `first-message-on-session-prompt` fires on the `session_prompt` producer's `ProducerCompleted` or `ProducerFailed`. It orders the first message after the session prompt; no trigger orders prompt pieces among themselves. The `ProducersEnded` view goes; the predicate reads the event's producer kind.
- **One slice extractor.** The extractor moves from `tool_loop/delegate.py` to `session/context_slice.py`; delegate and `session_prompt` both import it. Each keeps its own cap: 8,192 bytes for delegate, 64 KiB for a session's parent context. The session copy lacked delegate's v0.3 kind match (§ M.5), so a session `parent_context` slice filtered on `FinalAnswer` now also takes v0.3 replies.
- **Removed:** `ModelFailures` and `model_failures`, `ProducersEnded`, `FRAGMENT_SOURCE_KINDS`, `TRIGGER_ID_WARN_ON_FRAGMENT_ERROR`, the seven old producer-kind constants, and the four source modules (`role_producer.py`, `bundle_producer.py`, `tools_suite_producer.py`, `parent_context_producer.py`).
- **Found, filed on K265:** `FragmentCohort` keeps one slot per session-open source with the latest winning, so a bundle whose `extends` chain has two methodologies sends only the last to the model. K263 keeps that behavior: the invariant here is unchanged prompt bytes.
- **Found, UI:** the session view renders a `SessionWarning` as `warning: ${payload.condition_kind}`; the struct has no such field, so every warning reads "warning: warning". Fixed to read `kind`, `source_name` and `detail`.

### Predicted breaks

- `test_session_vocabulary_constants.py`: the removed constants and `FRAGMENT_SOURCE_KINDS`.
- `test_fragment_source_failure_handling.py`: no `ProducerFailed` for a failed source; the warning names `tools_suite`, not `tools_suite_fragment`. Rewritten to the new contract.
- `test_prompt_fragment_bundle.py`, `test_prompt_fragment_parent_context.py`, `test_prompt_fragment_role.py` (`_PRECEDENCE`), `test_delegate_per_call_context.py`: import paths of the moved functions.
- `test_render_seed_alone_exceeds.py`: it looks for a `session_warning` initial and producer.
- `test_session_topology_bundled.py` and the committed CI records of `session`, `daily` and `natural_conversation`: the topology fingerprint and the session-open envelopes change. Every other record is unchanged.
- Unchanged: `test_prompt_built_once_261.py` (prompt bytes), the role and tools-suite fragment tests (they match on `source`), every UI test.

## prerequisites

- K262 closed.

## context_files

- `sdd-kit-2/AGENTS.md`
- `substrate/process/planning/RESEARCH-2026-10-09-session-topology-structure-round4.md`
- `substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md`
- `substrate/process/signals/session-vocabulary.md`
- `substrate/process/BLACKBOARD.md`
- `substrate/src/substrate/topologies/session/__init__.py`, `vocabulary.py`, `views.py`
- `role_producer.py`, `bundle_producer.py`, `tools_suite_producer.py`, `parent_context_producer.py`, `per_turn_producer.py`

## signal contract

### Emits

- `PromptFragment` (same fields; `source` per fragment)

### Invariants

- The composed prompt's bytes are unchanged for a session with a role, a bundle, tools and a per_turn line (K261's test passes unmodified).

## artifact contract

### Files created

- `substrate/src/substrate/topologies/session/session_prompt_producer.py`
- `substrate/tests/test_fewer_producers_263.py`

### Files modified

- `substrate/src/substrate/topologies/session/__init__.py`
- `substrate/src/substrate/topologies/session/vocabulary.py`

### Content assertions

- The session registers 11 producer kinds or fewer.
- No trigger subscribes to `substrate.ProducerCompleted` to order prompt pieces.

### Command exit codes

- `uv run python -m pytest tests/test_fewer_producers_263.py` returns 0.
- `uv run python -m pytest` (kernel fast suite), `ruff check`, `ruff format --check`, `mypy --strict src`, `lint-imports` return 0.
- `uv run --project ../substrate python -m pytest tests/` in substrate-ui returns 0.

## observation contract

### Driving steps

- The same plain turn as the research measurement, before and after.

### Expected

- The envelope count per plain turn is recorded on the card; the target is 13 or fewer, from 20.
- The structure view in the installed app lists the new producer names.

## done criteria

The session's producers are fewer, each does one named job, and a plain turn writes fewer envelopes.

## result

- **Producers.** The session registers 8 producer kinds, down from 14 possible: `session_started`, `model`, `tool`, `return`, `session_end`, `interrupt_fragment`, `session_prompt` and `first_message`. The CI wrapper adds `driver_stepper`. `session_prompt_producer.py` holds the five sources as plain functions; `role_producer.py`, `bundle_producer.py`, `tools_suite_producer.py` and `parent_context_producer.py` are deleted. The design notes above were followed as written.
- **Envelopes.** Session open, with role, bundle and tools, went from 22 envelopes before the first `UserMessage` to 13. A plain later turn is 10, before and after; K261 and K262 had already cut it from the research's 20.
- **Failure isolation.** A source that raises yields a `SessionWarning` naming the source and the error, with no `ProducerFailed`; the other sources' fragments land and reach the first prompt (`test_fragment_source_failure_handling.py`).
- **One extractor (F106).** `session/context_slice.py` serves delegate and the session. The session's slice gains § M.5: a `FinalAnswer` filter on a v0.3 parent now takes its replies, where the copy took nothing (`test_fewer_producers_263.py`).
- **Removed:** `ModelFailures`, `ProducersEnded`, `FRAGMENT_SOURCE_KINDS`, `warn-on-fragment-error`, and seven producer constants. Vocabulary addendum N records the change from K.4 and K.5.
- **Content assertions.** 8 producer kinds, within the card's limit of 11. One trigger subscribes to `ProducerCompleted`: `first-message-on-session-prompt`, which orders the first message after the session prompt. No trigger orders prompt pieces among themselves.
- **Found and fixed outside the plan:**
  - The UI's warning row read a field `SessionWarning` never had (`condition_kind`), so every warning showed "warning: warning". It now reads `kind`, `source_name` and `detail`.
  - `test_prompt_fragment_parent_context.py::test_kinds_filter_drops_non_matching_events` had checked nothing since K262: it filtered on `Park`, and its assertions sat behind `if frags:`. It now filters on `Returned` and requires the fragment.
- **Checks:**
  - Kernel suite: 1,352 passed, 4 skipped, 0 failed (10 min 40 s).
  - UI suite: 215 passed. `tsc` is clean, and so are ruff, ruff format, `mypy --strict` and `lint-imports`.
  - CI records: `session` and `daily` move, as predicted. `natural_conversation` moves at seq 39 for K267's reason (its card, line 171), not K263's. The other 15 regenerated byte-identical apart from run ids and timestamps, and were restored.
  - Installed app, rebuilt with `pack:runtime`, signed, not notarized: `vm_smoke` 12 of 12; shakeout 3 runs, 0 bugs; all nine gates pass. A new gate, `structure_lists_producers.ts`, reads the 8 producers from the structure view. `both_session_shapes.ts` now also checks the warning row.
- **Prediction misses:** none. Every predicted break broke, and nothing else did.
