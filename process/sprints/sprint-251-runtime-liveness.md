# Sprint 251 — Runtime liveness

```yaml
---
id: 251
status: halted on F017 (every other row closed)
halted_at: 2026-10-08
opened_at: 2026-10-08
pass_kind: remediation
roadmap: substrate-ui/process/planning/ROADMAP-2026-10-08-lens-audit-remediation.md
ledger_rows: 15
---
```

## why

A TimeoutError without a wall budget trips an assert and the run never ends (probe); the watchdog has no timer; Budget.event_counts is not enforced (findings §6).

## sources

- *Twelve-Factor App*, IX Disposability.

## scope (ledger rows)

Each row closes as named; a row the sprint cannot close halts the sprint.

| id | close | finding |
|---|---|---|
| F014 | fix | CONFIRMED runtime.py:689-690 — `except asyncio.TimeoutError: assert wall_cap is not None`. On 3.11+ asyncio.TimeoutError IS builtin TimeoutError, so any Producer without a wall budget that raises TimeoutError (socket/… |
| F016 | fix | runtime.py:936 — cancel_producer returns {"parent": None} regardless of the instance's real parent. |
| F017 | fix | runtime.py:508-533 — every resume folds the WHOLE record (read_record with blob resolution) to restore views/counts; a session turn is a resume, so turn N costs O(N) and a session O(N²). (Measure on a long session bef… |
| F018 | fix | runtime.py:96-106 — process-global _ACTIVE_RUNTIMES_BY_RECORD_ROOT keyed by str(Path(root)) unresolved; a relative vs absolute spelling of one root misses (find_active_runtime). |
| F021 | fix | policies.py:123-132 + runtime.py:383-384 — quiescence_with_watchdog(seconds) has no watchdog: `seconds` only feeds poll_s = min(0.01, seconds), so any value >= 0.01 (the default 30) has no effect. "Watchdog" names a t… |
| F022 | fix | runstate.py:27-37 RunPhase{running,paused,finalised,failed} and constants.py RunStatus{incomplete,paused,finalised,failed} (added sprint 107) — two enums carrying the same three outcome values; runtime._status() maps … |
| F023 | fix | topology.py:33-34,55-56 — Budget/Cap docs say a breach yields `substrate.BudgetExceeded`; no such kind exists (constants.LIFECYCLE_KINDS); the runtime records ProducerFailed{error:"budget_exceeded", budget_exceeded:{.… |
| F024 | fix | topology.py:215-232 — Budget.event_counts is accepted and stored but never enforced (UserWarning only, since Sprint 164 → 199); a declared cap that does nothing. |
| F025 | fix | composition.py:52 — kernel/ imports projections/ (LiveRecord): the writer layer depends on a reader layer. |
| F026 | fix | composition.py:138-140 — comment says the inner root comes "from the input ... or a fresh child of the cwd"; the code (231-244) refuses without inner_root. |
| F027 | fix | policies.py:45 — TermContext.resume_condition is never set by the runtime (runtime.py:799-806). |
| F028 | fix | topology.py:208-214 — producer_kind() calls factory() at registration to sniff an export map, swallowing any exception. |
| F032 | fix | "__initial__" literal at graph.py:51, runtime.py:477,478,488,489 — no constant. |
| F033 | fix | run-failure reasons "view_failure"/"kernel_error"/"stuck_quiescent" are literals at sequencer.py:278, runtime.py:413,448 and re-listed in graph.py:59 — one vocabulary in three places, no enum. |
| F037 | fix | Three subscription matchers: sequencer.subscribed (71), runtime._resume_view_matches (986), inspect._envelope_matches (345) — same rule on Event vs dict; plus two `_as_event` copies (runtime.py:998, inspect.py:357). |

## checks

- A producer raising TimeoutError with no wall budget is recorded ProducerFailed and the run finalises (probe becomes a test).
- `quiescence_with_watchdog(seconds)` fires after `seconds` of no progress, or the name changes to what it does.
- Budget.event_counts enforced with a test, or removed from the API.
- One subscription matcher; a failure-reason enum; `__initial__` a constant; one run-outcome enum.
- cancel_producer returns the real parent; the active-runtime map keys on resolved paths.

## result

**Halt: F017 is open and needs a decision.**
- A session turn is a resume, and a resume rebuilds the run's Views and counts by reading the whole record, so turn N costs O(N).
- Measured on a deterministic session over HTTP, 300 turns, 5,420 events, 5.2 MB: turns 0–10 took 15.5 ms each, 190–200 took 351 ms, 290–300 took 310 ms.
- A profile of turn 200 found three full passes over the record (0.78 s of 0.83 s), each verifying every frame's CRC by reserializing it as canonical JSON:
  - `SessionRegistry._record_state`;
  - `recover_open_segment`;
  - the resume fold.
- Now one pass does all three: `record.recover_and_read`; the registry reads only the first frame; deeper damage surfaces from the resume and maps to `TornRecordOnResume` as before. Turns 190–200 take 186 ms and 290–300 take 114 ms.
- The growth is still linear. Removing it needs one of two designs, and that choice is the Architect's:
  - Views that can be snapshotted at a pause and restored, which means a serialization contract on every View;
  - a session runtime that stays alive and paused between turns instead of finishing and resuming, which changes the daemon's process model.

**Liveness and the budget (F014, F021, F024).**
- F014 closed in K258: a Producer's own TimeoutError is an ordinary failure.
- F021: `quiescence_with_watchdog(seconds)` had no watchdog. `seconds` only capped a 10 ms poll, so every value of 0.01 or more did nothing. It is now `quiescence()`.
  - 116 call sites changed. The dead `watchdog_seconds` parameter left 13 topology factories, their callers, two application manifests and the console. The value was never read, so behaviour is identical.
  - A deadline on one Producer is `Budget(wall_seconds=...)`.
- F024: `Budget.event_counts` is enforced. The emission that would pass a kind's cap is not recorded, and the Producer fails with `budget_exceeded: {axis: "event_counts", kind, limit, reason}`. Before, the cap was stored and a UserWarning said so.
- F023: the Budget and Cap docs name the real record, a ProducerFailed with `budget_exceeded`. The `substrate.BudgetExceeded` kind they named never existed.

**Correct answers from the runtime (F016, F018, F027, F028).**
- `cancel_producer` returns the instance's real parent, from a `parent_by_instance` map kept beside `kind_by_instance`.
- The active-runtime map keys on the resolved path, so `find_active_runtime("rec")` and the absolute spelling find the same run.
- `TermContext.resume_condition`, which nothing set or read, is gone.
- A factory that raises when built is refused at registration with a RegistrationError naming the kind. It used to be swallowed, silently dropping an embedded substrate's export map.

**One copy of each rule (F022, F025, F026, F032, F033, F037).**
- `Subscription.matches(event)` is the one subscription rule, and `Event.from_envelope` the one converter. The sequencer, the resume fold and inspect each kept a copy.
- `RunFailureReason` (StrEnum) holds the three run-failure reasons; the sequencer, the runtime and graph use it.
- RunPhase's outcome members take their strings from RunStatus.
- F025 closed in K258, when `LiveRecord` moved into the record layer.
- F032 closed in K250, with `INITIAL_TRIGGER_ID`.
- F026: the composition comment says the inner root is required, as the code does.

**Found on the way.**
- `docs/api.md` had drifted: 31 public names missing, and 4 that K258 moved to `substrate.app` still listed. Its generator refuses a mismatch, but nothing ran it. The groups are fixed, the page regenerated, and `tests/test_api_docs_cover_the_surface.py` fails when the committed page differs from a fresh one.
- `scripts/gen_topology_records.py` wrote each record to `topologies/<key>/`. The `pair_coding` key was renamed, so an earlier run had committed a stray `pair_coding_chunked/` copy, and the real record went stale. The generator now asks `bundled.record_path`. The stray copy is deleted, and all 18 bundled records are regenerated.

**Tests.**
- `tests/test_runtime_liveness_251.py` has 7 tests. The four behavioural ones fail on 0758514f for their own finding:
  - the parent comes back None;
  - the relative root is not found;
  - all three ticks are recorded;
  - the raising factory is not refused.
- The torn-record test in the UI suite now damages a real record: a sealed segment cut mid-frame. It fails when `turn_sync`'s new mapping is removed. It used to monkeypatch `read_record`.

**Gates.**

| Gate | Result |
|---|---|
| kernel ruff, format, mypy --strict (138 files), lint-imports (2 contracts) | clean |
| UI suite | 210 passed |
| kernel deterministic suite (`-m "not realmodel"`) | 1,279 passed, 4 skipped, 43 deselected |
| vm_smoke, resume_ended_session, lifecycle gates | pass |
