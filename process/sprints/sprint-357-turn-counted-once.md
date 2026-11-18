# Sprint 357 — The history view counts each event once

```yaml
---
id: 357
status: closed
phase: core stalls (substrate-ui roadmap 2026-11-18-core-stalls r1, C4)
pass_kind: functional
depends_on: [356]
plan: ../substrate-ui/process/planning/2026-11-18-core-stalls/ROADMAP-2026-11-18-core-stalls-r1.md
research: ../substrate-ui/process/planning/2026-11-18-core-stalls/RESEARCH-2026-11-18-bootstrap-time.md
---
```

## scope

`TurnHistory.update` re-renders the current turn and counts all of it on every event (`turn_cost(self._current)`, `output_savings(self._current)`), so a turn of n events is counted n times. Since K352 the count is a tokenizer pass; on a copy of `s_7c1dab4e` (11,882 envelopes) it was 5.35 s of an 8.84 s resume, 1,174 `Tokenizer.encode` calls. The renderer's per-event step becomes `transcript._event_lines`, used by `_render_turns` and by the view; the view adds each event's lines and its result's saving to the turn's running cost as the event arrives. One verifiable property: the same resume spends a fraction of the time in `encode`, and every history and compaction test holds.

## context_files

- `src/substrate/topologies/session/transcript.py` (`_render_turns`, `turn_cost`, `output_savings`, `result_lines`)
- `src/substrate/topologies/session/views.py` (`TurnHistory`)

## signal contract

### Emits

- `TranscriptCompacted` and `PromptComposed` as before; a turn's planned cost can differ by the few tokens a tokenizer merges across a line break.

### Invariants

- `PromptComposed.text` is byte-identical: `_render_turns` renders the same lines.
- The plan is a function of the record.

## artifact contract

### Files modified

- `transcript.py`, `views.py`

### Files created

- `tests/test_turn_counted_once_357.py`

### Command exit codes

- The new test, the history, compaction and session tests, the committed-record tests (records regenerated if their counts moved) return 0; ruff and `mypy --strict` clean.

## close

`transcript.py`: the renderer's per-event step is `_event_lines`, with `TurnRender` carrying each harness call's tool and the turn's last reply; `_render_turns` is the header plus `_event_lines` per event; `event_saving` is one result's saving and `output_savings` its list; `turn_cost` is `turn_header_cost` plus `event_cost` per event. `views.py`: `TurnHistory` adds each event's `event_cost` and `event_saving` as it arrives.

- `tests/test_turn_counted_once_357.py`: 2 passed. The view's running count and savings equal `turn_cost` and `output_savings` on two turns with every rendered kind; a 303-event turn folds with at most three counts per event.
- Mutant (the view re-counting the whole turn on every event): the once-per-event test fails; the equality test passes, as a recount reaches the same sum.
- The committed records and the history and compaction tests (113) passed after the renderer change: `PromptComposed.text` is byte-identical. Full kernel suite: 1,737 passed, 14 skipped. ruff clean; `mypy --strict` clean.
- Observation: the resume of `s_7c1dab4e`'s copied record under `cProfile` took 3.58 s, from 8.84 s; `Tokenizer.encode` left the profile's top 28.
- These are unit tests of the view. The end-to-end check of a resumed turn through the server is the core-stalls observation test that follows.

Rubber Duck Pass: no frame changed. No observations.
