# Sprint 290 — Tool outputs sent once

```yaml
---
id: 290
status: closed
closed_at: 2026-10-11
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

- **Fixed.** The model step no longer appends "Tool results so far" in native mode, text mode or the wrap-up prompt (`session/__init__.py`). This turn's results are already in the history as `TOOL` and `RESULT` lines, because the ticket runs to the triggering `ToolResult`. The wrap-up directive, the last error and the text-mode tool list stay.
- **Test.** `test_tool_outputs_sent_once_290.py`: a text-mode driver calls a tool twice in one turn, and each marker appears once in each later prompt. It fails on the old code (2 copies of the first marker in the second prompt) and passes now.
- **Suites.** Session, prompt, tool-loop, harness and guidance tests: 258 passed, 5 skipped (opt-in tiers).
- **Out of scope.** `tool_loop/__init__.py` keeps its own "Tool results so far": that topology renders no transcript history, so its list is the only copy.

