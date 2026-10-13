# Sprint 310 — The language producer in the turn

```yaml
---
id: 310
status: open
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
