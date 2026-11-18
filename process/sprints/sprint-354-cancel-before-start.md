# Sprint 354 — A producer cancelled before it starts is recorded, and its run goes on

```yaml
---
id: 354
status: closed
phase: core stalls (substrate-ui roadmap 2026-11-18-core-stalls r1, C1)
pass_kind: functional
depends_on: [353]
plan: ../substrate-ui/process/planning/2026-11-18-core-stalls/ROADMAP-2026-11-18-core-stalls-r1.md
research: ../substrate-ui/process/planning/2026-11-18-core-stalls/RESEARCH-2026-11-18-core-stalls.md
---
```

## scope

`_flush_scheduled` counts a producer in flight when it creates its task (`runtime.py:670`); the sequencer lowers the count only when the producer's end frame is recorded (`sequencer.py:310`); the task writes `ProducerStarted` as its first statement and `ProducerCancelled` from its `CancelledError` handler. A task cancelled before its first step never runs its body, so it writes neither: `inflight` stays up, the run never goes quiet, and the run never ends. An interrupt during a session turn's bootstrap does exactly this (research), and the turn holds the session lock until the process dies. The fix: the task's done callback, finding the task cancelled with its body never begun, writes the `ProducerStarted` and the `ProducerCancelled` (with the cancel's `cause` and `caller`) the body would have written. The vocabulary's cohort-frontier invariant (completed + failed + cancelled = started for every producer) holds again; no tag or payload changes. One verifiable property: a session turn interrupted during its bootstrap ends with `ProducerCancelled` and `Returned` `interrupted`.

## context_files

- `src/substrate/kernel/runtime.py` (`_flush_scheduled`, `_producer_task`, `cancel_producer`, `_writer_loop`)
- `src/substrate/kernel/runstate.py`, `src/substrate/kernel/sequencer.py` (`_track_lifecycle`)
- `src/substrate/topologies/session_registry.py` (`interrupt`, `_run_resume_sync`)
- `process/signals/current.json` (`substrate.ProducerStarted`, `substrate.ProducerCancelled`, the cohort-frontier invariant)

## signal contract

### Emits

- `substrate.ProducerStarted` then `substrate.ProducerCancelled` (`cause`, `caller` as the cancel set them) for a producer cancelled before its first step.

### Invariants

- A producer whose body ran records exactly the frames it recorded before.
- Every `TriggerFired` instance gets a `ProducerStarted` and one end frame.

## artifact contract

### Files modified

- `src/substrate/kernel/runtime.py`, `src/substrate/kernel/runstate.py`

### Files created

- `tests/test_cancel_before_start_354.py`

### Command exit codes

- The new test and the kernel's runtime, cancel and session tests return 0; the full kernel suite returns 0; ruff and `mypy --strict` clean.

## observation contract

The research's reproduction: a copy of `s_7c1dab4e`'s record, resumed with one message and an interrupt 1.66 s in, during the bootstrap. Before: the turn hangs and the record ends at `TriggerFired`. After: the turn returns, the record ends `ProducerStarted`, `ProducerCancelled` (`caller` `daemon:interrupt-hard`), `Returned` `interrupted`, `TerminationMatched` `pause-await-input`.

## done criteria

An interrupt at any moment of a turn ends the turn.

## close

`runstate.py`: `RunState.began`, the instances whose task body has begun. `runtime.py`: `_producer_task` adds its instance as its first statement; the task's done callback, finding the task cancelled and its instance not begun, puts `ProducerStarted` and `ProducerCancelled` (`cause`, `caller` from `cancel_reasons`) on the inbox, so the sequencer lowers `inflight` and the session topology's return-on-interrupt ends the turn. A producer whose body ran writes exactly what it wrote before; no tag or payload changed.

- `tests/test_cancel_before_start_354.py`: 3 passed. A run whose producer is cancelled at its task's creation records `ProducerStarted` then `ProducerCancelled` (`cause` `external`, `caller` `test:bootstrap-esc`) and finalises; a producer that ran records one `ProducerStarted`, its emission and no cancel; a session turn cancelled the same way ends `ProducerStarted`, `ProducerCancelled`, `TriggerFired`, `ProducerStarted`, `Returned` `interrupted`, `TerminationMatched`, the session parked and its next turn answered.
- Mutant (the done callback's frames removed): the two cancel tests fail, the third passes.
- Full kernel suite: 1,730 passed, 14 skipped. ruff clean; `mypy --strict` clean.
- Observation: the research's reproduction, `s_7c1dab4e`'s record copied and resumed with an interrupt 1.69 s in. Before the fix the turn hung and the record ended at `TriggerFired` seq 11883; after it the turn finished in 7.6 s and the record reads `ProducerStarted`, `ProducerCancelled`, `TriggerFired` `return-on-interrupt`, `ProducerStarted`, `Returned` `interrupted`, `TerminationMatched`. The interrupt itself still answered `None`: roadmap C2.

Rubber Duck Pass: every `TriggerFired` instance in the new records has a `ProducerStarted` and one end frame, as the vocabulary's cohort-frontier invariant requires. Observation: order, the cancelled-before-start pair lands after the cycle that created the task, as a `ProducerCancelled` from the body would; resolved-here.
