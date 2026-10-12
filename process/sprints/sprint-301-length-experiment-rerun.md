# Sprint 301 — The length experiment's switch arms, run again on the fixed kernel

```yaml
---
id: 301
status: closed
closed_at: 2026-10-12
phase: 1
pass_kind: research
roadmap: process/planning/ROADMAP-2026-10-12-changes-on-time-r2.md
context_files:
  - scripts/assay_length_drift.py
  - process/planning/RESEARCH-2026-10-12-length-drift-r2.md
---
```

## scope

The 2026-10-12 run's `n2t@2`, `n2t@5` and `t2n@5` arms delivered each change a turn late. After K299, the five arms run again (`process/runs/assays/length_drift_<date>/`), and research round 3 reads them, keeping round 2's correction that word count measures content as well as padding.

## observation contract

Before the run, one session's record is read to confirm the prompt for the turn after the change holds the new text. Round 3 written from the new data.

## result

- Ran on the fixed kernel (`6d2d5114`): 60 sessions, 600 turns, none failed; data in `process/runs/assays/length_drift_2026-10-12_k299/`. Delivery was checked before the run by K300's tests and U167's gate and live check, not by reading one of this run's records (its records sit in a temporary folder the script removes).
- `RESEARCH-2026-10-12-length-drift-r3.md`: glm 0.95–1.05 of normal in every arm; kimi terse 0.93, normal→terse at turn 2 0.82, at turn 5 0.90; no drift back visible; a change to normal on kimi stayed at 0.92.
