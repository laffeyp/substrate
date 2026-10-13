# Sprint 303 — Lexicons v1

```yaml
---
id: 303
status: open
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
