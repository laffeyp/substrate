# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K260: kernel readers of session records read the old shape and the v0.3 shape alike.

Old (v0.2): a turn ends `ModelReply(text) → FinalAnswer(text) → Park`, a tool call writes no
ModelReply. New (vocabulary § K): one `ModelReply` per model call with a `stop_reason`, and
`Returned` ends the turn. The same two turns, written both ways, must render the same transcript
and yield the same replies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from substrate.topologies.session import transcript as t
from substrate.topologies.session.vocabulary import TURN_END_KINDS, turn_replies


def _env(seq: int, kind: str, **payload: Any) -> dict[str, Any]:
    return {"seq": seq, "kind": kind, "payload": payload}


OLD = [
    _env(10, "UserMessage", text="add 2 and 3", turn_index=0, assembled_prompt="add 2 and 3"),
    _env(11, "ToolCall", call_id="c0", tool="add", args=[2, 3], step=0),
    _env(12, "ToolResult", call_id="c0", tool="add", output=5, step=0, ok=True, error=""),
    _env(13, "ModelReply", text="It is 5.", model_usage={}, turn_index=0),
    _env(14, "FinalAnswer", text="It is 5.", steps=1),
    _env(15, "Park", awaiting="UserMessage", turn_index=0, reason="final_answer", detail=""),
    _env(16, "UserMessage", text="thanks", turn_index=1, assembled_prompt="thanks"),
    _env(17, "ModelReply", text="Any time.", model_usage={}, turn_index=1),
    _env(18, "FinalAnswer", text="Any time.", steps=0),
    _env(19, "Park", awaiting="UserMessage", turn_index=1, reason="final_answer", detail=""),
]

_USAGE = {"input_tokens": 9, "output_tokens": 3, "wall_ms": 40, "model": "m", "estimated": False}
NEW = [
    _env(10, "UserMessage", text="add 2 and 3", turn_index=0),
    _env(11, "ModelReply", text="", stop_reason="tool_use", usage=_USAGE, turn_index=0, step=0),
    _env(12, "ToolCall", call_id="c0", tool="add", args=[2, 3], step=0),
    _env(13, "ToolResult", call_id="c0", tool="add", output=5, step=0, ok=True, error=""),
    _env(
        14,
        "ModelReply",
        text="It is 5.",
        stop_reason="end_turn",
        usage=_USAGE,
        turn_index=0,
        step=1,
    ),
    _env(15, "Returned", turn_index=0, reason="replied", detail=""),
    _env(16, "UserMessage", text="thanks", turn_index=1),
    _env(
        17,
        "ModelReply",
        text="Any time.",
        stop_reason="end_turn",
        usage=_USAGE,
        turn_index=1,
        step=0,
    ),
    _env(18, "Returned", turn_index=1, reason="replied", detail=""),
]


def test_both_shapes_render_the_same_transcript() -> None:
    old = "\n".join(["SEED", *t._render_turns(t._group_by_turn(OLD))])
    new = "\n".join(["SEED", *t._render_turns(t._group_by_turn(NEW))])
    assert old == new, (old, new)
    assert old.count("It is 5.") == 1 and old.count("Any time.") == 1


def test_both_shapes_yield_the_same_replies() -> None:
    assert [text for _seq, text in turn_replies(OLD)] == ["It is 5.", "Any time."]
    assert [text for _seq, text in turn_replies(NEW)] == ["It is 5.", "Any time."]


def test_a_bail_answer_that_differs_from_the_reply_is_the_turns_reply() -> None:
    bail = [
        _env(1, "UserMessage", text="go", turn_index=0),
        _env(2, "FinalAnswer", text="stopped: tool failed", steps=3),
        _env(3, "Park", awaiting="UserMessage", turn_index=0, reason="final_answer"),
    ]
    assert [text for _seq, text in turn_replies(bail)] == ["stopped: tool failed"]


def test_both_turn_end_kinds_count() -> None:
    assert {"Returned", "Park"} <= TURN_END_KINDS


def test_delegate_reads_session_replies_through_the_helper() -> None:
    src = Path(__file__).resolve().parents[1] / "src/substrate/topologies/tool_loop/delegate.py"
    text = src.read_text()
    assert text.count("turn_replies(") == 2, "fan-out and standing-session reads use turn_replies"
