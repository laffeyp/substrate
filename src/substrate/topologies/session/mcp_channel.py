# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The MCP channel: a harness driver calls the session's tools as registered tools (K284).

While a harness driver's model step runs, the step opens a channel for its session. The daemon's
MCP endpoint hands each JSON-RPC message to `handle_jsonrpc`. `tools/list` answers from the
session's tools. `tools/call` puts the call on the channel and waits. The model step takes it from
the channel, runs the tool, writes `HarnessToolCall` / `HarnessToolResult` with `via=mcp`, and
sends the result back. The model step is the record's only writer.

MCP's JSON-RPC shapes (`initialize`, `notifications/initialized`, `tools/list`, `tools/call`) are
written here; no MCP library is needed for three methods. Session vocabulary § Q.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Final

from ...adapters.harness_streams import SUBSTRATE_MCP_SERVER
from ..tool_loop.tools import (
    ARG_ERROR_KEY,
    Tool,
    _named_to_positional,
    ollama_tools,
    required_params,
)

MCP_PROTOCOL_VERSION: Final[str] = "2025-06-18"
MCP_SERVER_NAME: Final[str] = SUBSTRATE_MCP_SERVER

# JSON-RPC error codes (JSON-RPC 2.0 § 5.1).
_METHOD_NOT_FOUND: Final[int] = -32601
_INVALID_PARAMS: Final[int] = -32602
_NO_RUNNING_STEP: Final[int] = -32000

# How long a `tools/call` waits for the model step to run it. A harness's step can run for a
# long time; the bound only stops a daemon thread waiting forever on a step that is gone.
_CALL_WAIT_SECONDS: Final[float] = 3600.0


@dataclass
class McpCall:
    """One `tools/call` waiting for the model step."""

    tool: str
    arguments: dict[str, Any]
    reply: concurrent.futures.Future[tuple[bool, str]] = field(
        default_factory=concurrent.futures.Future
    )


@dataclass
class McpChannel:
    """A running harness step's channel: its tools and the queue its step reads."""

    tools: dict[str, Tool]
    loop: asyncio.AbstractEventLoop
    calls: asyncio.Queue[McpCall]


_CHANNELS: dict[str, McpChannel] = {}
_LOCK = threading.Lock()


@contextmanager
def open_channel(session_id: str, tools: dict[str, Tool]) -> Iterator[McpChannel]:
    """Open the session's channel for the length of one harness step. Called on the step's loop."""
    channel = McpChannel(tools=dict(tools), loop=asyncio.get_running_loop(), calls=asyncio.Queue())
    with _LOCK:
        _CHANNELS[session_id] = channel
    try:
        yield channel
    finally:
        with _LOCK:
            if _CHANNELS.get(session_id) is channel:
                del _CHANNELS[session_id]
        while not channel.calls.empty():  # calls that arrived as the step ended
            channel.calls.get_nowait().reply.set_result((False, "the session's model step ended"))


def tool_list(tools: dict[str, Tool]) -> list[dict[str, Any]]:
    """The session's tools in MCP's `tools/list` shape."""
    return [
        {
            "name": t["function"]["name"],
            "description": t["function"]["description"],
            "inputSchema": t["function"]["parameters"],
        }
        for t in ollama_tools(tools)
    ]


async def run_call(call: McpCall, tools: dict[str, Tool]) -> tuple[bool, str]:
    """Run one call the way the session's tool producer runs a `ToolCall`: unknown tools, bad and
    missing arguments come back as failures the model reads; the body runs in a worker thread so
    an interrupt reaches the loop, and a cancel runs the tool's own stop hooks."""
    from ..tool_loop.tools import _TOOL_CANCEL_HOOKS

    entry = tools.get(call.tool)
    if entry is None:
        return False, f"unknown tool '{call.tool}'"
    args = _named_to_positional(call.tool, call.arguments, tools)
    if len(args) == 1 and isinstance(args[0], dict) and ARG_ERROR_KEY in args[0]:
        return False, str(args[0][ARG_ERROR_KEY])
    missing = required_params(call.tool, tools)[len(args) :]
    if missing:
        return False, f"{call.tool}: missing required argument(s): {', '.join(missing)}"
    cancel_hooks: list[Any] = []
    token = _TOOL_CANCEL_HOOKS.set(cancel_hooks)
    try:
        output = await asyncio.to_thread(entry.run, args)
    except asyncio.CancelledError:
        for hook in list(cancel_hooks):
            try:
                hook()
            except Exception:  # noqa: BLE001, S110 — one failed stop must not skip the others
                pass
        raise
    except Exception as e:  # noqa: BLE001 — a tool's failure is the model's observation
        return False, f"{type(e).__name__}: {e}"
    finally:
        _TOOL_CANCEL_HOOKS.reset(token)
    return True, output if isinstance(output, str) else json.dumps(output, default=str)


def _ok(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle_jsonrpc(session_id: str, message: dict[str, Any]) -> dict[str, Any] | None:
    """Answer one MCP JSON-RPC message for a session. A notification returns None. Called from a
    daemon thread; a `tools/call` blocks until the model step has run it."""
    method = message.get("method")
    msg_id = message.get("id")
    if method == "initialize":
        return _ok(
            msg_id,
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": MCP_SERVER_NAME, "version": "1"},
            },
        )
    if isinstance(method, str) and method.startswith("notifications/"):
        return None
    if method == "ping":
        return _ok(msg_id, {})
    with _LOCK:
        channel = _CHANNELS.get(session_id)
    if method == "tools/list":
        return _ok(msg_id, {"tools": tool_list(channel.tools) if channel else []})
    if method != "tools/call":
        return _err(msg_id, _METHOD_NOT_FOUND, f"method not found: {method}")
    if channel is None:
        return _err(msg_id, _NO_RUNNING_STEP, f"session {session_id} has no running model step")
    params = message.get("params") or {}
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return _err(msg_id, _INVALID_PARAMS, "tools/call takes a name and an arguments object")
    call = McpCall(tool=name, arguments=arguments)
    asyncio.run_coroutine_threadsafe(channel.calls.put(call), channel.loop)
    try:
        ok, output = call.reply.result(timeout=_CALL_WAIT_SECONDS)
    except concurrent.futures.TimeoutError:
        return _err(msg_id, _NO_RUNNING_STEP, f"{name}: the model step did not run the call")
    return _ok(msg_id, {"content": [{"type": "text", "text": output}], "isError": not ok})


__all__ = [
    "MCP_PROTOCOL_VERSION",
    "MCP_SERVER_NAME",
    "McpCall",
    "McpChannel",
    "handle_jsonrpc",
    "open_channel",
    "run_call",
    "tool_list",
]
