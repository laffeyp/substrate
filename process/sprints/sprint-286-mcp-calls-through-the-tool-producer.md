# Sprint 286 — MCP calls through the tool producer

```yaml
---
id: 286
status: closed
closed_at: 2026-10-10
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-harness-tool-calls-r2.md
asked: 2026-10-10 (Architect)
---
```

## why

K284 recorded a harness driver's call to Substrate's own tools as `HarnessToolCall` with `via = mcp`, and ran the tool inside the model step. The Architect: `HarnessToolCall` is for the harness's tools, and Substrate's tools are `ToolCall` and `ToolResult`. Running the tool in the model producer also bypassed the tool producer: its argument checks were copied by hand, and its repeated-write guard never applied.

## scope

Roadmap r2: vocabulary § Q.6, `ToolCall.origin` and `ToolResult.origin`, the tool producer runs MCP calls, and both continue-triggers skip `origin = mcp`.

## result

- **Vocabulary.** § Q.6 amends Q.1–Q.3. `ToolCallOrigin` (`reply`, `mcp`) sits in `tool_loop/kinds.py`. `ToolCall` and `ToolResult` carry `origin`, default `reply`, so old frames decode. `HarnessToolCall` drops `via`, and `ToolRoute` is gone.
- **The model step.** On an MCP call it registers the waiting future and yields `ToolCall(origin = mcp)`, with arguments mapped by `_named_to_positional`. It runs nothing.
- **The tool producer.** `tool-on-tool-call` passes `origin`. `_tool_factory` writes it on every `ToolResult`. `_session_tool_factory` wraps the tool loop's producer: once a `ToolResult(origin = mcp)` is written, `mcp_channel.deliver` hands it to the waiting request.
- **No second model step.** `model-on-tool-result` and `model-wrap-up-on-tool-result` add `_answers_reply`.
- **The channel.** `mcp_channel.run_call` is gone. The channel keeps `pending` futures by call id, and closing it releases every queued and pending call with an error.
- **Records.** The `session`, `daily` and `tool_loop` CI records were regenerated. The script rewrote all 18; the 15 that were not stale were restored.
- **Tests.**
  - `test_mcp_channel_284.py`, 8 passed. A harness's `write_file` over MCP leaves a `ToolCall` written by `model` and a `ToolResult` written by `tool`, both `origin = mcp`, with one `PromptComposed`, one `ModelReply` and one `Returned`. Three bad calls come back as failures from the tool producer. A second write of the same file is refused by the repeated-write guard. A stream's echo of the call is skipped.
  - K282 and K283 tests updated: 11 passed.
  - Every non-live kernel test naming tools, the session or the transcript: 559 passed.
