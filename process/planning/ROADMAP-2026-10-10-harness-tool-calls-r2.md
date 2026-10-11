# ROADMAP: a harness driver's tool calls on the record (round 2)

*2026-10-10, night. Round 1 (`ROADMAP-2026-10-10-harness-tool-calls.md`, K282–K285, U129–U130) stays on disk.*

**Why a round 2.** Round 1 recorded a harness driver's call to Substrate's own tools over MCP as `HarnessToolCall` with `via = mcp`, and the model step ran the tool itself. The Architect caught it. Substrate's tools are recorded as Substrate's `ToolCall` and `ToolResult`, and `HarnessToolCall` and `HarnessToolResult` are for the harness's own tools only. Running a tool inside the model producer also bypassed the tool producer, which is the unit that runs tools, applies their rules (argument checks, the repeated-write guard) and writes their results.

## Pressure test (from the code)

| Question | Finding |
|---|---|
| Can the tool producer run while the model step that asked for it still runs? | Yes. The runtime runs each producer as its own asyncio task (`kernel/runtime.py:665`). |
| Can a trigger tell an MCP call's result from a reply's? | Yes, by payload. Each trigger has a predicate on the event (`session/__init__.py:1235-1265`). `ToolCall` and `ToolResult` need one field naming where the call came from. |
| What stops a second model step? | `model-on-tool-result` and `model-wrap-up-on-tool-result` start the next model call on every `ToolResult`. For an MCP call, the harness is still running in the current step and takes the result over MCP; a new step would start a second CLI process on the same turn. Both predicates skip an MCP call's result. |
| How does the waiting MCP request learn the result? | In-process. The session's tool producer, after it writes an MCP call's `ToolResult`, hands it to the call's waiting future. No record polling. |
| Can the tool producer end with no `ToolResult`? | Only by cancellation. It turns every failure into `ok = False` (`tool_loop/__init__.py:421-432`). A hard interrupt also cancels the model step, whose channel closes and releases every waiting call with an error. |

## Decisions

| Decision | What it decides |
|---|---|
| `ToolCall.origin`, `ToolResult.origin` | `reply` (the model step's reply asked for it; the default, so old records read) or `mcp` (a harness driver called it over MCP). |
| `HarnessToolCall` is the harness's own tools only | Its `via` field and `ToolRoute` go. |
| The model step only records the request | On an MCP call it yields `ToolCall(origin = mcp)`. The tool producer runs it and writes `ToolResult(origin = mcp)`. |
| One writer per event | The model producer writes the `ToolCall`, the tool producer writes the `ToolResult`; the MCP request only waits. |

## Cards

1. **K286: MCP calls through the tool producer.** Vocabulary v0.5.1 (§ Q.6); the `origin` field; the session's tool producer delivers MCP results; both continue-triggers skip `origin = mcp`; `mcp_channel.run_call` goes; `HarnessToolCall.via` goes. CI records regenerated. *Check:* the K284 tests rewritten. A harness writing `a.txt` over MCP leaves `ToolCall(origin = mcp)` then `ToolResult(origin = mcp)`, written by the tool producer, one model step, and no `HarnessToolCall` for it.
2. **U131: the console and the installed app.** `ToolCall` rows from MCP show `(mcp)`; `HarnessToolCall` rows show `(harness)`. Generated kinds, the kinds file, unit specs. Build, install, gates. *Check:* in the installed app, claude, codex and cursor-agent each write one file with their own tool (`HarnessToolCall`) and one with Substrate's `write_file` (`ToolCall` and `ToolResult`, `origin = mcp`), with one model step per turn.
