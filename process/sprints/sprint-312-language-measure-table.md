# Sprint 312 — The measure table

```yaml
---
id: 312
status: closed
closed_at: 2026-10-13
phase: 1
pass_kind: functional
roadmap: ../substrate-ui/process/planning/ROADMAP-2026-10-13-language-in-the-app.md
---
```

## scope

`substrate.language.catalog`: one entry per profile measure (74): short name, unit, group (`length`, `tone`, `guidance`, `other`), typical display range, two-sentence explanation. The intent table: for each length and tone position whose control text states a direction, the measures it names and the direction, citing the text (`vocabulary.LENGTH_TEXTS`, `TONE_TEXTS`). Normal and neutral write no text and state no intent.

## observation contract

A test fails if `profile()` returns a measure the catalog lacks, or the catalog names one `profile()` does not return; the 13 watched measures carry their groups; every intent entry names a position whose control text exists.

## result

- `substrate.language.catalog`: `CATALOG`, 74 `Measure` entries (short name, unit, `Family`, `Group`, display range, explanation); the 13 watched measures carry `length`, `tone` or `guidance`, every other `other`.
- `vocabulary.LANGUAGE_INTENTS`, beside the texts it reads: terse (words, restatement, background, offers of more ↓), full (words ↑), blunt (Hyland hedges ↓), formal (contractions ↓), dry (positive emotion, exclamation marks ↓). Normal and neutral state none.
- Found while writing the LIWC entries: LIWC2007 writes its multi-word fillers run together (`imean`, `youknow*`), so "I mean" and "you know" split into words never match; the fillers explanation says so.
- Tests `tests/test_language_catalog_312.py`, 4: the catalog names exactly the profile measures; the watched measures carry exactly their groups; every entry is complete with one or two sentences; every intent names a position with a control text and a catalogued measure. The sentence check caught "Kobak et al. (2025)" splitting as a sentence; the entries read "Kobak and colleagues".
