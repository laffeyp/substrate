# Sprint 283 — Reading a harness driver's stream

```yaml
---
id: 283
status: closed
closed_at: 2026-10-10
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

## result

- **Parsers.** `adapters/harness_streams.py`: `ClaudeStreamParser`, `CodexJsonParser` and `CursorStreamParser`, each feeding lines into `StreamToolCall`, `StreamToolResult`, `StreamUsage` and a final text. A failed run raises `HarnessStreamError`; non-JSON lines are skipped. A Codex `file_change` that arrives only as completed writes its call first. Dollar and rate-limit fields are never read.
- **The CLI.** `CliResponder(stream_format=, stream_flags=)` and `astream()`, which reads stdout line by line, drains stderr alongside, kills the process group on a cancel and yields `StreamReply` last. `respond` and `arespond` return the stream's reply, so every other caller keeps working.
- **The model step.** A driver with a stream format yields `HarnessToolCall` and `HarnessToolResult` (`via=harness`) as they arrive. It takes the stream's reply, and its token counts as usage (`estimated=False`).
- **Tests.** `tests/test_harness_stream_283.py`: the three parsers on real streams (fixtures in `tests/fixtures/harness_streams/`), Codex with its shell off, a failed run, a whole session turn on a replayed cursor-agent stream (the calls land before the reply, and Substrate's own tool producer never runs): 8 passed. Live, opt-in: claude, codex and cursor-agent each wrote `a.txt`, read from the stream, 3 of 3. Every non-live test naming `CliResponder` or the session topology: 209 passed.
- **Not yet.** The daemon passes no stream format until UI sprint 129.
