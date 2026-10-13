# Sprint 312 — The measure table

```yaml
---
id: 312
status: open
phase: 1
pass_kind: functional
roadmap: ../substrate-ui/process/planning/ROADMAP-2026-10-13-language-in-the-app.md
---
```

## scope

`substrate.language.catalog`: one entry per profile measure (74): short name, unit, group (`length`, `tone`, `guidance`, `other`), typical display range, two-sentence explanation. The intent table: for each length and tone position whose control text states a direction, the measures it names and the direction, citing the text (`vocabulary.LENGTH_TEXTS`, `TONE_TEXTS`). Normal and neutral write no text and state no intent.

## observation contract

A test fails if `profile()` returns a measure the catalog lacks, or the catalog names one `profile()` does not return; the 13 watched measures carry their groups; every intent entry names a position whose control text exists.
