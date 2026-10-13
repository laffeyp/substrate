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

Eleven lexicons in `src/substrate/language/lexicons/`, each a TOML file whose `[lexicon]` table names the source, licence, construction and `substrate-text-1`:

| File | Entries | Source | Licence |
|---|---|---|---|
| `kobak_style_2024.toml` | 379 words | Kobak et al. 2025: the 2024 excess words the authors annotated "style" | MIT, notice in `licences/` |
| `kobak_style_2024_rare.toml` | 291 words | the same, 2024 frequency below 0.02: the paper's rare set (figure S6), the 291 round 4 names | MIT |
| `hedges.toml` | 52 relational + 65 propositional, 46 added forms | Ulinski & Hirschberg 2019, Table 1 (117, the paper's count); added inflections are Substrate's and kept apart | CC BY 4.0 (ACL Anthology, 2016 on) |
| `boosters.toml` | 36 | Substrate, after Hyland's (2005) category; Hyland's list not reproduced | Substrate |
| `intensifiers.toml` | 40 | Substrate, after Quirk et al. (1985) amplifiers | Substrate |
| `padding.toml` | 4 categories, 69 phrases | Substrate: restatement, background, closing summary, offer of more (the terse text's three, plus dellm's summary closers) | Substrate |
| `address.toml` | 3 categories, 29 forms | the English pronoun paradigm | Substrate |
| `contractions.toml` | 6 suffixes, 15 words | standard contraction forms; `'s` only after listed pronouns, since it is also the possessive | Substrate |
| `informal.toml` | 38 | Substrate | Substrate |
| `enthusiasm.toml` | 26 words, 20 phrases | Substrate | Substrate |
| `function_words.toml` | 9 categories, 320 entries, and the LSM formula | categories and formula from Ireland et al. 2011 (Table 1, p. 40, LIWC2007); words enumerated by Substrate | Substrate |

- **Kobak, rebuilt and checked.** `scripts/build_lexicon_kobak.py` repeats the authors' selection (`03-figures.ipynb`, commit `53db991a`) in plain Python on their `yearly-counts.csv.gz` and `excess_words.csv`, records both files' SHA-256, and refuses to write unless it gets 379 and 291. Both lists equal the notebook's saved output word for word. Round 4's "291 style words" is the rare subset; the paper's full 2024 style set is 379.
- **What was not used, and why.** Hyland's hedge and booster lists are in a copyrighted book with no open copy. lingmatch's LIWC-style function-word lists are GPL-2+, which Substrate's licence cannot ship. LIWC's dictionaries are proprietary. Substrate's LSM values therefore do not equal LIWC-based LSM, and `function_words.toml` says so.
- **Stated limits, in each file.** The hedge terms are candidates: the paper found some used as hedges in under 10% of occurrences (`about`, `like`, `read`). Padding phrases depend on position; sprint 304 defines where each category counts. Several words sit in two lexicons (`really`: hedge; `truly`: booster and intensifier); each lexicon is counted on its own.
- **Tests** `tests/test_lexicons_303.py`, 27: each file has the eight header fields; every entry is case-folded, has no curly apostrophe, and splits into tokens that match rule W1; no list repeats an entry; the published counts hold (379, 291, 117); the rare set sits inside the full set; the MIT notice ships; the LSM table names nine categories that exist. Red first on 11 cases (lists outside their tables, no Kobak `construction`), green after. W1 is restated as a regex because the tokenizer does not exist yet; sprint 304 tokenizes every entry with the real one.
