# Sprint 356 — `turn_sync` can bound its wait for the session's lock

```yaml
---
id: 356
status: closed
phase: core stalls (substrate-ui roadmap 2026-11-18-core-stalls r1, C3)
pass_kind: functional
depends_on: [355]
plan: ../substrate-ui/process/planning/2026-11-18-core-stalls/ROADMAP-2026-11-18-core-stalls-r1.md
---
```

## scope

The quit's sweep ends each session through `turn_sync`, which acquired the session's `threading.Lock` with a plain `with`: no limit. A turn that never returned held the lock, the sweep waited forever, and Electron killed the backend at 45 s (review 2026-11-18, § 3.2). `turn_sync` takes `lock_timeout_seconds`; past it, it raises `SessionBusy` (a `TimeoutError`). None, the default, waits as before. One verifiable property: with the lock held elsewhere, `turn_sync(lock_timeout_seconds=0.5)` raises `SessionBusy` in about half a second.

## context_files

- `src/substrate/topologies/session_registry.py` (`turn_sync`), `src/substrate/app.py` (its re-exports)

## signal contract

### Emits

- None; no record frame changes.

### Invariants

- Without `lock_timeout_seconds` a turn waits for the lock as before, and every path releases it.

## artifact contract

### Files modified

- `src/substrate/topologies/session_registry.py`, `src/substrate/app.py`

### Files created

- `tests/test_turn_lock_timeout_356.py`

### Command exit codes

- The new test and the registry, interrupt and delegate tests return 0; ruff and `mypy --strict` clean.

## close

`SessionBusy`; `turn_sync(lock_timeout_seconds=)` acquires with that timeout and releases in a `finally`; `substrate.app` re-exports `SessionBusy` beside the registry's other exceptions.

- `tests/test_turn_lock_timeout_356.py`: 2 passed. A held lock ends the wait with `SessionBusy` between 0.4 and 3 s; two turns with a free lock run and leave it released.
- Mutant (the limit ignored): the held-lock test fails at its 10 s limit.
- Registry, interrupt and delegate tests: 91 passed (`test_session_registry_consolidated_099` caught the missing `substrate.app` export before it was added). ruff clean; `mypy --strict` clean.

Rubber Duck Pass: no frame changed. Consumer: substrate-ui sprint 519, the quit's sweep. No observations.
