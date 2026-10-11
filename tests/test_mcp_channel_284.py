# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K284, K286: the MCP channel (session vocabulary § Q.6).

A harness driver in the `mcp` tool mode calls the session's tools as registered MCP tools. The
daemon's endpoint hands each JSON-RPC message to `handle_jsonrpc` on a daemon thread. The running
model step records the call as Substrate's own `ToolCall(origin=mcp)`; the session's tool producer
runs it and writes the `ToolResult`, which goes back to the waiting request. No second model step
starts: the harness that asked is still running.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from substrate import api
from substrate.adapters.harness_streams import (
    CLAUDE_STREAM_JSON,
    StreamReply,
    StreamToolCall,
    StreamToolResult,
    StreamUsage,
)
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.mcp_channel import handle_jsonrpc, open_channel, tool_list
from substrate.topologies.tool_loop.tools import full_suite

SID = "s_284"


def _call(name: str, arguments: dict[str, Any], msg_id: int = 1) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


class FakeHarness:
    """A harness driver in-process: while its call runs, it calls the session's tools over the
    channel from another thread, as the daemon's MCP endpoint does, then replies."""

    name = "fake-harness"
    stream_format = CLAUDE_STREAM_JSON

    def __init__(self, calls: list[dict[str, Any]], echo: bool = False) -> None:
        self._calls = calls
        self._echo = echo  # also report each call in the stream, as Claude Code and Codex do
        self.prompts: list[str] = []
        self.responses: list[dict[str, Any] | None] = []

    async def astream(self, prompt: str, *, system: str = "") -> Any:
        self.prompts.append(prompt)
        for i, message in enumerate(self._calls):
            if self._echo:
                params = message["params"]
                yield StreamToolCall(
                    f"toolu_{i}", f"mcp__substrate__{params['name']}", params["arguments"]
                )
            self.responses.append(
                await asyncio.to_thread(handle_jsonrpc, SID, {**message, "id": i + 1})
            )
            if self._echo:
                yield StreamToolResult(f"toolu_{i}", True, "echo")
        yield StreamUsage(10, 2)
        yield StreamReply("done")


def _turn(tmp_path: Path, driver: FakeHarness, *, mcp: bool = True) -> list[dict[str, Any]]:
    root = tmp_path / "record"
    um = UserMessage(text="write a.txt", turn_index=0, assembled_prompt="", slash_source="chat")
    topo = session_topology(
        driver=driver,
        driver_name="fake-harness",
        driver_context_tokens=100_000,
        seed="SEED",
        tools=full_suite(tmp_path / "ws", owner=SID),
        session_id=SID,
        workspace_path=str(tmp_path / "ws"),
        first_turn_user_message=um,
        mcp=mcp,
    )
    (tmp_path / "ws").mkdir()
    asyncio.run(api.Runtime(root, persistent=True).run(topo, name="session"))
    return list(api.read_record(root, resolve_blobs=True))


