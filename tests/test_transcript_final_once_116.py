# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""UI sprint 116: a plain-text answer reaches the next prompt once, not twice.

A plain reply writes a ModelReply and a FinalAnswer with the same text. The transcript rendered
both, so the driver read every earlier answer twice (a CLI driver said so, 2026-10-09). A
FinalAnswer whose text differs from the turn's last ModelReply (one pulled out of a JSON reply)
still renders.
"""

from __future__ import annotations

from typing import Any

from substrate.topologies.session import transcript as t


def _turn(*events: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"kind": kind, "payload": payload} for kind, payload in events]


def test_a_plain_answer_renders_once() -> None:
    turn = _turn(
        (t._KIND_USER_MESSAGE, {"text": "hello", "turn_index": 0}),
        (t._KIND_MODEL_REPLY, {"text": "hi there"}),
        (t._KIND_FINAL_ANSWER, {"text": "hi there"}),
    )
    prompt = "\n".join(t._render_turns([turn]))
    assert prompt.count("hi there") == 1, prompt


def test_a_final_answer_that_differs_still_renders() -> None:
    turn = _turn(
        (t._KIND_USER_MESSAGE, {"text": "sum", "turn_index": 0}),
        (t._KIND_MODEL_REPLY, {"text": '{"final": "42"}'}),
        (t._KIND_FINAL_ANSWER, {"text": "42"}),
    )
    prompt = "\n".join(t._render_turns([turn]))
    assert "FINAL: 42" in prompt, prompt
