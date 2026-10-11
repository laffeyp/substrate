# Sprint 290 — Tool outputs sent once

```yaml
---
id: 290
status: open
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-11-compaction.md
asked: 2026-10-11 (Architect)
---
```

## scope

- Remove the model step's "Tool results so far" block where the history already holds this turn's `ToolResult` events (native and text tool modes; `session/__init__.py`, the `progress` block). The wrap-up prompt keeps its own ending.

## checks

- In a native-tool session with two tool calls in one turn, each output appears once in the second step's `PromptComposed`; the golden prompts change only by the removed block.

## result

