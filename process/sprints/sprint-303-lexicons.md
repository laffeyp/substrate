# Sprint 303 — Lexicons v1

```yaml
---
id: 303
status: closed
closed_at: 2026-10-13
phase: 1
pass_kind: research
roadmap: process/planning/ROADMAP-2026-10-12-language-measurement-r3.md
context_files:
  - process/planning/RESEARCH-2026-10-10-language-metrics-r4.md
  - skills/dellm/SKILL.md
---
```

## scope

None of round 4's word lists exist in the repository. This card builds them, each as one versioned file under `src/substrate/language/lexicons/` naming its source, licence, version and how it was built: Kobak's 291 style words (the paper's supplement); hedges and boosters (Hyland's lists, or an open equivalent); intensifiers; padding phrases (restatement openers, background lead-ins, closing summaries, offers of more), from the guidance texts and published catalogues; address words; contractions and slang; exclamation and enthusiasm words; an open function-word list and an LSM category schema. Entries are written in `substrate-text-1`'s token form.

## observation contract

Each file loads, its entries tokenize to themselves under K302's spec, and its header cites a source whose licence permits shipping it. A list built by Substrate says so.

## checks

A test loads every lexicon and checks the header fields and the token form.

## result

Revised 2026-10-13. The first version (`f1c1966c`) wrote Substrate's own boosters, intensifiers, address, informal, enthusiasm and function-word lists because Hyland's lists were in a book, lingmatch's are GPL and LIWC's are proprietary. The Architect: published word lists are research facts to implement, not something to rebuild. Every list a source has published now comes from that source.

| File | Entries | Source |
|---|---|---|
| `kobak_style_2024.toml` | 379 | Kobak et al. 2025: the 2024 excess words annotated "style"; rebuilt by `scripts/build_lexicon_kobak.py` from the authors' counts (commit `53db991a`, MIT notice in `licences/`) |
| `kobak_style_2024_rare.toml` | 291 | the same with 2024 frequency below 0.02: the paper's rare set, the 291 round 4 names |
| `hedges_hyland_2005.toml` | 97 | Hyland 2005, p. 218, as printed in Vázquez Orta & Giner 2008 (doi 10.14198/raei.2008.21.10); equal item for item to the copy in Liu, Salvi, Schoenegger et al. 2025 (arXiv 2505.09662) |
| `boosters_hyland_2005.toml` | 63 | Hyland 2005, p. 218, as printed in Vázquez Orta & Giner 2009 (doi 10.14198/raei.2009.22.14) |
| `hedges_ulinski_2019.toml` | 117 + 46 added forms | Ulinski & Hirschberg 2019, Table 1: hedges of informal text; the added inflections are kept apart |
| `amplifiers_alshaar_2017.toml` | 15 boosters, 8 maximizers | Alshaar 2017 (Quirk's amplifiers), as printed in arXiv 2505.09662 |
| `liwc2007.toml` | 22 categories | LIWC2007 English dictionary (4,487 entries, 64 categories), copied entry by entry by `scripts/build_lexicon_liwc2007.py`, which checks the file's SHA-256: the nine LSM categories of Ireland et al. 2011 with their formula, all function words (467), the five persons, tentative (156) and certainty (86) words, positive emotion (407), swear words, assent, nonfluencies, fillers |
| `padding.toml` | 4 categories, 69 phrases | Substrate: the categories are Substrate's own length control (restatement, background, offers of more) and dellm's summary closers; no published list measures them |
| `contractions.toml` | 6 suffixes, 15 words | the standard contraction forms, as a rule |

- **Replaced:** `boosters.toml` (by Hyland's), `intensifiers.toml` (by Alshaar's amplifiers), `function_words.toml`, `address.toml`, `informal.toml` and `enthusiasm.toml` (by LIWC2007's categories).
- **Two printing slips in Hyland's hedge list** are corrected and recorded in the file: "in my view in this view" is two items, and "rather x" (rather before an adjective) is entered as "rather". Hyland's "must (possibility)" is entered as "must".
- **LIWC wildcards.** LIWC entries ending in `*` match every token with that start (`anybod*`). The file declares `wildcard = "*"`; sprint 304's matcher honours it.
- **Stated limits, in each file.** Hyland's and Ulinski's items are candidates counted without reading context ("about", "would", "must"). Alshaar's "so", "right", "well" and "too" have many non-amplifier uses. Several words sit in more than one list; each list is counted on its own.
- **Tests** `tests/test_lexicons_303.py`, 23: header fields; every entry case-folded, without curly apostrophes, and made of W1 tokens (a trailing LIWC wildcard allowed); no repeats; the published counts (379, 291, 97, 63, 117, 15 and 8); the rare set inside the full set; the MIT notice; nine LSM categories present; LIWC's articles exactly `a, alot, an, the`. The token-form test caught two doubled spaces in the Hyland transcription ("certain   level").
