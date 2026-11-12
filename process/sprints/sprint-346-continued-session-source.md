# Sprint 346 — The continued_session prompt source (session vocabulary v0.19)

```yaml
---
id: 346
status: closed
closed_at: 2026-11-12
phase: continuing a session (substrate-ui roadmap 2026-11-12-continue-a-session r1, E2)
pass_kind: functional
depends_on: [345]
plan: ../substrate-ui/process/planning/2026-11-12-continue-a-session/ROADMAP-2026-11-12-continue-a-session-r1.md
---
```

## scope

A session-open prompt source that carries a conversation held elsewhere into a new session. `PromptSource.CONTINUED_SESSION` (`"continued_session"`) joins the session-open sources at precedence 30, beside `parent_context`. Its function takes `{"turns": [...], "provenance": {...}}`: `turns` are event dicts of the kinds the history renders (`UserMessage`, `ModelReply`, `HarnessToolCall`, `HarnessToolResult`); the source groups them into turns and renders them with the history's renderer (`_group_by_turn`, `_render_turns`, `transcript.py`), so the opening text reads as Substrate's own history does, and records one `PromptFragment` with the given provenance. No tool-specific code: reading another tool's file is the caller's. Session vocabulary § AD, v0.19. One verifiable property: given two turns, the fragment's text equals what `_render_turns` writes for the same two turns.

## context_files

- `src/substrate/topologies/session/session_prompt_producer.py` (`parent_context_fragments`, `session_prompt_sources`)
- `src/substrate/topologies/session/vocabulary.py` (`PromptSource`, `SESSION_OPEN_SOURCES`)
- `src/substrate/topologies/session/transcript.py` (`_group_by_turn`, `_render_turns`, `head_block`)
- `process/signals/session-vocabulary.md` (§ I, § P.2, § AC)

## signal contract

### Emits

- `PromptFragment(source=continued_session, precedence=30, provenance={tool, path, summary_line, turns, events})`.

### Invariants

- A session that names no continued session writes the fragments it writes today, byte for byte.
- §§ A–AC of the session vocabulary byte-preserved.

## artifact contract

### Files modified

- `src/substrate/topologies/session/vocabulary.py`, `session_prompt_producer.py`, `process/signals/session-vocabulary.md` (§ AD, v0.19 status line)

### Files created

- `tests/test_continued_session_source.py`

### Content assertions

- `PromptSource.CONTINUED_SESSION` is in `SESSION_OPEN_SOURCES`; § AD names the field, its precedence and its provenance.

### Command exit codes

- `uv run pytest tests/test_continued_session_source.py` and the session topology's tests return 0; `scripts/ci_local.sh` at the roadmap's close.

## observation contract

A session run in the test with the source set: its record holds one `PromptFragment` of source `continued_session`, and its first `PromptComposed.text` holds the rendered turns after the head's other fragments by precedence.

## done criteria

A new session can open with another conversation's turns as its opening text, written as Substrate writes its own history.

## notes

Primitive-plus-consumer: the consumer is sprint 347 (`sprint-347-session-names-continuation.md`), which wires the source into the session topology from the manifest. Three source files for one concept: the vocabulary member, the source, the vocabulary document.

## self-review checklist

- [x] Scope is concrete and bounded.
- [x] Vocabulary change by the document's next version, § AD.
- [x] Consumer named, its card on disk.
- [x] Artifact contract is gradable.
- [x] Observation contract present.

## close

`PromptSource.CONTINUED_SESSION` is a session-open source (`vocabulary.py`); `continued_session_fragments` renders the given turns with `_group_by_turn` and `_render_turns` after one line naming the tool, and `session_prompt_sources` takes `continued_session` (`session_prompt_producer.py`). Session vocabulary v0.19, § AD. `tests/test_session_prompt_vocabulary_v02.py` lists the new source in its two pinned sets, as a vocabulary change requires.

- `tests/test_continued_session_source.py`: 5 passed. The fragment's text is the renderer's own; precedence 30, provenance with the counts; no turns, no fragment; a source only when named; the producer body yields it and `compose_model_prompt` places it after the seed.
- With the memory, parent-context, producer and vocabulary tests: 31 passed. `ruff check`, `ruff format --check` clean; `mypy --strict` on the two source files clean.
- Mutant (the raw events in place of the rendering): 2 of 5 fail.

The observation contract's full session run moves to sprint 347, which wires the source into the session topology; here the producer body and the composer are run directly.

Rubber Duck Pass: one new fragment kind on the record, `PromptFragment(source=continued_session)`, written once at session open with its provenance; no other event changes. No observations.
