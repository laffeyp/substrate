# ROADMAP: a harness driver's tool calls on the record

*2026-10-10.*

**Input.** `substrate-ui/process/planning/RESEARCH-2026-10-10-harness-tool-calls-on-the-record.md` and its evidence folder, and the Architect's direction recorded there.

**Goal.** Every tool call a harness driver (claude, codex, cursor-agent) makes is on the session's record, whichever tool set it used. Its own tools are read from its event stream. Substrate's tools reach it as registered tools through an MCP server, served only to harness drivers, and each such call runs in Substrate. Ollama models keep native tool calls and change in no way.

## What exists today

- **The CLI call.** `CliResponder.arespond` (`adapters/models.py:549`) waits for the CLI to exit and returns stdout as one string. Everything the harness did in between is lost.
- **The model step** (`topologies/session/__init__.py:582-626`) is an async generator yielding `ModelReply` and `ToolCall`. A CLI driver runs in "text" tool mode: Substrate's tools are a list in the prompt plus a JSON directive. Codex read that list as "supplied as text … does not make them callable".
- **The streams** (research, real runs): claude `--output-format stream-json --verbose` gives `tool_use` and `tool_result`; codex `exec --json` gives `item.started` and `item.completed` (`command_execution`, `file_change`, `mcp_tool_call`); cursor-agent `--output-format stream-json` gives `tool_call` started and completed. Each carries name, arguments, result and an id.
- **MCP support.** claude takes `--mcp-config <json>` (with `--strict-mcp-config` already set); codex takes a streamable HTTP server (`codex mcp add --url`); cursor-agent reads `.cursor/mcp.json`, and a forum report says `-p` mode does not pass MCP tools to the model. No MCP library is installed in the kernel.

## Decisions for this roadmap

| Decision | What it decides |
|---|---|
| One event pair, two routes | `HarnessToolCall{call_id, tool, args, via, step, turn_index}` and `HarnessToolResult{call_id, ok, output}`. `via` is `harness` (its own tool, read from the stream) or `mcp` (Substrate's tool, run by Substrate). Distinct from `ToolCall`, which starts Substrate's tool producer and the next model step; a harness call happens inside one model step and must start nothing. |
| The model step writes them | Single writer: the model step yields each event as the stream or the MCP channel delivers it. |
| MCP over HTTP from the daemon | `POST /api/session/<id>/mcp`, JSON-RPC `initialize`, `tools/list`, `tools/call`, written in Substrate (three methods; no new dependency). A call is handed to the session's running model step, which runs the tool and records it. |
| MCP only for harness drivers | A driver profile names how its CLI takes an MCP server. Ollama drivers get none. |
| Text tool list goes for MCP drivers | A driver with MCP gets Substrate's tools only as registered tools; the prompt drops the text list and the JSON directive. |
| No money | Stream fields for dollar estimates and rate limits are never read. Token counts from the stream are measurements and are kept. |
| A driver that cannot take MCP headless keeps streams | If cursor-agent `-p` does not pass MCP tools to its model (to be tested in U129), it gets stream recording only and keeps the text list. |

## Order and checks

Each card runs the tests for the code it changes. The full kernel and UI suites run once, in U130.

1. **K282: session vocabulary v0.5 (§ Q).** `HarnessToolCall`, `HarnessToolResult`, the `via` values, the `mcp` tool mode. Structs, constants, `SESSION_KINDS`, transcript lines so the next turn's history shows them. *Check:* vocabulary tests; a record with the pair renders in history.
2. **K283: reading a harness's stream.** `adapters/harness_streams.py`: one parser per format (claude, codex, cursor-agent) that turns stream lines into tool-call, tool-result, final-text and usage items. `CliResponder` gains `stream_format` and `astream()`; the model step yields the pair live and takes the final text as the reply. *Check:* parsers on the saved real streams; a session on each CLI records a file write as `via=harness`.
3. **K284: the MCP channel.** `topologies/session/mcp_channel.py`: a per-session handler the model step registers while the harness runs; `tools/list` from the session's tools; `tools/call` runs the tool and records the pair `via=mcp`. *Check:* a test drives a scripted harness that calls `write_file` over the channel and finds the pair on the record and the file on disk.
4. **U129: the daemon and the drivers.** Profiles gain `stream_flags`, `stream_format` and an MCP injection (claude `--mcp-config`, codex `-c mcp_servers.substrate.url=…`, cursor-agent `.cursor/mcp.json` with `--approve-mcps`). The `/mcp` endpoint. The transcript shows each pair as a tool card marked with its route. *Check:* in the installed app, one session per driver writes a file with its own tool and one with Substrate's `write_file`; both appear on the record and in the transcript.
5. **U130: gates, suites, install.** Live tests (opt-in) per driver for both routes; full kernel and UI suites; build, install, all Electron gates.
6. **K285: amend the specs.** Product spec round 14, tech spec round 8, design spec round 3: harness drivers, their tool routes and the MCP endpoint. Earlier rounds untouched.
