# Sprint 301 — The length experiment's switch arms, run again on the fixed kernel

```yaml
---
id: 301
status: open
phase: 1
pass_kind: research
roadmap: process/planning/ROADMAP-2026-10-12-changes-on-time.md
context_files:
  - scripts/assay_length_drift.py
  - process/planning/RESEARCH-2026-10-12-length-drift-r2.md
---
```

## scope

The 2026-10-12 run's `n2t@2`, `n2t@5` and `t2n@5` arms delivered each change a turn late. After K299, the five arms run again (`process/runs/assays/length_drift_<date>/`), and research round 3 reads them, keeping round 2's correction that word count measures content as well as padding.

## observation contract

Before the run, one session's record is read to confirm the prompt for the turn after the change holds the new text. Round 3 written from the new data.
