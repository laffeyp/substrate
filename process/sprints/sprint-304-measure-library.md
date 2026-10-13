# Sprint 304 — Measure library v0

```yaml
---
id: 304
status: closed
closed_at: 2026-10-13
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

## result

- **Built.** `src/substrate/language/`: `text.py` (substrate-text-1: `parse` → tokens, sentences, units, format counts; `words`), `lexicon.py` (loader; `Matcher`, longest term first without overlaps, LIWC wildcards; `LexiconIndex`, one pass for all lists; contractions), `measures.py` (rhythm, TTR, MATTR, MTLD, HD-D, Zipf, Heaps, entropy, compression ratio, repeated n-grams, burstiness, DFA, format rates, syllables, Flesch and Flesch–Kincaid), `relation.py` (length ratio, lexical echo, phrase copy, NCD, LSM, profile difference, lagged correlation), `profile.py` (every one-text measure with its `Params`, library version, preprocessing, lexicon versions, compressor, and the mergeable partials). `lexicons/syllables_cmudict.tsv.gz` (126,052 words, by `scripts/build_syllables_cmudict.py`).
- **Agreement** (`docs/language/measures.md`): MATTR, MTLD and HD-D equal lexicalrichness 0.5.1 on the same tokens over 600 replies (largest difference 8.4e-15); the Zipf fit equals powerlaw 2.0.0 (8.9e-16); DFA equals nolds 0.6.3 on white noise, a random walk and 14,531 real sentence lengths (≤ 1e-9); the syllable table equals the cmudict package word for word. Against textstat 0.7.13 (`scripts/language_crosscheck_textstat.py`): syllables agree on 123,208 of the 123,328 words both dictionaries hold (textstat reads NLTK's older edition); Flesch differs by a median of −0.92 points because the tokenizers differ, the formula being the same.
- **Speed.** 4.1 ms median for a real 1,821-token text, 4.3 ms for 1,626 tokens with code and tables. The first build took 30.8 ms: 38 lexicon lists each scanned every token. `LexiconIndex` looks each word type up once and was checked equal to the per-list matcher on 200 replies.
- **Tests** `tests/test_language_measures_304.py`, 85: 62 fixtures; every entry of every lexicon tokenizes to itself; each measure by hand; the four reference cross-checks; the profile's provenance; all 600 replies profile; the 5 ms bound. Breaking MTLD's `≤` or DFA's detrending each fails a reference test. Two of my first test cases were wrong and were replaced: a random-text burstiness bound I had chosen, and a guess that LIWC does not list "nobody" as an impersonal pronoun.
- **Dependencies.** lexicalrichness, nolds, powerlaw and cmudict added to `dev` for the tests; the library imports none of them. textstat stays out: its wheel installs a top-level `tests` package that broke `import tests._sandbox` in 8 test modules; the comparison script runs it with `uv run --with textstat==0.7.13`.
- **Checks.** ruff, mypy --strict (145 files), lint-imports (2 kept). Kernel suite: 1,639 passed, 13 skipped, 1 failed: `test_realmodel_tool_comprehension::test_inspect_record_summary_read_back_by_model`. llama3.2:1b called `inspect_record` on the parent folder of the path in the prompt (it dropped `/seeded`), got the tool's "no record" error, and answered without a second call; the same in two runs. BLACKBOARD F-5 lists this file's 1B-model tests; K304 changes no session or tool code.