def test_initialize_and_notifications() -> None:
    init = handle_jsonrpc(SID, {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
    assert init is not None
    assert init["result"]["serverInfo"]["name"] == "substrate"
    assert "tools" in init["result"]["capabilities"]
    assert handle_jsonrpc(SID, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_a_call_with_no_running_step_is_an_error() -> None:
    reply = handle_jsonrpc("s_none", _call("write_file", {"path": "x", "text": "y"}))
    assert reply is not None and reply["error"]["code"] == -32000


def test_tools_list_names_every_tool_with_its_schema(tmp_path: Path) -> None:
    tools = full_suite(tmp_path)
    listed = {t["name"]: t for t in tool_list(tools)}
    assert set(listed) == set(tools)
    assert listed["write_file"]["inputSchema"]["required"] == ["path", "text"]

    async def during_a_step() -> dict[str, Any] | None:
        with open_channel(SID, tools):
            return await asyncio.to_thread(
                handle_jsonrpc, SID, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
            )

    reply = asyncio.run(during_a_step())
    assert reply is not None and {t["name"] for t in reply["result"]["tools"]} == set(tools)


def _by_kind(events: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [e for e in events if e["kind"] == kind]


def test_a_harness_writes_a_file_through_the_tool_producer(tmp_path: Path) -> None:
    driver = FakeHarness([_call("write_file", {"path": "a.txt", "text": "ok"})])
    events = _turn(tmp_path, driver)
    assert (tmp_path / "ws" / "a.txt").read_text() == "ok"
    (response,) = driver.responses
    assert response is not None and response["result"]["isError"] is False
    assert "wrote 2 bytes" in response["result"]["content"][0]["text"]
    (call,) = _by_kind(events, "ToolCall")
    (result,) = _by_kind(events, "ToolResult")
    # Substrate's own kinds: the model step asked, the tool producer ran it and wrote the result.
    assert call["producer"]["kind"] == "model" and result["producer"]["kind"] == "tool"
    assert call["payload"]["origin"] == "mcp" and result["payload"]["origin"] == "mcp"
    assert (call["payload"]["tool"], call["payload"]["args"]) == ("write_file", ["a.txt", "ok"])
    assert result["payload"]["call_id"] == call["payload"]["call_id"] and result["payload"]["ok"]
    assert not _by_kind(events, "HarnessToolCall")
    # One model step: the result went back over MCP and started none.
    assert len(_by_kind(events, "PromptComposed")) == 1
    replies = _by_kind(events, "ModelReply")
    assert [r["payload"]["stop_reason"] for r in replies] == ["end_turn"]
    assert len(_by_kind(events, "Returned")) == 1
    # The mcp mode sends no text tool list and no JSON directive.
    (prompt,) = driver.prompts
    assert "Tools you MAY use" not in prompt and '"arguments"' not in prompt


def test_bad_calls_come_back_as_failures_the_model_reads(tmp_path: Path) -> None:
    driver = FakeHarness(
        [
            _call("no_such_tool", {}),
            _call("write_file", {"path": "a.txt"}),
            _call("write_file", {"file": "a.txt", "text": "x"}),
        ]
    )
    events = _turn(tmp_path, driver)
    assert [r["result"]["isError"] for r in driver.responses if r] == [True, True, True]
    texts = [r["result"]["content"][0]["text"] for r in driver.responses if r]
    assert "unknown tool" in texts[0]
    assert "missing required argument(s): text" in texts[1]
    assert "unknown argument(s) ['file']" in texts[2]
    results = [e["payload"] for e in _by_kind(events, "ToolResult")]
    assert [(r["ok"], r["origin"]) for r in results] == [(False, "mcp")] * 3
    assert not (tmp_path / "ws" / "a.txt").exists()
    assert len(_by_kind(events, "PromptComposed")) == 1


def test_the_tool_producers_own_rules_apply(tmp_path: Path) -> None:
    """The repeated-write guard lives in the tool producer. K284 ran MCP calls in the model step,
    so it never applied; through the tool producer it does."""
    write = _call("write_file", {"path": "a.txt", "text": "ok"})
    driver = FakeHarness([write, write])
    _turn(tmp_path, driver)
    first, second = driver.responses
    assert first is not None and first["result"]["isError"] is False
    assert second is not None and second["result"]["isError"] is True
    assert "already wrote a.txt" in second["result"]["content"][0]["text"]


def test_without_mcp_a_harness_keeps_the_text_tool_list(tmp_path: Path) -> None:
    driver = FakeHarness([])
    _turn(tmp_path, driver, mcp=False)
    (prompt,) = driver.prompts
    assert "Tools you MAY use" in prompt


def test_the_streams_copy_of_a_substrate_mcp_call_is_not_recorded_twice(tmp_path: Path) -> None:
    """Claude Code reports its call to Substrate's server as `mcp__substrate__write_file`, Codex as
    `substrate.write_file`. Found live 2026-10-10: each call landed twice, once per route."""
    driver = FakeHarness([_call("write_file", {"path": "a.txt", "text": "ok"})], echo=True)
    events = _turn(tmp_path, driver)
    assert [e["payload"]["tool"] for e in _by_kind(events, "ToolCall")] == ["write_file"]
    assert not _by_kind(events, "HarnessToolCall") and not _by_kind(events, "HarnessToolResult")
