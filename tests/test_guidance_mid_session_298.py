# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 298 (session vocabulary § U): guidance changes mid-session as its bundle does, and
the history line names the levels, not the bundles.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from substrate import api
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.transcript import session_changed_line


class Capture:
    name = "capture"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def respond(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "ok"


def _turn(root: Path, text: str, turn_index: int, *, bundle: str) -> None:
    um = UserMessage(text=text, turn_index=turn_index, assembled_prompt="", slash_source="chat")
    topo = session_topology(
        driver=Capture(),
        driver_name="capture",
        driver_context_tokens=100_000,
        seed="SEED",
        tools={},
        session_id="s_298",
        workspace_path=str(root.parent),
        first_turn_user_message=um if turn_index == 0 else None,
        bundle=bundle,
    )
    rt = api.Runtime(root, persistent=True)
    if turn_index == 0:
        asyncio.run(rt.run(topo, name="session"))
    else:
        asyncio.run(rt.resume(topo, resume_event=um))


def _events(root: Path) -> list[dict[str, Any]]:
    return list(api.read_record(root, resolve_blobs=True))


def test_a_level_change_names_the_levels() -> None:
    line = session_changed_line("bundle", "standard", "standard-low")
    assert line == "Environment update: guidance changed from high to low."
    assert session_changed_line("bundle", "standard-small", "harness") == (
        "Environment update: guidance changed from low to harness."
    )


def test_other_changes_keep_their_lines() -> None:
    assert session_changed_line("bundle", "standard", "custom-team") == (
        "Environment update: bundle changed from standard to custom-team."
    )
    assert session_changed_line("tone", "neutral", "blunt") == (
        "Environment update: tone changed from neutral to blunt."
    )


def test_a_guidance_change_reaches_the_next_prompt_at_its_place(tmp_path: Path) -> None:
    root = tmp_path / "record"
    _turn(root, "FIRST", 0, bundle="standard")
    _turn(root, "SECOND", 1, bundle="standard-low")
    events = _events(root)
    # A level's bundle carries its own reminder line, so `per_turn` changes with it.
    changes = [e["payload"] for e in events if e["kind"] == "SessionChanged"]
    assert {"field": "bundle", "old": "standard", "new": "standard-low"} in changes
    text = [e["payload"]["text"] for e in events if e["kind"] == "PromptComposed"][-1]
    line = "Environment update: guidance changed from high to low."
    assert line in text
    # § P.4: the change is recorded at the first step of the turn it governs, so its line sits
    # beside that turn's message, after the earlier turns.
    assert text.index("FIRST") < text.index("SECOND") < text.index(line)
