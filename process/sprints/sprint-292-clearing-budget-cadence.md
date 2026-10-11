# Sprint 292 — Clearing, budget, cadence

```yaml
---
id: 292
status: open
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-11-compaction.md
asked: 2026-10-11 (Architect)
---
```

## scope

- In `transcript.py` and the model step: clear tool-output bodies beyond the newest K behind a placeholder; keep user messages and final replies; drop whole turns only when those exceed the budget; apply the rule inside the current turn; scale the estimate by the driver's recorded usage ratio; set CLI windows per model; clear in batches; record an event only when the cut changes. First confirm whether a session's model can read its own record by seq through `inspect_record`; the placeholder names a read-back path only if one works.

## checks

- Unit tests for the plan; replaying a recorded session gives byte-identical prompts; replanning `s_b8dab6b0cfd443cdba9bc8b3` keeps all four user messages and replies inside the budget.

## result

