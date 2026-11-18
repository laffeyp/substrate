# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K357: the history view counts each event once.

`TurnHistory.update` re-rendered and re-counted the whole current turn on every event, so a turn
of n events was counted n times; since K352 each count is a tokenizer pass, and on a copy of an
11,882-envelope record it was 5.35 s of an 8.84 s resume (research
`RESEARCH-2026-11-18-bootstrap-time.md`). The view now adds each event's count as it arrives, and
`transcript.turn_cost` is the same sum.
"""

from __future__ import annotations

from typing import Any

import pytest
from _text import varied_text

from substrate.topologies.session import transcript
from substrate.topologies.session.transcript import TURN_EVENT_KINDS, output_savings, turn_cost
from substrate.topologies.session.views import TurnHistory
from substrate.types import Event


def _turn(turn_index: int, calls: int) -> list[dict[str, Any]]:
    """A turn with every kind the history renders: message, a change line, native and harness
    tool calls and results, a tool-use reply, a final reply."""
    out: list[dict[str, Any]] = [
        {
            "kind": "UserMessage",
            "payload": {"text": "go " + varied_text(200), "turn_index": turn_index},
        },
        {"kind": "SessionChanged", "payload": {"field": "driver", "old": "a", "new": "b"}},
    ]
    for i in range(calls):
        out += [
            {"kind": "ModelReply", "payload": {"text": "", "stop_reason": "tool_use"}},
            {"kind": "ToolCall", "payload": {"call_id": f"c{i}", "tool": "read", "args": [i]}},
            {
                "kind": "ToolResult",
                "payload": {
                    "call_id": f"c{i}",
                    "tool": "read",
                    "ok": True,
                    "output": varied_text(400),
                },
            },
            {
                "kind": "HarnessToolCall",
                "payload": {"call_id": f"h{i}", "tool": "Bash", "args": {"command": "ls"}},
            },
            {
                "kind": "HarnessToolResult",
                "payload": {"call_id": f"h{i}", "ok": i % 2 == 0, "output": varied_text(300)},
            },
        ]
    out.append(
        {
            "kind": "ModelReply",
            "payload": {"text": "done " + varied_text(120), "stop_reason": "end_turn"},
        }
    )
    return out


def _fold(turns: list[list[dict[str, Any]]]) -> TurnHistory:
    view = TurnHistory(TURN_EVENT_KINDS)
    seq = 0
    for turn in turns:
        for env in turn:
            env["seq"] = seq
            view.update(
                Event(
                    seq=seq,
                    kind=env["kind"],
                    schema="",
                    producer=None,
                    t=0.0,
                    payload=env["payload"],
                )
            )
            seq += 1
    return view


def test_the_running_count_is_the_turns_count() -> None:
    turns = [_turn(0, 3), _turn(1, 5)]
    state = _fold(turns).value()
    assert [cost for _a, _b, cost, _s in state.turns] == [turn_cost(t) for t in turns]
    assert [savings for _a, _b, _c, savings in state.turns] == [output_savings(t) for t in turns]
    assert all(cost > 0 for _a, _b, cost, _s in state.turns)


def test_a_long_turn_is_counted_once_per_event(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    count = transcript.count_tokens

    def counting(text: str) -> int:
        calls["n"] += 1
        return count(text)

    monkeypatch.setattr(transcript, "count_tokens", counting)
    turn = _turn(0, 60)  # 303 events
    _fold([turn])
    # One count per rendered event, the header, and two per tool result (whole and placeholder).
    assert calls["n"] <= 3 * len(turn)
