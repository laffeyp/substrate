# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 300 (postmortem 2026-10-12, roadmap round 2): a mid-session change reaches the
prompt for the message on which it is recorded.

Each test changes a setting between two messages and reads what the driver received for the second
one, the prompt the postmortem found still holding the old text. Written before K299 as its red.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.vocabulary import (
    LENGTH_TEXTS,
    TONE_TEXTS,
    LengthPosition,
    TonePosition,
)

TERSE = LENGTH_TEXTS[LengthPosition.TERSE]
FULL = LENGTH_TEXTS[LengthPosition.FULL]
FORMAL = TONE_TEXTS[TonePosition.FORMAL]
BLUNT = TONE_TEXTS[TonePosition.BLUNT]


class Capture:
    """Records each prompt it is sent. It has no system channel, so the system text arrives
    folded into the prompt, as K274's tests read it."""

    name = "capture"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def respond(self, prompt: str) -> str:
        self.calls.append((prompt, ""))
        return "ok"


def _bundle(home: Path, name: str, per_turn: str, methodology: str) -> None:
    b = home / "bundles" / name
    b.mkdir(parents=True)
    (b / "bundle.toml").write_text(f'[bundle]\nname = "{name}"\n', encoding="utf-8")
    (b / "per-turn.md").write_text(per_turn, encoding="utf-8")
    (b / "methodology.md").write_text(methodology, encoding="utf-8")


def _turn(root: Path, driver: Capture, text: str, turn_index: int, **settings: Any) -> None:
    slash = settings.pop("slash_source", "chat")
    um = UserMessage(text=text, turn_index=turn_index, assembled_prompt="", slash_source=slash)
    topo = session_topology(
        driver=driver,
        driver_name="capture",
        driver_context_tokens=100_000,
        seed="SEED",
        tools={},
        session_id="s_300",
        workspace_path=str(root.parent),
        first_turn_user_message=um if turn_index == 0 else None,
        **settings,
    )
    rt = api.Runtime(root, persistent=True)
    if turn_index == 0:
        asyncio.run(rt.run(topo, name="session"))
    else:
        asyncio.run(rt.resume(topo, resume_event=um))


def _events(root: Path) -> list[dict[str, Any]]:
    return list(api.read_record(root, resolve_blobs=True))


def _whole(call: tuple[str, str]) -> str:
    return call[1] + "\n" + call[0]


def test_a_length_change_reaches_the_next_message(tmp_path: Path) -> None:
    root, driver = tmp_path / "record", Capture()
    _turn(root, driver, "FIRST", 0, length="terse", tone="neutral")
    _turn(root, driver, "SECOND", 1, length="full", tone="neutral")
    second = _whole(driver.calls[-1])
    assert FULL in second and TERSE not in second
    assert "Environment update: length changed from terse to full." in second


def test_a_tone_change_reaches_the_next_message(tmp_path: Path) -> None:
    root, driver = tmp_path / "record", Capture()
    _turn(root, driver, "FIRST", 0, length="normal", tone="formal")
    _turn(root, driver, "SECOND", 1, length="normal", tone="blunt")
    second = _whole(driver.calls[-1])
    assert BLUNT in second and FORMAL not in second


def test_length_and_tone_together(tmp_path: Path) -> None:
    root, driver = tmp_path / "record", Capture()
    _turn(root, driver, "FIRST", 0, length="terse", tone="formal")
    _turn(root, driver, "SECOND", 1, length="full", tone="blunt")
    second = _whole(driver.calls[-1])
    assert FULL in second and BLUNT in second
    assert TERSE not in second and FORMAL not in second


def test_a_bundle_change_reaches_the_next_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUBSTRATE_HOME", str(tmp_path / "home"))
    _bundle(tmp_path / "home", "b1", "B1-REMINDER", "B1-METHOD")
    _bundle(tmp_path / "home", "b2", "B2-REMINDER", "B2-METHOD")
    root, driver = tmp_path / "record", Capture()
    _turn(root, driver, "FIRST", 0, bundle="b1")
    _turn(root, driver, "SECOND", 1, bundle="b2")
    second = _whole(driver.calls[-1])
    assert "B2-METHOD" in second and "B1-METHOD" not in second
    assert second.count("B2-REMINDER") == 1 and "B1-REMINDER" not in second


def test_a_reminder_line_change_reaches_the_next_message(tmp_path: Path) -> None:
    root, driver = tmp_path / "record", Capture()
    _turn(root, driver, "FIRST", 0, per_turn="OLD-REMINDER")
    _turn(root, driver, "SECOND", 1, per_turn="NEW-REMINDER")
    second = _whole(driver.calls[-1])
    assert "NEW-REMINDER" in second and "OLD-REMINDER" not in second


def test_the_turn_reads_message_change_text_prompt_reply(tmp_path: Path) -> None:
    root, driver = tmp_path / "record", Capture()
    _turn(root, driver, "FIRST", 0, length="terse", tone="neutral")
    calls_before = len(driver.calls)
    _turn(root, driver, "SECOND", 1, length="full", tone="neutral")
    events = _events(root)
    second = max(i for i, e in enumerate(events) if e["kind"] == "UserMessage")
    kinds = [e["kind"] for e in events[second:]]
    wanted = ["UserMessage", "SessionChanged", "PromptFragment", "PromptComposed", "ModelReply"]
    seen = [k for k in kinds if k in wanted]
    order = [seen.index(k) for k in wanted]
    assert order == sorted(order), seen
    assert len(driver.calls) == calls_before + 1


def test_a_skill_message_after_a_change(tmp_path: Path) -> None:
    root, driver = tmp_path / "record", Capture()
    _turn(root, driver, "FIRST", 0, length="terse", tone="neutral")
    _turn(
        root, driver, "rewrite this", 1, length="full", tone="neutral", slash_source="skill:dellm"
    )
    second = _whole(driver.calls[-1])
    assert FULL in second and TERSE not in second
    assert any(
        e["kind"] == "PromptFragment" and e["payload"]["source"] == "skill" for e in _events(root)
    )
