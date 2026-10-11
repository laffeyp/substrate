# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K282: session vocabulary v0.5 (§ Q), a harness driver's tool calls.

`HarnessToolCall` and `HarnessToolResult` are session kinds and turn events. They start no producer,
and history renders them between the turn's `USER:` line and its reply.
"""

from __future__ import annotations

from typing import Any

import msgspec

from substrate.topologies.session import HarnessToolCall, HarnessToolResult
from substrate.topologies.session.transcript import TURN_EVENT_KINDS, compose_model_prompt
from substrate.topologies.session.vocabulary import (
    HARNESS_TOOL_CALL,
    HARNESS_TOOL_RESULT,
    SESSION_KINDS,
    ToolMode,
)


def test_the_kinds_are_session_kinds_and_turn_events() -> None:
    for kind in (HARNESS_TOOL_CALL, HARNESS_TOOL_RESULT):
        assert kind in SESSION_KINDS
        assert kind in TURN_EVENT_KINDS
    assert {m.value for m in ToolMode} == {"none", "native", "text", "mcp"}


def test_the_pair_round_trips() -> None:
    call = HarnessToolCall(
        call_id="toolu_1",
        tool="Bash",
        args={"command": "ls"},
        step=0,
        turn_index=2,
    )
    back = msgspec.json.decode(msgspec.json.encode(call), type=HarnessToolCall)
    assert back == call
    result = HarnessToolResult(call_id="toolu_1", ok=True, output="a.txt")
    assert msgspec.json.decode(msgspec.json.encode(result), type=HarnessToolResult) == result


def _env(seq: int, kind: str, **payload: Any) -> dict[str, Any]:
    return {"seq": seq, "kind": kind, "payload": payload}


def test_history_shows_the_calls_between_the_message_and_the_reply() -> None:
    history = [
        _env(1, "UserMessage", text="make a.txt", turn_index=0),
        _env(
            2,
            HARNESS_TOOL_CALL,
            call_id="c1",
            tool="Bash",
            args={"command": "printf ok > a.txt"},
            step=0,
            turn_index=0,
        ),
        _env(3, HARNESS_TOOL_RESULT, call_id="c1", ok=True, output=""),
        _env(
            4,
            "ToolCall",
            call_id="mcp0.0",
            tool="read_file",
            args=["a.txt"],
            step=0,
            origin="mcp",
        ),
        _env(
            5,
            "ToolResult",
            call_id="mcp0.0",
            tool="read_file",
            output="",
            step=0,
            ok=False,
            error="no such file",
            origin="mcp",
        ),
        _env(6, "ModelReply", text="done", stop_reason="end_turn", turn_index=0, step=0),
        _env(7, "Returned", reason="replied", turn_index=0),
        _env(8, "UserMessage", text="next", turn_index=1),
    ]
    _system, text, _seqs = compose_model_prompt(history=history, seed="SEED", fragments=[])
    order = [
        "USER: make a.txt",
        "HARNESS TOOL Bash: args={'command': 'printf ok > a.txt'}",
        "HARNESS RESULT: ",
        "TOOL read_file: args=['a.txt']",
        "RESULT(fail): no such file",
        "MODEL: done",
        "USER: next",
    ]
    positions = [text.index(line) for line in order]
    assert positions == sorted(positions), text
