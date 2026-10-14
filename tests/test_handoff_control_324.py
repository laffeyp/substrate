# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 324: the handoff control (session vocabulary § Y). How readily the model hands
work to a topology, set like length and tone, changed mid-session, and measured from the record as
topology calls per turn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from substrate.cli import main
from substrate.topologies.session.handoff import handoff_calls
from substrate.topologies.session.session_prompt_producer import control_fragments
from substrate.topologies.session.vocabulary import HANDOFF_TEXTS, HandoffPosition
from substrate.topologies.session_registry import SessionRegistry

from test_changes_reach_next_prompt_300 import Capture, _events, _turn, _whole

RARE = HANDOFF_TEXTS[HandoffPosition.RARE]
EAGER = HANDOFF_TEXTS[HandoffPosition.EAGER]


def test_each_position_writes_its_text_and_the_default_writes_none() -> None:
    assert control_fragments("normal", "neutral", "normal") == []
    (rare,) = control_fragments("normal", "neutral", "rare")
    assert rare.text == RARE and rare.provenance == {"control": "handoff", "position": "rare"}
    (eager,) = control_fragments("normal", "neutral", "eager")
    assert eager.text == EAGER
    with pytest.raises(ValueError):
        control_fragments("normal", "neutral", "sometimes")


def test_the_registry_keeps_and_refuses_positions(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path / "s", session_topology_factory=lambda *a: None)
    common: dict[str, Any] = dict(
        name=None,
        driver="d",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="",
    )
    m = reg.create(session_id="s_1", handoff="eager", **common)
    assert m.handoff == "eager"
    assert SessionRegistry(base=tmp_path / "s").get("s_1").handoff == "eager"  # on disk
    assert reg.set_controls("s_1", length=None, tone=None, handoff="rare").handoff == "rare"
    with pytest.raises(ValueError, match="handoff must be one of"):
        reg.create(session_id="s_2", handoff="sometimes", **common)


def test_the_session_opens_with_it_and_a_change_reaches_the_next_message(tmp_path: Path) -> None:
    root, driver = tmp_path / "record", Capture()
    _turn(root, driver, "FIRST", 0, length="normal", tone="neutral", handoff="rare")
    assert RARE in _whole(driver.calls[-1])
    _turn(root, driver, "SECOND", 1, length="normal", tone="neutral", handoff="eager")
    second = _whole(driver.calls[-1])
    assert EAGER in second and RARE not in second
    assert "Environment update: handoff changed from rare to eager." in second
    events = _events(root)
    started = next(e["payload"] for e in events if e["kind"] == "SessionStarted")
    assert started["handoff"] == "rare"
    changed = [e["payload"] for e in events if e["kind"] == "SessionChanged"]
    assert {"field": "handoff", "old": "rare", "new": "eager"} in changed


def _ev(kind: str, **payload: Any) -> dict[str, Any]:
    return {"kind": kind, "payload": payload}


def test_topology_calls_are_counted_per_turn_with_the_position() -> None:
    events = [
        _ev("SessionStarted", handoff="rare", driver_model="m1"),
        _ev("UserMessage", turn_index=0),
        _ev("ToolCall", tool="read_file"),
        _ev("UserMessage", turn_index=1),
        _ev("SessionChanged", field="handoff", old="rare", new="eager"),
        _ev("ToolCall", tool="delegate"),
        _ev("ToolCall", tool="review"),
        _ev("ToolCall", tool="build"),
    ]
    assert handoff_calls(events) == [
        {"turn": 0, "position": "rare", "model": "m1", "calls": 0, "tools": []},
        {
            "turn": 1,
            "position": "eager",
            "model": "m1",
            "calls": 3,
            "tools": ["delegate", "review", "build"],
        },
    ]


def test_the_command_prints_a_line_per_turn(tmp_path: Path) -> None:
    root, driver = tmp_path / "record", Capture()
    _turn(root, driver, "FIRST", 0, length="normal", tone="neutral", handoff="eager")
    result = CliRunner().invoke(main, ["handoff", str(root)])
    assert result.exit_code == 0, result.output
    (line,) = [json.loads(x) for x in result.stdout.splitlines() if x.startswith("{")]
    assert line == {"turn": 0, "position": "eager", "model": "capture", "calls": 0, "tools": []}
