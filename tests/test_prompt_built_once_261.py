# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K261: the model gets one prompt per call, in a plain order, and the record holds those bytes.

Before: the composed prompt (ending in the user's message) was prepended to the rendered
transcript (seed, then every turn including the current one), so the user's text reached the
model twice and ahead of the seed; tool lists and results were appended after that; and the
record's PromptComposed held only the first part. A capture responder records every prompt the
driver gets and the test compares each to the record.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from substrate import api
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.tool_loop.tools import CALCULATOR

SEED = "SEED-TEXT"
PER_TURN = "PER-TURN-TEXT"


class Capture:
    """Answers with a tool call once, then plainly; records every prompt."""

    name = "capture"

    def __init__(self, replies: list[str]) -> None:
        self.prompts: list[str] = []
        self._replies = list(replies)

    def respond(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._replies.pop(0) if self._replies else "done"


def _run(root: Path, driver: Capture, text: str, turn_index: int, tools: dict[str, Any]) -> None:
    um = UserMessage(text=text, turn_index=turn_index, assembled_prompt="", slash_source="chat")
    topo = session_topology(
        driver=driver,
        driver_name="capture",
        driver_context_tokens=100_000,
        seed=SEED,
        per_turn=PER_TURN,
        tools=tools,
        session_id="s_261",
        workspace_path=str(root.parent),
        first_turn_user_message=um if turn_index == 0 else None,
    )
    rt = api.Runtime(root, persistent=True)
    if turn_index == 0:
        asyncio.run(rt.run(topo, name="session"))
    else:
        asyncio.run(rt.resume(topo, resume_event=um))


def _composed(root: Path) -> list[str]:
    return [
        e["payload"]["text"]
        for e in api.read_record(root, resolve_blobs=True)
        if e["kind"] == "PromptComposed"
    ]


def test_one_prompt_per_call_seed_first_message_once_and_on_the_record(tmp_path: Path) -> None:
    root = tmp_path / "record"
    driver = Capture(["first answer", "second answer"])
    _run(root, driver, "HELLO-ONE", 0, {})
    _run(root, driver, "HELLO-TWO", 1, {})
    assert len(driver.prompts) == 2
    first, second = driver.prompts
    assert first.count("HELLO-ONE") == 1, first
    assert first.index(SEED) < first.index(PER_TURN) < first.index("HELLO-ONE"), first
    assert second.count("HELLO-ONE") == 1 and second.count("HELLO-TWO") == 1, second
    assert second.count("first answer") == 1, second
    assert second.index("HELLO-ONE") < second.index("first answer") < second.index("HELLO-TWO")
    assert second.count(PER_TURN) == 1, second
    assert _composed(root) == driver.prompts


def test_each_step_of_a_tool_turn_is_on_the_record(tmp_path: Path) -> None:
    root = tmp_path / "record"
    driver = Capture(['{"name": "add", "arguments": {"a": 2, "b": 3}}', "It is 5."])
    _run(root, driver, "ADD-2-3", 0, CALCULATOR)
    assert len(driver.prompts) == 2, driver.prompts
    assert _composed(root) == driver.prompts
    tool_step = driver.prompts[1]
    assert tool_step.count("ADD-2-3") == 1, tool_step
    assert tool_step.count("RESULT: 5") == 1, tool_step
    # K267: the model step's input is the recorded form, so no prompt shows sealed types.
    assert not any("mappingproxy" in p for p in driver.prompts), driver.prompts


def test_the_first_prompt_of_a_new_session_has_its_session_pieces(tmp_path: Path) -> None:
    """The first model call of a fresh session must see the session-open fragments (the tool
    list here). Before the fix the first message started the model before the fragment producers
    had written, and the first prompt went out without the tool list (diff against pre-K261)."""
    root = tmp_path / "record"
    driver = Capture(["It is 5."])
    _run(root, driver, "ADD-2-3", 0, CALCULATOR)
    assert "add(a, b)" in driver.prompts[0], driver.prompts[0]
    kinds = [e["kind"] for e in api.read_record(root)]
    assert kinds.index("PromptFragment") < kinds.index("UserMessage"), kinds


def test_a_resume_never_writes_a_second_first_message(tmp_path: Path) -> None:
    """The first-message trigger fires only on a fresh record. A topology rebuilt for a later
    turn with a first message configured (as a caller may do) must not inject it again: an
    initial never re-runs on resume, and the trigger that replaced it must not either."""
    root = tmp_path / "record"
    driver = Capture(["one", "two"])
    _run(root, driver, "FIRST", 0, CALCULATOR)
    um = UserMessage(text="SECOND", turn_index=1, assembled_prompt="", slash_source="chat")
    topo = session_topology(
        driver=driver,
        driver_name="capture",
        driver_context_tokens=100_000,
        seed=SEED,
        per_turn=PER_TURN,
        tools=CALCULATOR,
        session_id="s_261",
        workspace_path=str(root.parent),
        first_turn_user_message=UserMessage(
            text="FIRST", turn_index=0, assembled_prompt="", slash_source="chat"
        ),
    )
    asyncio.run(api.Runtime(root, persistent=True).resume(topo, resume_event=um))
    texts = [e["payload"]["text"] for e in api.read_record(root) if e["kind"] == "UserMessage"]
    assert texts == ["FIRST", "SECOND"], texts
