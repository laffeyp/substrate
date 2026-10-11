# Sprint 284 — The MCP channel

```yaml
---
id: 284
status: open
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-harness-tool-calls.md
asked: 2026-10-10 (Architect)
---
```

## why

A harness driver gets Substrate's tools only as text in its prompt, and Codex said that does not make them callable. Over MCP they are registered tools, and Substrate runs each call.

## scope

- `topologies/session/mcp_channel.py`: a registry of per-session handlers. While a harness call runs, the model step registers one for its session; a handler answers `tools/list` from the session's tools and `tools/call` by running the tool.
- The model step drains the handler's calls while it reads the stream, and yields `HarnessToolCall`/`HarnessToolResult` (`via=mcp`) for each, so the record has one writer.
- `handle_jsonrpc(session_id, message)`: `initialize`, `tools/list`, `tools/call`, `notifications/initialized`; MCP's JSON-RPC shapes, written in Substrate with no new dependency. A call for a session with no running harness step answers an MCP error.

## checks

- A scripted harness calls `write_file` through `handle_jsonrpc` while its step runs: the file is on disk and the pair is on the record with `via=mcp`.
- `tools/list` names every tool the session binds, with its input schema.
