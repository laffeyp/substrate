# Sprint 291 — Vocabulary round: compaction strategies

```yaml
---
id: 291
status: open
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

