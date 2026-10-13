# Sprint 305 — The drift detector

```yaml
---
id: 305
status: open
phase: 1
pass_kind: research
roadmap: process/planning/ROADMAP-2026-10-12-language-measurement-r3.md
depends_on: [304]
context_files:
  - process/planning/RESEARCH-2026-10-10-language-metrics-r4.md
---
```

## scope

Page–Hinkley as Hinkley (1971) and its standard modern statement define it: both directions, warm-up and reset. Its defaults for δ, λ and warm-up come from synthetic series, not from sessions.

## observation contract

On synthetic series, a table of false-alarm rate (no change), detection delay (planted steps of known size) and the behaviour on slow drift, against δ and λ. The chosen defaults are read from that table and stored as parameters.

## checks

Tests on series with a known answer; ruff, mypy --strict.
