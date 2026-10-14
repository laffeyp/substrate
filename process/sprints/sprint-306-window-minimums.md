# Sprint 306 — Window minimums

```yaml
---
id: 306
status: closed
closed_at: 2026-10-13
phase: 1
pass_kind: research
roadmap: process/planning/ROADMAP-2026-10-12-language-measurement-r3.md
depends_on: [304]
context_files:
  - process/planning/RESEARCH-2026-10-10-language-metrics-r4.md
---
```

## scope

Round 4's window table marks several minimums "working value". Each gets a value derived from the measure's definition or measured on synthetic text: for example, the length at which zlib's fixed overhead stops dominating the compression ratio, and the length at which MTLD's factor count settles on shuffled text.

## observation contract

The window table with every minimum sourced, defined or measured, and the script that measured it in the repository.

## result

- **Measured** (`scripts/language_window_minimums.py`, `docs/language/windows.md`) by a criterion fixed in the script first: within 5% (or 0.05) of the reference and spread at most 10% (or 0.05). Heaps beta 800 words; LSM 1,600 words per text; entropy and Zipf alpha 3,200 words; DFA alpha 400 sentences (white noise); burstiness 20 occurrences per word (random gaps). Compression ratio has none on the grid (0.359 at 3,200 words, 0.326 at 6,400): it is compared only at equal lengths. MTLD keeps its sourced 100 words; MATTR and HD-D their definitional windows.
- **Applied.** `measures.MIN_*` hold the values; `profile` reports MTLD, entropy, Zipf, Heaps and DFA as None below them, `relation.lsm` returns None when either text is under 1,600 words, and the burstiness default moved from 5 to 20 occurrences. Library 0.1.0 → 0.2.0, since stored values change; `measures.md` stays as the 0.1.0 record.
- **The rule they set** (`docs/language/windows-r2.md`): each measure runs over a trailing window of one stream at least as long as its minimum, across session boundaries when needed; values are compared at equal window lengths, with the length stored beside them.
- **Tests** `tests/test_language_windows_306.py`, 4: one reply reports None for the long-window measures and a compression ratio; each measure appears at its minimum; LSM needs its minimum on both sides; a word with 19 occurrences gives no burstiness. The K304 by-hand LSM case now passes `min_words=0`. 117 language tests pass, 1 skipped (the opt-in timing bound); ruff, mypy --strict clean.

## pressure test (2026-10-13)

- **Red checked.** The four K306 tests, run against the code before K306 (`c5f955d3`) with the constants written in, fail on behaviour: entropy 7.08 where None is due, LSM 0.73 on a short text, burstiness counted at 19 occurrences.
- **Fixed: the profile did not name its minimums,** though they decide whether a value is a number or None. `measures.MINIMUMS` now goes into every profile beside `params`; a test checks it.
- **Where the minimums apply.** `profile` applies them to the one-text measures; `relation.lsm` applies its own, since no relation profile exists yet. Build card B1 puts both behind one call.
- K305 has no retyped direction strings (`Direction` throughout); its defaults and K306's minimums each have one home (`DEFAULT_DRIFT`, `measures.MIN_*`).
