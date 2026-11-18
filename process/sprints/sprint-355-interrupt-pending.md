# Sprint 355 — An interrupt the turn cannot take yet is kept, and says so

```yaml
---
id: 355
status: closed
phase: core stalls (substrate-ui roadmap 2026-11-18-core-stalls r1, C2)
pass_kind: functional
depends_on: [354]
plan: ../substrate-ui/process/planning/2026-11-18-core-stalls/ROADMAP-2026-11-18-core-stalls-r1.md
---
```

## scope

`SessionRegistry.interrupt` answers `None`, "no turn in flight", in two cases where a turn is in flight. (1) The turn's loop is busy, as through a bootstrap (9.4 s on a 4 MB record): the cancel is queued with `call_soon_threadsafe`, the one-second wait runs out, and `None` comes back — yet the queued cancel runs when the loop frees and, since K354, ends the turn. (2) The turn is accepted but its worker has not yet set `TurnHandle.loop`: the cancel is dropped. In both, `interrupt` now returns `PENDING_INTERRUPT`, `{"kind": "pending", "instance": "", "parent": None}`. In case 2 the handle keeps the request (`TurnHandle.pending_tier`), and the worker schedules it on the loop it creates, where it runs after the bootstrap as case 1's does. One verifiable property: an interrupt during a turn's bootstrap returns the pending reference and the turn ends `Returned` `interrupted`.

## context_files

- `src/substrate/topologies/session_registry.py` (`TurnHandle`, `interrupt`, `_run_run_sync`, `_run_resume_sync`)
- `../substrate-ui/server.py` (`_session_interrupt`), `../substrate-ui/web/vm/session_controller.ts` (the interrupt's text)

## signal contract

### Emits

- No new tags. The turn's record ends `ProducerCancelled` (`caller` `daemon:interrupt-hard`), `Returned` `interrupted`, as K354 makes it.

### Invariants

- An interrupt on an idle session still answers `None`.
- An interrupt that reaches a live producer at once still answers its reference.

## artifact contract

### Files modified

- `src/substrate/topologies/session_registry.py`

### Files created

- `tests/test_interrupt_pending_355.py`

### Command exit codes

- The new test and the interrupt and session-registry tests return 0; ruff and `mypy --strict` clean.

## observation contract

The research's reproduction: the interrupt 1.7 s into `s_7c1dab4e`'s copied bootstrap returns the pending reference, and the turn ends `Returned` `interrupted`.

## close

`session_registry.py`: `PENDING_INTERRUPT`; `TurnHandle.pending`, (session_id, tier); `interrupt` answers pending when the handle has no loop yet (and keeps the request) and when its one-second wait times out (the cancel stays queued); the loop-side cancel is the module function `_cancel_step`, queued by `_schedule_cancel`; both workers schedule a kept request on the loop they create, where it runs after the run's bootstrap.

- `tests/test_interrupt_pending_355.py`: 3 passed. An interrupt during a 2 s bootstrap answers pending and the turn ends `Returned` `interrupted`; an interrupt with the handle registered and no loop yet answers pending and the turn ends the same way; an idle session still answers None.
- Mutants: the busy-loop path answering None fails 1; the workers ignoring a kept request fail 1.
- Interrupt, cancel, registry, delegate and session-topology tests: 126 passed. ruff clean; `mypy --strict` clean.
- Observation: the research's reproduction, the interrupt 1.65 s into `s_7c1dab4e`'s copied bootstrap, answered `{'kind': 'pending', 'instance': '', 'parent': None}`; the turn finished in 6.6 s ending `ProducerCancelled`, `Returned` `interrupted`.

Rubber Duck Pass: no record frame changed; the reproduction's tail is K354's. No observations.
