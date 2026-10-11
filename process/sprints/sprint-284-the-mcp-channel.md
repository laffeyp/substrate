# Sprint 284 — The MCP channel

```yaml
---
id: 284
status: closed
closed_at: 2026-10-10
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

## result

- **The channel.** `topologies/session/mcp_channel.py`. `open_channel(session_id, tools)` lasts for one harness step. `handle_jsonrpc` answers `initialize`, `ping`, `notifications/*`, `tools/list` (from `ollama_tools`, in MCP's `inputSchema` shape) and `tools/call`. A call is queued onto the step's loop with `run_coroutine_threadsafe`, and the daemon thread waits on a `concurrent.futures.Future`. A call with no running step answers JSON-RPC error −32000.
- **Running a call.** `run_call` runs the call the way the tool producer runs a `ToolCall`: unknown tools, unknown arguments and missing ones come back as failures. The body runs in `asyncio.to_thread`, and a cancel runs the tool's stop hooks.
- **The model step.** `session_topology(mcp=True)` with a streaming driver selects `ToolMode.MCP`, so the prompt carries no text tool list and no JSON directive. `_harness_stream` reads the stream and the channel from one queue and yields `via=harness` and `via=mcp` pairs in the order they happen. A cancel stops both.
- **Tests.** `tests/test_mcp_channel_284.py`, 6 passed:
  - `initialize`, notifications, and the error for a call with no running step;
  - `tools/list` against the suite;
  - a harness writing `a.txt` through the channel, with the file on disk, the pair on the record before the reply, no `ToolCall`, and no tool list in the prompt;
  - three bad calls returned as failures;
  - `mcp=False` keeping the text list.

  Session, vocabulary and transcript tests: 393 passed. Records and API docs: 45 passed.
- **Not yet.** The daemon endpoint and each driver's MCP flags come in UI sprint 129.
