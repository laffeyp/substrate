# Sprint 309 — Vocabulary v0.11: language measured live

```yaml
---
id: 309
status: closed
closed_at: 2026-10-13
phase: 1
pass_kind: functional
asked: 2026-10-13 (Architect: "go… make sure we have the right design"; in the turn: "as long as it's in that millisecond range… completely fine putting it inside the turn")
vocabulary: process/signals/session-vocabulary.md § W
research: process/planning/RESEARCH-2026-10-13-language-metrics-r5.md
---
```

## scope

§ W as types: `LANGUAGE_PROFILE`, `LANGUAGE_DRIFT`, `PRODUCER_KIND_LANGUAGE`, `TRIGGER_ID_LANGUAGE_ON_REPLY`, `TRIGGER_ID_RETURN_ON_LANGUAGE` and `LanguageStream`, `LanguagePairing` in the session vocabulary (the command's `Stream` and `Pairing` move there); the `LanguageProfile` and `LanguageDrift` Structs; `profile()` returns `instrument_sha256`; `drift.WATCHED` names the measures the detector watches.

## observation contract

The constants are in the vocabulary's sets and `__all__`; the Structs encode and decode a profile and a drift; `instrument_sha256` changes when a parameter changes and not otherwise; the command's lines carry the same `instrument_sha256` as `profile()`.

## result

- **Built.** Session vocabulary v0.11 § W (`process/signals/session-vocabulary.md`). In `vocabulary.py`: `LANGUAGE_PROFILE`, `LANGUAGE_DRIFT` (also in `SESSION_KINDS`), `PRODUCER_KIND_LANGUAGE` (in `SESSION_PRODUCER_KINDS`), `TRIGGER_ID_LANGUAGE_ON_REPLY`, `TRIGGER_ID_RETURN_ON_LANGUAGE` (in `SESSION_TRIGGER_IDS`), `LanguageStream`, `LanguagePairing`. In the session package: the `LanguageProfile` and `LanguageDrift` Structs. `profile()` returns `instrument_sha256`; `drift.WATCHED` names 13 measures. The command's `Stream` and `Pairing` are now the vocabulary's enums, and its lines carry `instrument_sha256`.
- **Tests** `tests/test_language_vocabulary_309.py`, 5, red first (the types did not import): the constants and their sets; both events encode and decode; the digest is the same for two texts and changes with `mattr_window`; the watched measures are profile measures; the CI record's command lines carry `profile()`'s digest. The three exact-set guards (`SESSION_KINDS` against the package's Structs, the producer kinds, the 20 trigger ids) failed until the new members were listed, as they are meant to. 254 vocabulary, session and language tests pass; ruff, mypy --strict, lint-imports clean.
