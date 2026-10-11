# Sprint 283 — Reading a harness driver's stream

```yaml
---
id: 283
status: open
phase: 1
pass_kind: functional
roadmap: substrate/process/planning/ROADMAP-2026-10-10-harness-tool-calls.md
asked: 2026-10-10 (Architect)
---
```

## why

`CliResponder.arespond` returns stdout as one string at exit, so a harness's own file writes and commands never reach the record. Each of the three CLIs streams every tool call (research, real runs in `substrate-ui/process/planning/evidence-2026-10-10-harness-streams/`).

## scope

- `adapters/harness_streams.py`: one parser per format (`claude-stream-json`, `codex-json`, `cursor-stream-json`) turning stream lines into tool-call, tool-result, final-text and token-usage items. Dollar estimates and rate-limit events are never read.
- `CliResponder(stream_format=, stream_flags=)` and `astream(prompt, system)`: an async iterator of those items; cancellation kills the process group as `arespond` does.
- The model step, for a driver with a stream format, yields `HarnessToolCall`/`HarnessToolResult` (`via=harness`) as they arrive and takes the final text as the reply. Usage comes from the stream's token counts.

## checks

- Each parser on its saved real stream: the write and the `ls` come out as calls with their results, and the final text matches.
- A session turn on each CLI records the file write as `via=harness`.
