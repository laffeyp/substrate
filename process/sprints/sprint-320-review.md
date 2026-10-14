# Sprint 320 — Review

```yaml
---
id: 320
status: open
phase: 2
pass_kind: functional
depends_on: [317, 319]
roadmap: process/planning/ROADMAP-2026-10-13-core-topologies.md
---
```

## scope

A one-shot run that reviews a branch, a commit range or files in a named style and returns a report per reviewer; the styles are texts, picked from well-known review styles in published practice as part of this card (r8 § 4.3). Replaces the `code_review` application.

## observation contract

A deterministic reviewer on a fixture branch returns its report in the caller's record; two styles run in parallel and return two reports; the style set and its sources are written down.
