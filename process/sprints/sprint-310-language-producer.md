# Sprint 310 — The language producer in the turn

```yaml
---
id: 310
status: closed
closed_at: 2026-10-13
phase: 1
pass_kind: functional
depends_on: [309]
vocabulary: process/signals/session-vocabulary.md § W.1, W.3–W.6
---
```

## scope

`session_topology(language=True)` registers the `language` producer and `language-on-reply` / `return-on-language`, and narrows `return-on-reply` to `language` off. The producer reads the turn by its seq range (`api.read_range`), emits the turn's `LanguageProfile` events, runs `drift.PageHinkley` with `DEFAULT_DRIFT` over each watched measure's series of user messages and final replies, and emits a `LanguageDrift` for an alarm on the newest value.

## observation contract

Tests written first and red on the current code:
- a two-turn session with `language=True`: the record order of § W.5; each `LanguageProfile`'s measures equal the command's `values.text` (and relation values) for the same text; `Returned` comes after the last language event;
- `language=False`: the record is v0.10's, no language event;
- a measurement that raises still returns the turn, with `ProducerFailed` on the record;
- a session whose replies jump in length after 20 turns records a `LanguageDrift` on `words`, up, at the jump's reply;
- a turn ending in a model error records no language event and returns.

## result

- **Built.** `topologies/session/language_producer.py`: `language_input` (the trigger's input, three seqs, one home for its keys) and `language_producer_factory`. The producer reads the turn by `api.read_range` and decodes the events with `msgspec.convert` into `UserMessage`, `ModelReply` and `LanguageProfile`; it emits the user (or delegate) profile, one per reply, the two relation profiles, then a `LanguageDrift` per watched measure that alarms on the newest value of the user or final-reply series. `session_topology(language=True)` registers it with `language-on-reply` and `return-on-language`, and `return-on-reply` fires only with `language` off. A turn's record: final `ModelReply`, `language-on-reply`, the profiles, any drifts, `return-on-language`, `Returned`.
- **Shared with the command.** `turn_pairings` (now taking (text, stop reason) pairs) and `relation_values` live in `language_lines.py`; both the command and the producer call them, so a live relation value equals the command's.
- **Typed results.** `profile()` returns a `Profile` (with an `Instrument` and its `sha256`) instead of a dict, so no caller retypes `"measures"` or `"instrument_sha256"`; `lexicon.LIWC2007` and `lexicon.CONTRACTIONS` name the two lexicons read in more than one module.
- **The warm-up waits for spread.** The 26-turn test showed `rate_kobak_style`, 0 for twenty replies, raising a drift of 9.6 × 10¹³ (the warm-up SD was 0 and the detector divided by 10⁻¹²). The warm-up now runs on until its values vary, as phase I of a control chart needs an estimable variance; `warmup_scale` returns None for a series that never varies. Library 0.2.1. Test added to `test_language_drift_305.py`.
- **Tests** `tests/test_language_producer_310.py`, 6, red first (`session_topology` had no `language`): the turn's order and that only `return-on-language` returns it; live values equal the command's for every profile; `language=False` records none; a measurement that raises still returns the turn with `ProducerFailed`; a jump in reply length at turn 22 records `LanguageDrift(words, up)` at that reply; a model-error turn records none. With `return-on-reply` left on beside the measurement the first version of the order test still passed, because the language producer happened to finish first; the test now asserts which trigger fired, and the same change fails it.
- **Checks.** Kernel suite 1,668 passed, 14 skipped, 2 failed: `test_trigger_names_264` built its session with `language` off, so the declared triggers outnumbered the registered ones (now built with `language=True`, passes); `test_realmodel_tool_comprehension::test_inspect_record_summary_read_back_by_model`, llama3.2:1b dropping `/seeded` from the path, as before this card. All 77 recorded sessions still measure (1,480 lines). ruff, mypy --strict (148 files), lint-imports clean.
