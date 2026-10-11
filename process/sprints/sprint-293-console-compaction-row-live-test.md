# Sprint 293 — The console's compaction row; live test

```yaml
---
id: 293
status: open
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-11-compaction.md
asked: 2026-10-11 (Architect)
---
```

## scope

- substrate-ui: the compaction row names what was cleared or dropped, and a repeated cut does not appear. An opt-in live test reruns the codex case: a heavy second turn, then a question that needs it. Full kernel and UI suites once.

## checks

- The third turn's prompt holds the first two user messages and replies, and the model answers from them; suites pass.

## result

