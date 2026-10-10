# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""tools_suite fragment source — sprint 064 tests, with K261's prompt order.

Verifies:
 - tools_suite: session with CALCULATOR tools emits one
   PromptFragment(source=tools_suite) at session open with tool names
   in text and provenance.
 - Precedence pin (20 for tools_suite).
 - The model's recorded prompt orders per_turn, the tool list, then the message (K261).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from substrate import api
from substrate.topologies.session.ci import ci_session_topology


def test_tools_suite_fragment_lands_at_session_open(tmp_path: Path) -> None:
    """CI session with CALCULATOR emits exactly one
    PromptFragment(source=tools_suite) whose text mentions the add/mul
    tools and whose provenance names them."""

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("hi", "/exit"),
            session_id="s_tools_suite",
        )
        await api.Runtime(tmp_path / "ci").run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "ci"))
    frags = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "tools_suite"
    ]
    assert len(frags) == 1, f"expected 1 tools_suite fragment, got {len(frags)}"
    payload = frags[0]["payload"]
    assert "add" in payload["text"]
    assert "mul" in payload["text"]
    assert payload["precedence"] == 20
    assert set(payload["provenance"]["tool_names"]) == {"add", "mul"}


def test_prompt_orders_per_turn_tools_then_message(tmp_path: Path) -> None:
    """K261: the model's recorded prompt on turn 1 holds per_turn (precedence 10), the tool list
    (20) and the user's message, in that order, each once."""

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("compose-me", "/exit"),
            session_id="s_prompt_order",
            per_turn="PT-LINE",
        )
        await api.Runtime(tmp_path / "ci").run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "ci"))
    composed = [e for e in envs if e.get("kind") == "PromptComposed"]
    assert composed, "no PromptComposed on the record"
    text = composed[0]["payload"]["text"]
    per_turn_pos, tools_pos, user_pos = (
        text.find("PT-LINE"),
        text.find("add("),
        text.find("compose-me"),
    )
    assert -1 not in (per_turn_pos, tools_pos, user_pos), text
    assert per_turn_pos < tools_pos < user_pos, text
    assert text.count("PT-LINE") == 1 and text.count("compose-me") == 1, text
