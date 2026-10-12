# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K296: Length and Tone, two controls a session opens with (session vocabulary § T).

Each position other than the default writes one `control` fragment, on the system channel after
the bundle's style, with the control and position in its provenance. The defaults write nothing.
A change writes SessionChanged and the `control` source again; a change back to both defaults
writes an empty fragment, so the old text stops.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.session_prompt_producer import control_fragments
from substrate.topologies.session.vocabulary import (
    LENGTH_TEXTS,
    SESSION_OPEN_SOURCES,
    SYSTEM_SOURCES,
    TONE_TEXTS,
    LengthPosition,
    PromptSource,
    TonePosition,
)
from substrate.topologies.session_registry import SessionRegistry

TERSE = LENGTH_TEXTS[LengthPosition.TERSE]
BLUNT = TONE_TEXTS[TonePosition.BLUNT]
FORMAL = TONE_TEXTS[TonePosition.FORMAL]


class Capture:
    name = "capture"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def respond(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "ok"


def _turn(root: Path, text: str, turn_index: int, *, length: str | None, tone: str | None) -> None:
    um = UserMessage(text=text, turn_index=turn_index, assembled_prompt="", slash_source="chat")
    topo = session_topology(
        driver=Capture(),
        driver_name="capture",
        driver_context_tokens=100_000,
        seed="SEED",
        tools={},
        session_id="s_296",
        workspace_path=str(root.parent),
        first_turn_user_message=um if turn_index == 0 else None,
        length=length,
        tone=tone,
    )
    rt = api.Runtime(root, persistent=True)
    if turn_index == 0:
        asyncio.run(rt.run(topo, name="session"))
    else:
        asyncio.run(rt.resume(topo, resume_event=um))


def _events(root: Path) -> list[dict[str, Any]]:
    return list(api.read_record(root, resolve_blobs=True))


def test_each_position_writes_its_text_and_the_defaults_write_nothing() -> None:
    frags = control_fragments("terse", "blunt")
    assert [(f.source, f.text, f.provenance) for f in frags] == [
        ("control", TERSE, {"control": "length", "position": "terse"}),
        ("control", BLUNT, {"control": "tone", "position": "blunt"}),
    ]
    assert control_fragments("normal", "neutral") == []
    assert [f.text for f in control_fragments("full", "neutral")] == [
        LENGTH_TEXTS[LengthPosition.FULL]
    ]
    with pytest.raises(ValueError):
        control_fragments("warm", "neutral")
    assert PromptSource.CONTROL in SESSION_OPEN_SOURCES and PromptSource.CONTROL in SYSTEM_SOURCES


def test_a_session_opens_with_its_controls_on_the_system_channel(tmp_path: Path) -> None:
    root = tmp_path / "record"
    _turn(root, "HELLO", 0, length="terse", tone="blunt")
    events = _events(root)
    started = next(e["payload"] for e in events if e["kind"] == "SessionStarted")
    assert (started["length"], started["tone"]) == ("terse", "blunt")
    controls = [
        e["payload"]
        for e in events
        if e["kind"] == "PromptFragment" and e["payload"]["source"] == "control"
    ]
    assert [c["text"] for c in controls] == [TERSE, BLUNT]
    system = next(e["payload"]["system"] for e in events if e["kind"] == "PromptComposed")
    assert TERSE in system and BLUNT in system


def test_the_defaults_leave_the_prompt_as_it_was(tmp_path: Path) -> None:
    root = tmp_path / "record"
    _turn(root, "HELLO", 0, length="normal", tone="neutral")
    events = _events(root)
    assert not [
        e for e in events if e["kind"] == "PromptFragment" and e["payload"]["source"] == "control"
    ]


def test_a_change_is_recorded_and_the_new_text_replaces_the_old(tmp_path: Path) -> None:
    root = tmp_path / "record"
    _turn(root, "FIRST", 0, length="terse", tone="blunt")
    _turn(root, "SECOND", 1, length="terse", tone="formal")
    _turn(root, "THIRD", 2, length="terse", tone="formal")
    events = _events(root)
    changes = [e["payload"] for e in events if e["kind"] == "SessionChanged"]
    assert changes == [{"field": "tone", "old": "blunt", "new": "formal"}]
    systems = [e["payload"]["system"] for e in events if e["kind"] == "PromptComposed"]
    # K299 (§ V): the message on which the change is recorded (SECOND) reads the new text.
    assert FORMAL in systems[1] and TERSE in systems[1] and BLUNT not in systems[1]
    assert FORMAL in systems[-1] and TERSE in systems[-1] and BLUNT not in systems[-1]


def test_a_change_back_to_the_defaults_clears_the_text(tmp_path: Path) -> None:
    root = tmp_path / "record"
    _turn(root, "FIRST", 0, length="terse", tone="neutral")
    _turn(root, "SECOND", 1, length="normal", tone="neutral")
    _turn(root, "THIRD", 2, length="normal", tone="neutral")
    events = _events(root)
    last_system = [e["payload"]["system"] for e in events if e["kind"] == "PromptComposed"][-1]
    assert TERSE not in last_system
    cleared = [
        e["payload"]
        for e in events
        if e["kind"] == "PromptFragment"
        and e["payload"]["source"] == "control"
        and e["payload"]["text"] == ""
    ]
    assert len(cleared) == 1 and cleared[0]["provenance"].get("cleared") is True


def test_the_registry_holds_the_positions_and_refuses_unknown_ones(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path / "sessions")
    m = reg.create(
        session_id="s_a",
        name=None,
        driver="deterministic",
        workspace=str(tmp_path),
        workspace_shape="flat",
        bundle=None,
        seed="",
        length="full",
        tone="dry",
    )
    assert (m.length, m.tone) == ("full", "dry")
    assert (reg.set_controls("s_a", length="terse", tone=None).length) == "terse"
    with pytest.raises(ValueError):
        reg.set_controls("s_a", length="enormous", tone=None)
    with pytest.raises(ValueError):
        reg.create(
            session_id="s_b",
            name=None,
            driver="deterministic",
            workspace=str(tmp_path),
            workspace_shape="flat",
            bundle=None,
            seed="",
            tone="warm",
        )
