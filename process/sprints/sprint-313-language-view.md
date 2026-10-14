# Sprint 313 — The language view

```yaml
---
id: 313
status: closed
closed_at: 2026-10-13
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

## result

- `topologies/session/language_view.py`, `app.language_view(record)`: `lines` (as `substrate language`), `lanes` (user and model stream × the 13 watched measures: `warmup_span`, `warmup_end_seq`, `mean`, `sd`, and per point `seq`, `turn`, `value`, `window`, `deviation`), `shifts` (each `LanguageDrift` with its turn), `changes` (each `SessionChanged` with the turn it applies to), `warmup`, `last_seq` (the cache key). The model series is each turn's final reply, as the live detector's.
- `drift.warmup_span` reports how many values the warm-up took (20, or more until they vary); `warmup_scale` uses it, so the view and the detector share one rule.
- A count's window (words, tokens, sentences, paragraphs; `Measure.count` in the catalog) is divided by the texts in the window: the first draft returned the window's total words (168 on a two-turn session), a line that would climb toward 3,200 regardless of the replies.
- Tests `tests/test_language_view_313.py`, 4, on a 26-turn built record with a length change and a jump at turn 22: warm-up span, mean, SD and every deviation; shifts equal the record's `LanguageDrift` events, `words` up at turn 22; the length change at turn 22; a count's window per text (fails without the division); a record without language events still returns lanes.
