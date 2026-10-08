# Sprint 251 — Runtime liveness

```yaml
---
id: 251
status: open
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

(filled at close)
