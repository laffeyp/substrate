# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K274: the reminder line, and SessionChanged (session vocabulary § P.2, § P.4).

The reminder line (`per_turn`) is written once and sits right after the current message on every
step. When the session's driver, bundle, reminder line or date differ from the record, the turn's
first model step records a SessionChanged and tells the model beside the message; a changed bundle
or reminder line is written again, and later steps read the new text.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.tool_loop.tools import CALCULATOR

REMINDER = "REMINDER-LINE"


class Capture:
    """Calls `add` once on the first turn, then answers; records every prompt."""

    name = "capture"

    def __init__(self, replies: list[str]) -> None:
        self.prompts: list[str] = []
        self._replies = list(replies)

    def respond(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._replies.pop(0) if self._replies else "done"


def _bundle(home: Path, name: str, per_turn: str, methodology: str) -> None:
    b = home / "bundles" / name
    b.mkdir(parents=True)
    (b / "bundle.toml").write_text(f'[bundle]\nname = "{name}"\n', encoding="utf-8")
    (b / "per-turn.md").write_text(per_turn, encoding="utf-8")
    (b / "methodology.md").write_text(methodology, encoding="utf-8")


def _turn(
    root: Path,
    driver: Capture,
    text: str,
    turn_index: int,
    *,
    driver_name: str = "capture",
    bundle: str | None = None,
    per_turn: str = "",
    tools: dict[str, Any] | None = None,
) -> None:
    um = UserMessage(text=text, turn_index=turn_index, assembled_prompt="", slash_source="chat")
    topo = session_topology(
        driver=driver,
        driver_name=driver_name,
        driver_context_tokens=100_000,
        seed="SEED",
        per_turn=per_turn,
        tools=tools or {},
        session_id="s_274",
        workspace_path=str(root.parent),
        bundle=bundle,
        first_turn_user_message=um if turn_index == 0 else None,
    )
    rt = api.Runtime(root, persistent=True)
    if turn_index == 0:
        asyncio.run(rt.run(topo, name="session"))
    else:
        asyncio.run(rt.resume(topo, resume_event=um))


def _events(root: Path) -> list[dict[str, Any]]:
    return list(api.read_record(root, resolve_blobs=True))


def test_the_reminder_line_sits_after_the_message_on_every_step(tmp_path: Path) -> None:
    root = tmp_path / "record"
    driver = Capture(['{"name": "add", "arguments": {"a": 1, "b": 2}}', "three"])
    _turn(root, driver, "HELLO", 0, per_turn=REMINDER, tools=dict(CALCULATOR))
    assert len(driver.prompts) == 2
    for prompt in driver.prompts:
        assert prompt.count(REMINDER) == 1, prompt
        assert prompt.index("USER: HELLO") < prompt.index(REMINDER), prompt
        assert prompt.index("SEED") < prompt.index("USER: HELLO")
    frags = [e["payload"] for e in _events(root) if e["kind"] == "PromptFragment"]
    assert [(f["source"], f["provenance"]) for f in frags if f["source"] == "per_turn"] == [
        ("per_turn", {"from": "manifest"})
    ]


def test_a_bundle_supplies_the_reminder_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUBSTRATE_HOME", str(tmp_path / "home"))
    _bundle(tmp_path / "home", "b1", "B1-REMINDER", "B1-METHOD")
    driver = Capture(["hi"])
    _turn(tmp_path / "record", driver, "HELLO", 0, bundle="b1")
    (prompt,) = driver.prompts
    assert prompt.index("USER: HELLO") < prompt.index("B1-REMINDER")


def test_a_driver_change_is_recorded_and_told(tmp_path: Path) -> None:
    root = tmp_path / "record"
    driver = Capture(["one", "two"])
    _turn(root, driver, "FIRST", 0, driver_name="glm-5.2:cloud")
    _turn(root, driver, "SECOND", 1, driver_name="claude")
    changes = [e["payload"] for e in _events(root) if e["kind"] == "SessionChanged"]
    assert changes == [{"field": "driver", "old": "glm-5.2:cloud", "new": "claude"}]
    line = "Environment update: driver changed from glm-5.2:cloud to claude."
    second = driver.prompts[1]
    assert second.index("USER: SECOND") < second.index(line)
    assert line not in driver.prompts[0]


def test_no_change_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "record"
    driver = Capture(["one", "two"])
    _turn(root, driver, "FIRST", 0, per_turn=REMINDER)
    _turn(root, driver, "SECOND", 1, per_turn=REMINDER)
    assert not [e for e in _events(root) if e["kind"] == "SessionChanged"]


def test_a_bundle_change_writes_its_sources_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUBSTRATE_HOME", str(tmp_path / "home"))
    _bundle(tmp_path / "home", "b1", "B1-REMINDER", "B1-METHOD")
    _bundle(tmp_path / "home", "b2", "B2-REMINDER", "B2-METHOD")
    root = tmp_path / "record"
    driver = Capture(["one", "two", "three"])
    _turn(root, driver, "FIRST", 0, bundle="b1")
    _turn(root, driver, "SECOND", 1, bundle="b2")
    _turn(root, driver, "THIRD", 2, bundle="b2")
    events = _events(root)
    changes = [e["payload"] for e in events if e["kind"] == "SessionChanged"]
    # The bundle supplies the reminder line, so both changed, and both are recorded.
    assert changes == [
        {"field": "bundle", "old": "b1", "new": "b2"},
        {"field": "per_turn", "old": "B1-REMINDER", "new": "B2-REMINDER"},
    ]
    # The step that sees the change still reads b1's text; it says so beside the message.
    assert "B1-METHOD" in driver.prompts[1]
    assert "Environment update: bundle changed from b1 to b2." in driver.prompts[1]
    # The next turn reads b2's text only.
    third = driver.prompts[2]
    assert "B2-METHOD" in third and "B1-METHOD" not in third
    assert third.count("B2-REMINDER") == 1 and "B1-REMINDER" not in third
    regenerated = [
        e["payload"]
        for e in events
        if e["kind"] == "PromptFragment" and "generation" in e["payload"]["provenance"]
    ]
    # K296 (§ T.3): a rewritten source with no text writes one empty fragment, so a style the
    # old bundle had cannot outlive the change. Neither test bundle has a style.
    assert {f["source"] for f in regenerated} == {"bundle_methodology", "per_turn", "bundle_style"}
    cleared = [f for f in regenerated if f["source"] == "bundle_style"]
    assert [f["text"] for f in cleared] == [""] and cleared[0]["provenance"]["cleared"] is True
