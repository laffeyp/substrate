# Sprint 304 — Measure library v0

```yaml
---
id: 304
status: open
phase: 1
pass_kind: research
roadmap: process/planning/ROADMAP-2026-10-12-language-measurement-r3.md
depends_on: [302, 303]
context_files:
  - process/planning/RESEARCH-2026-10-10-language-metrics-r4.md
---
```

## scope

`src/substrate/language/`: `substrate-text-1` as code, and every form, lexicon, relation, padding and register measure as a pure function implemented to its published definition. Cross-checks, as test-only dependencies: MATTR, MTLD and HD-D against lexicalrichness (and koRpus or quanteda where reachable); readability against textstat; DFA against nolds or MFDFA; Zipf and Heaps fits against the powerlaw package's estimators; NCD and LSM against their papers' formulas.

## observation contract

- The tokenizer reproduces every K302 fixture, and tokenizes every K303 lexicon entry to itself.
- Each measure equals a hand-computed value on a small text, and agrees with its reference implementation on the fixture set within a stated tolerance, or the difference is traced (for example, to a tokenizer difference K302 recorded).
- A table: measure, source, reference implementation, agreement found.
- One 1,500-token text measures in under 5 ms.

## checks

New tests; kernel suite; ruff, mypy --strict, lint-imports.
