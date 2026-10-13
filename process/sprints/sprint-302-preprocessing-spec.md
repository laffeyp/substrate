# Sprint 302 — Preprocessing spec `substrate-text-1`

```yaml
---
id: 302
status: closed
closed_at: 2026-10-12
phase: 1
pass_kind: research
asked: 2026-10-12 (Architect: "card out and begin the first one")
roadmap: process/planning/ROADMAP-2026-10-12-language-measurement-r3.md
context_files:
  - process/planning/RESEARCH-2026-10-10-language-metrics-r4.md
---
```

## scope

Every measure starts from the same split of a text into words and sentences, and round 4 requires that split to have a versioned name. This card decides it: Unicode normalization, case folding, the word tokenizer (apostrophes, contractions, hyphens, URLs, numbers, emoji), the sentence splitter (abbreviations, decimals, list items, headings), markdown stripping, and code (fenced and inline code out of the prose measures, counted in format). Each choice is compared with what the published implementations the library will be checked against do (quanteda, koRpus, lexicalrichness, textstat), and each difference is written down.

## observation contract

- `docs/language/substrate-text-1.md`: each decision, the reason, the conventions of the reference packages, and where Substrate differs.
- `tests/fixtures/language/substrate-text-1.json`: synthetic cases for each rule, and real texts from the 77 recorded sessions and the length-experiment replies (markdown, code, lists, one-line and long texts), each with its expected prose text, tokens and sentences, written by hand from the spec before any code exists.

## checks

Every rule in the spec has at least one fixture; every fixture names the rule it tests.

## result

- `docs/language/substrate-text-1.md`: 22 rules. Normalization (NFC; curly apostrophes, non-breaking hyphens and spaces read as ASCII for tokenizing only; casefold for words, not for code, URL or email tokens). Blocks after CommonMark: fenced code out, headings and table cells give tokens but no sentences, soft line breaks join and hard breaks end a sentence. Inline code spans are one opaque token. Words keep internal apostrophes, hyphens and periods, and commas between digits. Sentences end on `.!?…` with closers; a `.` after a single letter or 14 listed abbreviations does not end one; a lowercase letter after `.` does not stop the split.
- References read: lexicalrichness 0.5.1 and textstat 0.7.13 source (downloaded wheels), quanteda's `tokens()` and koRpus's `tokenize()` reference pages, UAX #29 revision 49. The spec's table records each difference: lexicalrichness deletes digits and hyphens and splits `don't`; textstat deletes hyphens and the curly apostrophe (`don’t` → `dont`), splits sentences on every `.` and does not count sentences of two words or fewer; quanteda keeps punctuation as tokens by default. koRpus's case, digit, punctuation and URL handling is not stated on its page and is marked so.
- `tests/fixtures/language/substrate-text-1.json`: 54 synthetic cases and 8 real texts (7 from recorded sessions, 2 of them user messages, and 1 paragraph from the length experiment), each naming its source; written by hand before any code. Every rule has at least one case.
- The four known costs of the rules (`Plan A.` does not split, `__init__` outside backticks becomes `init`, indented code reads as text, a sentence ending in `e.g.` joins the next) each have a fixture, so a later version that changes them shows up.
