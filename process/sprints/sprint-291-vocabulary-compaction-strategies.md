# Sprint 291 — Vocabulary round: compaction strategies

```yaml
---
id: 291
status: closed
closed_at: 2026-10-11
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-11-compaction.md
asked: 2026-10-11 (Architect)
---
```

## scope

- `process/signals/session-vocabulary.md` § D: `strategy` gains `tool_output_cleared`; `TranscriptCompacted` carries the cleared seqs beside `dropped_seq_range`; invariants: a user message is never cleared or dropped while a later turn is kept, and no event is recorded unless the cut changed. The paired UI tag and `envelope_kinds` follow.

## checks

- The vocabulary, the Struct and the golden schema tests agree; the UI's generated kinds build.

## result

- **Vocabulary v0.7, § S.** The order of cuts (tool outputs first, whole turns only after), clearing that holds still until the budget forces it, the placeholder lines, the amended `TranscriptCompacted`, the estimate's scale, and invariants 9–11. One decision was made here: the cleared set is one boundary, `cleared_through_seq`, not a list of seqs, because outputs clear oldest first while the newest 3 stay whole.
- **Struct.** `TranscriptCompacted` gains `cleared_through_seq` and `token_scale`; `dropped_seq_range` becomes optional. All three have defaults, so records before v0.7 decode unchanged.
- **Constants.** `COMPACTION_ROLLING_WINDOW`, `COMPACTION_TOOL_OUTPUT_CLEARED` and `COMPACTION_REASON_WINDOW_EXCEEDED` in `vocabulary.py`; the emission site uses them in place of retyped strings.
- **Tests.** `test_compaction_vocabulary_291.py`: the codex session's v0.6 payload decodes; v0.7 fields round-trip. 2 of 2. Existing compaction and prompt tests: 10 of 10. `mypy --strict` clean on the session package.
- **The UI side** moves to K293: `session_controller.ts:1255` reads `dropped_seq_range`, which can now be absent; the event's kind name is unchanged, so the generated kinds need no change.

