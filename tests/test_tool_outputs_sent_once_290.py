# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K290: each tool output reaches the model once.

Before: within a turn, the history already rendered each ToolResult as a RESULT line, and the model
step appended the same outputs again under "Tool results so far" (native and text tool modes, and
the wrap-up prompt). Every tool output in the current turn was sent twice.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from substrate import api
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.tool_loop.tools import Tool

_MARKS = ("MARK-ALPHA-7f3c", "MARK-BRAVO-91d2")


def _probe(args: list[Any]) -> str:
    return _MARKS[int(args[0])] if args else _MARKS[0]


_PROBE = {
    "probe": Tool(
        "probe",
        "probe(i) -> a marker string",
        True,
        _probe,
        schema={"type": "object", "properties": {"i": {"type": "integer"}}, "required": ["i"]},
    )
}


class _TwoProbes:
    """A text-mode driver: probe(0), then probe(1), then an answer."""

    name = "two-probes"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, prompt: str) -> str:
        self.calls += 1
        if self.calls <= 2:
            return json.dumps({"name": "probe", "arguments": {"i": self.calls - 1}})
        return "done"


def test_each_tool_output_appears_once_in_later_prompts(tmp_path: Path) -> None:
    topo = session_topology(
        driver=_TwoProbes(),
        driver_name="two-probes",
        driver_context_tokens=100_000,
        seed="SEED",
        tools=dict(_PROBE),
        session_id="s290",
        workspace_path=str(tmp_path),
        first_turn_user_message=UserMessage(
            text="probe twice", turn_index=0, assembled_prompt="", slash_source="chat"
        ),
    )
    root = tmp_path / "rec"
    asyncio.run(api.Runtime(root).run(topo, name="session"))
    envs = list(api.read_record(root, resolve_blobs=True))
    results = [e for e in envs if e["kind"] == "ToolResult"]
    assert [r["payload"]["output"] for r in results] == list(_MARKS)
    prompts = [e["payload"]["text"] for e in envs if e["kind"] == "PromptComposed"]
    assert len(prompts) == 3
    assert all(m not in prompts[0] for m in _MARKS)
    assert prompts[1].count(_MARKS[0]) == 1 and _MARKS[1] not in prompts[1]
    assert prompts[2].count(_MARKS[0]) == 1 and prompts[2].count(_MARKS[1]) == 1
    assert all("Tool results so far" not in p for p in prompts)
