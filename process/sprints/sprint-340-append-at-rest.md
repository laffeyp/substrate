# Sprint 340 — An event appended to a session's record during or between turns

```yaml
---
id: 340
status: closed
closed_at: 2026-11-05
phase: editor shared work
pass_kind: functional
depends_on: []
plan: ../substrate-ui/process/planning/2026-11-05-editor-shared-work/PLAN-2026-11-05-editor-shared-work.md
---
```

## scope

Editor shared item 0(d). One registry call that writes an application event to a session's record whether a turn is running or not, and the first edit kind, `FileWritten`. Between turns a session's run is paused on disk: `Runtime.inject_event` needs a live run and `Runtime.resume` starts a turn, so the kernel gains `api.append_at_rest`, which appends to a paused record without resuming it. Nothing existing changes: no run writes a different frame except `RunStarted.config.vocab_version`.

## context_files

- `src/substrate/kernel/runtime.py` (`Runtime.resume`, `_resume_bootstrap`, `inject_event`, `_drive`'s lock and record setup)
- `src/substrate/kernel/sequencer.py` (`cycle`, `_emit`, `_resolve`, `_maybe_offload`)
- `src/substrate/record/record.py` (`RecordWriter`, `recover_and_read`)
- `src/substrate/topologies/session_registry.py` (`turn_sync`, `interrupt`, `_scan_record_status`)
- `src/substrate/projections/graph.py` (the pause read from the last frame)
- `process/signals/0.3.json` (RUN-BOUNDARY, PAUSE/RESUME RE-ENTRY), `process/signals/session-vocabulary.md`
- substrate-ui research r8 and r11 (the edit on the record; the inspector's HISTORY)

## signal contract

Emits (record kinds): `FileWritten` (new, session vocabulary v0.17); `substrate.TerminationMatched` restated after an at-rest append (kernel vocabulary v0.4, AT-REST APPEND).

## artifact contract

- `src/substrate/kernel/runtime.py`: contains `def append_at_rest` and `class RecordNotAtRestError`.
- `src/substrate/api.py`: exports both.
- `src/substrate/topologies/session_registry.py`: contains `def append_event`.
- `src/substrate/topologies/session/__init__.py`: `class FileWritten`; `vocabulary.py`: `FILE_WRITTEN` in `SESSION_KINDS`.
- `process/signals/0.4.json`, `0.4-rationale.md`; `current.json` → `0.4.json`; `proposals.json` gains `P-AT-REST-APPEND`, ratified.
- `process/signals/session-vocabulary.md`: § AB.
- The 18 bundled CI records: `RunStarted.config.vocab_version` `0.4`, nothing else.
- `tests/test_append_at_rest_k340.py`.

Command exit codes: `uv run ruff check src` 0; `uv run ruff format --check src` 0; `uv run mypy src` 0; `uv run python -m pytest tests/test_append_at_rest_k340.py` 0; the full kernel suite 0.

## observation contract

Behaviour is the record, read back by the tests:
- A paused record takes an event at seq N and the pause again at N+1, with the pause's payload unchanged; every frame before N is unchanged; the record then resumes to its terminal on one dense sequence.
- A session between turns gets `FileWritten`, scans as `parked`, and takes its next turn with the next turn index.
- A session in a turn (its model step held open on a `threading.Event`) gets `FileWritten` inside that turn, between its `UserMessage` and its `Returned`, through the live run.
- Refused, the record unchanged: no record, a reserved kind, a finalised record; a live run raises `BusLockedError`.
- Planted faults: the restated pause removed fails three tests; the live path forced to report "not running" fails the in-turn test.

## result

- **Built.** `api.append_at_rest(record_root, event)` (`runtime.py`): refuses a reserved kind or a non-canonical payload; takes the record's lock; recovers a torn tail; refuses a record whose last frame is not a pause; appends the event (`producer` null, blob store above 16 KiB) and the pause again; returns the event's seq. `SessionRegistry.append_event(session_id, event)`: with the per-session lock free, `append_at_rest`; with a turn holding it, `inject_event` on the turn's loop, only while that run's phase is `RUNNING`; in the moments a turn starts or ends, it waits on the lock for either path, up to 30 s.
- **Vocabulary.** Kernel v0.4 (one sequence rule, AT-REST APPEND; `VOCAB_VERSION` `0.4`). Session v0.17 (§ AB, `FileWritten`).
- **Tests.** `tests/test_append_at_rest_k340.py`, 7, as the observation contract lists.
- **Full suite.** 1,689 passed, 14 skipped, 2 failed. `test_the_committed_api_page_is_current`: `docs/api.md` regenerated after `scripts/gen_api_docs.py` grouped `append_at_rest` and `RecordNotAtRestError`; passes. `test_inspect_record_summary_read_back_by_model`: the live model (`qwen2.5:7b-instruct`) passed the temp folder without `/seeded` and did not retry; fails the same way at `b547dd01`, logged as K340-Q-1 on the BLACKBOARD.
- **Rubber Duck Pass.** On the in-turn record: `UserMessage` (turn 1) → `FileWritten` (`producer` null, the edit) → the turn's model step → `Returned` → `TerminationMatched` pause. On the between-turns record: `TerminationMatched` pause → `FileWritten` → `TerminationMatched` pause, same payload → next `UserMessage` (turn 1). Missing pair: none (`FileWritten` has no view tag yet; the UI vocabulary adds one with the editor's HISTORY). Order: AT-REST APPEND holds; RUN-BOUNDARY holds (finalised records refused). Payload: as § AB. Timing: none. Tone: none.
