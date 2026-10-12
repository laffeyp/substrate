# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K296 live: the same question under each Length and Tone position, on a real model.

Opt-in (SUBSTRATE_LIVE_DRIVER_TESTS=1), like K293. The replies are printed for a reader; the only
assertion is the coarse one the texts promise: a `terse` reply is shorter than a `full` one.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import OllamaResponder
from substrate.topologies.session import UserMessage, session_topology

MODEL = "kimi-k2.7-code:cloud"
QUESTION = (
    "Should a small team write unit tests before or after the code? Answer for a team of three."
)

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("SUBSTRATE_LIVE_DRIVER_TESTS") != "1",
        reason="a real model call; run with SUBSTRATE_LIVE_DRIVER_TESTS=1",
    ),
    pytest.mark.timeout(900),
]


def _reply(root: Path, length: str, tone: str) -> str:
    um = UserMessage(text=QUESTION, turn_index=0, assembled_prompt="", slash_source="chat")
    topo = session_topology(
        driver=OllamaResponder(MODEL),
        driver_name=MODEL,
        driver_context_tokens=100_000,
        seed="",
        tools={},
        session_id="s_296_live",
        workspace_path=str(root.parent),
        first_turn_user_message=um,
        length=length,
        tone=tone,
    )
    asyncio.run(api.Runtime(root, persistent=True).run(topo, name="session"))
    events: list[dict[str, Any]] = list(api.read_record(root, resolve_blobs=True))
    replies = [
        e["payload"]["text"] for e in events if e["kind"] == "ModelReply" and e["payload"]["text"]
    ]
    return replies[-1]


def test_the_positions_change_the_reply(tmp_path: Path) -> None:
    cases = [("terse", "neutral"), ("full", "neutral"), ("normal", "blunt"), ("normal", "formal")]
    replies = {case: _reply(tmp_path / f"{case[0]}-{case[1]}", *case) for case in cases}
    for (length, tone), text in replies.items():
        print(f"\n===== length={length} tone={tone} ({len(text.split())} words)\n{text}")
    assert len(replies[("terse", "neutral")].split()) < len(replies[("full", "neutral")].split())
