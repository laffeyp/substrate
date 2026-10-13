# Sprint 308 — A command that measures a session record

```yaml
---
id: 308
status: closed
closed_at: 2026-10-13
phase: 1
pass_kind: functional
roadmap: process/planning/ROADMAP-2026-10-12-language-measurement-r3.md
research: process/planning/RESEARCH-2026-10-13-language-metrics-r5.md
context_files:
  - src/substrate/language/
  - src/substrate/projections/narrate.py
  - src/substrate/api.py
  - src/substrate/cli.py
---
```

## scope

`substrate language <record> [--out FILE]` reads a session record and writes one JSON line per measured text, adding nothing to the record. A read-only projection beside `narrate` and `inspect`: `projections/language.py` builds the lines, `api.language_lines` exposes them, the CLI writes them.

Streams, one line each:
- `user`: each `UserMessage`; a message with `slash_source="delegate"` (written by a parent model) is stream `delegate`.
- `model`: each `ModelReply`.
- `relation`: each turn twice, pairing `final` (the user's text with the turn's last `end_turn` or `wrap_up` reply, or its last reply) and `turn` (all its replies joined in order).
- `composed`: each `PromptComposed`, its `.text` and `.system` measured apart.

Every line carries round 4's grouping keys as the record holds them at that seq (session id, seq, t, stream, turn, step, stop reason, slash source, driver model, model class, bundle, length and tone after any `SessionChanged`, the SHA-256 of the latest composed system text, workspace shape, topology), the library's provenance (version, preprocessing, parameters, minimums, lexicons, compressor), `values` and, for user and model lines, the mergeable `partials`.

`values.text` holds the text's own measures; for user and model lines `values.window` holds the same measures over the trailing window of that stream: the latest texts joined, back until 3,200 words (the largest one-text minimum) or the record's start, with its word and text counts. Relation lines add LSM over the trailing user and model windows.

Lines are canonical JSON (sorted keys, no NaN), so two runs give the same bytes.

## observation contract

- Every recorded session under `~/.substrate/sessions/` measures without error, and a second run reproduces every line byte for byte.
- On a built record with known text, each stream's lines, keys and values are checked by hand; a `SessionChanged` of length or tone shows on the lines after it.
- The 1,200 length-experiment replies profile without error.

## checks

New tests; the language and CLI tests; ruff, mypy --strict, lint-imports.

## result

- **Built.** `topologies/session/language_lines.py` (`language_lines`, `line_json`, `Stream`, `Pairing`), exported through `app`; `substrate language <record> [--out FILE]` in the CLI. The projection sits beside the session vocabulary because it reads session events by their vocabulary names (`USER_MESSAGE`, `MODEL_REPLY`, `PROMPT_COMPOSED`, `SESSION_STARTED`, `SESSION_CHANGED`, `SESSION_CHANGE_FIELDS`, `StopReason`, `constants.RUN_STARTED`); `api` sits below the topologies and could not import them.
- **Every recorded session measures.** All 77 records under `~/.substrate/sessions/`: 1,480 lines (305 user, 307 model, 538 relation, 330 composed) in 7.5 s, no errors; a second run gives the same bytes for every record. 40 records first failed: 113 replies written before `ModelReply` carried `step`, `stop_reason` and `usage` hold `text`, `turn_index` and `model_usage`; the projection reads those fields as recorded, and a turn with no recorded stop reason pairs its last reply as final.
- **Line contents.** Grouping keys as of the line's seq (session, seq, t, stream, turn, step, stop reason, slash source, reply model, driver model, model class, workspace shape, topology, the SHA-256 of the latest composed system text, and every `SessionChanged` field as `setting_*`); provenance (library, preprocessing, parameters, minimums, lexicons, compressor) on every line; `values.text`, and for user and model lines `values.window` over the trailing 3,200 words of that stream with its word and text counts; `partials` for user and model lines. Relation lines carry their keys as they stood at the turn's last reply, and add LSM over the trailing user and model windows.
- **Also.** `DELEGATE_SLASH_SOURCE` added to the session vocabulary; `delegate.py`'s two `slash_source="delegate"` literals use it.
- **Tests** `tests/test_language_lines_308.py`, 8, on a record built with a scripted driver: stream order; hand-counted words, window sizes and length ratio; a length change shows on the reply after it and not on the message before it; a delegate message is its own stream and stays out of the user window; provenance and keys on every line; the record's bytes unchanged and two runs identical; the CLI writes the same lines; the 1,200 experiment replies profile. Removing the `SessionChanged` handling fails the length-change test. ruff, mypy --strict (147 files), lint-imports (2 kept); 294 delegate, session and CLI tests pass.
