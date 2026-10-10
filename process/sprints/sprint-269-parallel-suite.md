# Sprint 269 — The suite runs in parallel

```yaml
---
id: 269
status: pending
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-09-session-topology-structure.md
asked: 2026-10-09 (Architect)
---
```

## why

The kernel suite runs one test at a time: about 6 minutes clean, up to 41 minutes on 2026-10-09 while failing real-model tests waited out guessed timeouts. `pytest-xdist` is not installed.

## scope

1. **Parallel.** Add `pytest-xdist` and run with `-n auto`. Isolate any test that shares state with another worker.
2. **Real-model tests.** Each runs on a model that can do its task. Its timeout is how long that task really takes on that model here, measured. A failed run is retried once before it counts, since one run of a stochastic system is one sample.

The tests check the same things they check now. The models, their options and their call timeouts do not change.

## checks

- A clean kernel run's wall time, serial against parallel.
- Each real-model timeout matches its measured duration.

## result

(filled at close)
