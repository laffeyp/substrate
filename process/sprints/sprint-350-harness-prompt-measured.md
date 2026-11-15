# Sprint 350 — A harness driver's prompt is counted by what the model reports

```yaml
---
id: 350
status: closed
closed_at: 2026-11-14
phase: continuing a session (substrate-ui roadmap 2026-11-12-continue-a-session r3, E8)
pass_kind: functional
depends_on: [348]
plan: ../substrate-ui/process/planning/2026-11-12-continue-a-session/ROADMAP-2026-11-14-continue-a-session-r3.md
---
```

## scope

The history window prices a prompt at four characters per token, corrected by `measured_scale` (reported over estimated prompt tokens, clamped 1–4, § S.5). For a harness driver the correction is fixed at 1.0 (`session/__init__.py` line 1119), because the harness reports one total for all its calls in a turn. Claude Code's stream reports each call's whole input on its `assistant` events (`message.usage`: `input_tokens` + `cache_creation_input_tokens` + `cache_read_input_tokens`). The parser keeps the first call's input; the reply's usage carries it as `first_call_prompt_tokens`; the history view scales a harness driver's estimate by it. A driver that reports no first call keeps 1.0. One verifiable property: a turn whose first call reports twice the estimate gives the next turn's window a scale of 2.0, and the window compacts sooner by that much.

## context_files

- `src/substrate/adapters/harness_streams.py` (the `claude-stream-json` parser, `StreamUsage`)
- `src/substrate/adapters/models.py` (`ModelUsage`)
- `src/substrate/topologies/session/__init__.py` (`_harness_stream`, `_prompt_input` line 1119)
- `src/substrate/topologies/session/views.py` (the history view's `_scale`)
- `process/signals/session-vocabulary.md` (§ S.5, § S.9)

## signal contract

### Emits

- `ModelReply.usage.first_call_prompt_tokens` (int, optional; a harness driver that reports its calls).

### Invariants

- A non-harness driver's scale is computed as before.
- A record without the field reads as before.

## artifact contract

### Files modified

- `harness_streams.py`, `models.py`, `session/__init__.py`, `views.py`, `session-vocabulary.md` (v0.20, § S.5 amended)

### Files created

- `tests/test_harness_prompt_measured_350.py`

### Command exit codes

- The new test and the stream, history and compaction tests return 0.

## observation contract

The parser fed a recorded-shape Claude Code stream (two `assistant` calls with usage, a closing `result`): `first_call_prompt_tokens` is the first call's input. A session on a harness stand-in whose first call reports twice the estimate: the next turn's `TranscriptCompacted` (or ticket) records scale 2.0, and the window drops turns it kept before. A run of the real `claude` through the parser: the first call's figure matches its `assistant` event.

## done criteria

The history window counts a Claude Code prompt as Claude counts it.

## notes

Five files for one concept: where the figure is read, carried, and used, and its vocabulary. The figure includes Claude Code's own system prompt and tools (17,679 tokens for a short prompt, measured), so the correction errs high: the window compacts a little early.

## self-review checklist

- [x] Scope is concrete and bounded.
- [x] Payload field by the vocabulary's next version.
- [x] Observation contract present.

## close

`harness_streams.py`: the Claude stream parser keeps the first `assistant` event's whole input and puts it on `StreamUsage.first_call_prompt_tokens`. `session/__init__.py`: the harness step carries it to the reply's usage (`_usage_of`, present only when reported) and a harness driver's history scale is `state.first_call_scale` (1.0 until a reply reports one). `views.py`: `TurnHistory` measures `first_call_scale` against the composed prompt's estimate. Session vocabulary v0.20, § AE. `models.py` unchanged: the field rides the reply's usage dict, as § S.9's `context_window` does.

- `tests/test_harness_prompt_measured_350.py`: 4 passed. The parser on the shape measured 2026-11-14 (first call 17,679, total 35,439); the reply's usage carries the field only when reported; the view's scale 2.0 from 2,000 over 1,000; a session on a stand-in harness reporting two characters a token compacts on its second turn with `token_scale` near 2.
- With every stream, history and compaction test: 53 passed, 7 skipped. ruff clean; `mypy --strict` on the three files clean.
- Mutant (the harness scale fixed at 1.0): "the second turn did not compact".
- Live: the installed `claude` through the parser on 15,675 characters of code: first call 23,998 tokens against an estimate of 3,918; the figure includes Claude Code's own prompt and tools.

Rubber Duck Pass: `ModelReply.usage` gains `first_call_prompt_tokens` on a harness driver's replies; `TranscriptCompacted.token_scale` now reads the harness's measured scale. No other event changes. No observations.
