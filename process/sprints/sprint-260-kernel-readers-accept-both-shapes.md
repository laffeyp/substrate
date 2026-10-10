# Sprint 260 — Kernel readers accept both session shapes

```yaml
---
id: 260
status: closed
opened_at: 2026-10-09
closed_at: 2026-10-09
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md
---
```

## why

K262 changes what a session writes. Records already on disk keep `Park` and `FinalAnswer` and must still read (research P6). Readers change first.

## scope

`vocabulary.py`:
- adds `RETURNED`;
- adds `is_turn_end(env)`, true for `Returned`, or for `Park` on an old record;
- adds `turn_reply(events)`, which returns a turn's reply from a `ModelReply` with `stop_reason` other than `tool_use`, or on an old record from the `ModelReply` before its `FinalAnswer`.

These readers use the two helpers:
- `transcript.py` (`_render`, `_split_turns`);
- `delegate.py:504` (fan-out child answer) and `:806` (standing-session answer);
- `cli.py:1002` (stream printer);
- `ci.py` (`advance-on-park` subscription accepts both).

`delegate.py:170` (tool_loop child) is unchanged.

## prerequisites

- K259 closed.

## context_files

- `sdd-kit-2/AGENTS.md`
- `substrate/process/planning/RESEARCH-2026-10-09-session-topology-structure-round4.md`
- `substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md`
- `substrate/process/signals/session-vocabulary.md`
- `substrate/process/BLACKBOARD.md`
- `substrate/src/substrate/topologies/session/vocabulary.py`, `transcript.py`, `ci.py`
- `substrate/src/substrate/topologies/tool_loop/delegate.py`
- `substrate/src/substrate/cli.py`

## signal contract

### Emits

None new; this sprint only reads.

### Invariants

- What a session writes is unchanged; the committed CI records still match.
- A tool_loop record reads as before.

## artifact contract

### Files created

- `substrate/tests/test_session_shapes_both_read_260.py`

### Files modified

- `substrate/src/substrate/topologies/session/vocabulary.py`
- `substrate/src/substrate/topologies/session/transcript.py`
- `substrate/src/substrate/topologies/session/ci.py`
- `substrate/src/substrate/topologies/tool_loop/delegate.py`
- `substrate/src/substrate/cli.py`

### Content assertions

- `grep -n 'FINAL_ANSWER' delegate.py` finds only the tool_loop read at `_run_child_to_answer`.
- `transcript.py` has no direct `== FINAL_ANSWER` or `== PARK` comparison.

### Command exit codes

- `uv run python -m pytest tests/test_session_shapes_both_read_260.py` returns 0.
- `uv run python -m pytest` (kernel fast suite), `ruff check`, `ruff format --check`, `mypy --strict src`, `lint-imports` return 0.
- `uv run --project ../substrate python -m pytest tests/` in substrate-ui returns 0.

## observation contract

### Driving steps

- The test builds an old-shape record (the committed session CI record) and a synthetic new-shape record of the same two turns.
- Each one goes through `render_transcript`, the delegate standing-session read and the CLI stream printer.

### Expected

- The rendered transcript, the delegate answer and the printed lines are equal for the two records; each turn's reply appears once.

## done criteria

Every kernel reader of session records reads the old and the new shape alike.

## result

- `vocabulary.py`: `RETURNED`, `TURN_END_KINDS` (`Returned`, `Park`), `StopReason`, `ReturnReason`, `turn_replies(events)`. A turn's reply is a v0.3 `ModelReply` whose `stop_reason` is not `tool_use`, or on an older record the `FinalAnswer`. An old `ModelReply` has no `stop_reason` and is not counted, so no reply counts twice.
- `transcript.py`: an empty `ModelReply` (a v0.3 tool-only call) renders nothing; `Returned` is a turn event; the old FinalAnswer de-duplication stays for old records.
- `delegate.py`: the fan-out child read (`_run_fanout`) and the standing-session read use `turn_replies`. `FINAL_ANSWER` remains only at the tool_loop child read (`_run_child_to_answer`).
- `ci.py`: `advance-on-park` subscribes to `TURN_END_KINDS`. That changed the `session` and `daily` CI topologies' fingerprints; their records were regenerated, with the event sequences byte-equal to before (kinds and texts compared). `gen_topology_records.py` rewrote all 18 records; the 16 untouched ones were restored from git.
- `cli.py` needed no change: `_render_stream_line` prints `ModelReply` text when there is any and skips `FinalAnswer`, which reads both shapes.
- Red before: the new test failed on import (no helpers). Green after: 5 passed.
- Gates: ruff, format, mypy --strict (138 files), lint-imports clean. Kernel suite 1,331 passed, 5 skipped; the 3 record failures are fixed by the regeneration, and `test_realmodel_background_bash_103` (real Ollama under suite load) failed again, as it did before this sprint. UI 215 passed.
