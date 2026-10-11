# Sprint 282 — Session vocabulary v0.5: a harness driver's tool calls

```yaml
---
id: 282
status: open
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-harness-tool-calls.md
asked: 2026-10-10 (Architect)
---
```

## why

A harness driver (claude, codex, cursor-agent) runs its own agent loop inside one model step. Its tool calls are not Substrate's `ToolCall`: that event starts Substrate's tool producer and then the next model step. They need their own kinds.

## scope

- `session-vocabulary.md` § Q: `HarnessToolCall{call_id, tool, args, via, step, turn_index}` and `HarnessToolResult{call_id, ok, output}`. `via` is `harness` (the driver's own tool, read from its stream) or `mcp` (Substrate's tool, run by Substrate over MCP). Neither starts a producer.
- The `mcp` tool mode: a driver that takes Substrate's tools as registered MCP tools; its prompt carries no text tool list and no JSON directive.
- Structs and constants in `vocabulary.py`; both kinds in `SESSION_KINDS` and `TURN_EVENT_KINDS`; `transcript.py` renders them in history so the next turn sees what the driver did.

## checks

- The vocabulary tests, including the raw-literal scan.
- A record holding the pair renders both lines in the next prompt's history.
