# Sprint 313 — The language view

```yaml
---
id: 313
status: open
phase: 1
pass_kind: functional
depends_on: [312]
roadmap: ../substrate-ui/process/planning/ROADMAP-2026-10-13-language-in-the-app.md
---
```

## scope

`app.language_view(record)`: the lines of `language_lines`, plus for the `user` and `model` streams and each watched measure: the warm-up state (the index where the detector's warm-up ended, or none), its mean and SD, each value in those SDs, and the shifts from the record's `LanguageDrift` events. The detector's arithmetic stays in `substrate.language.drift`.

## observation contract

On a built record of 26 turns with a jump: warm-up ends where `PageHinkley` scales; each deviation equals (value − mean) / SD of the warm-up values; the shifts equal the record's `LanguageDrift` events; a record without language events still returns lines and warm-up states.
