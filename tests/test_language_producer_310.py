# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 310: the `language` producer measures each turn between its final reply and
Returned (session vocabulary v0.11 § W). Written before the producer existed."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from substrate import api, app
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session import vocabulary as v


class Scripted:
    """Answers from a function of the call count."""

    name = "scripted"

    def __init__(self, reply: Callable[[int], str]) -> None:
        self.reply, self.n = reply, 0

    def respond(self, prompt: str) -> str:
        text = self.reply(self.n)
        self.n += 1
        return text


def _turn(root: Path, driver: Any, text: str, turn: int, *, language: bool = True) -> None:
    um = UserMessage(text=text, turn_index=turn, assembled_prompt="", slash_source="chat")
    topo = session_topology(
        driver=driver,
        driver_name="scripted",
        driver_context_tokens=100_000,
        seed="SEED",
        tools={},
        session_id="s_310",
        workspace_path=str(root.parent),
        first_turn_user_message=um if turn == 0 else None,
        language=language,
    )
    rt = api.Runtime(root, persistent=True)
    asyncio.run(rt.run(topo, name="session") if turn == 0 else rt.resume(topo, resume_event=um))


def _events(root: Path) -> list[dict[str, Any]]:
    return list(api.read_record(root, resolve_blobs=True))


REPLIES = ["The service listens on port 8080. The config sets it.", "The host is localhost."]


def test_the_turn_is_measured_before_it_returns(tmp_path: Path) -> None:
    root = tmp_path / "record"
    driver = Scripted(lambda n: REPLIES[n])
    _turn(root, driver, "What port does it use?", 0)
    _turn(root, driver, "And the host?", 1)
    events = _events(root)
    for turn in (0, 1):
        reply = next(
            e for e in events if e["kind"] == v.MODEL_REPLY and e["payload"]["turn_index"] == turn
        )
        returned = next(
            e for e in events if e["kind"] == v.RETURNED and e["payload"]["turn_index"] == turn
        )
        between = [e for e in events if reply["seq"] < e["seq"] < returned["seq"]]
        profiles = [e["payload"] for e in between if e["kind"] == v.LANGUAGE_PROFILE]
        assert [(p["stream"], p["pairing"]) for p in profiles] == [
            ("user", None),
            ("model", None),
            ("relation", "final"),
            ("relation", "turn"),
        ]
        assert all(p["turn_index"] == turn for p in profiles)
    # The turn is returned by return-on-language alone: a return-on-reply firing beside it would race
    # the measurement, and the pause on Returned would cancel whatever was left of it.
    fired = [e["payload"]["trigger_id"] for e in events if e["kind"] == api.TRIGGER_FIRED]
    assert v.TRIGGER_ID_RETURN_ON_REPLY not in fired
    assert fired.count(v.TRIGGER_ID_RETURN_ON_LANGUAGE) == 2
    assert sum(1 for e in events if e["kind"] == v.RETURNED) == 2


def test_live_values_equal_the_command(tmp_path: Path) -> None:
    root = tmp_path / "record"
    driver = Scripted(lambda n: REPLIES[n])
    _turn(root, driver, "What port does it use?", 0)
    _turn(root, driver, "And the host?", 1)
    lines = list(app.language_lines(root))
    by_seq = {(x["seq"], x["stream"]): x for x in lines if x["stream"] in ("user", "model")}
    live = [e for e in _events(root) if e["kind"] == v.LANGUAGE_PROFILE]
    for e in live:
        p = e["payload"]
        if p["stream"] == "relation":
            line = next(
                x
                for x in lines
                if x["stream"] == "relation"
                and x["turn"] == p["turn_index"]
                and x["pairing"] == p["pairing"]
            )
            assert {k: line["values"][k] for k in p["measures"]} == p["measures"]
        else:
            line = by_seq[(p["source_seq"], p["stream"])]
            assert line["values"]["text"] == p["measures"]
        assert p["instrument_sha256"] == lines[0]["instrument_sha256"]


def test_language_off_records_no_language_event(tmp_path: Path) -> None:
    root = tmp_path / "record"
    _turn(root, Scripted(lambda n: REPLIES[n]), "What port does it use?", 0, language=False)
    kinds = {e["kind"] for e in _events(root)}
    assert v.LANGUAGE_PROFILE not in kinds and v.RETURNED in kinds


def test_a_failed_measurement_still_returns_the_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import substrate.topologies.session.language_producer as lp

    def broken(*_: Any, **__: Any) -> Any:
        raise RuntimeError("measure failed")

    monkeypatch.setattr(lp, "profile", broken)
    root = tmp_path / "record"
    _turn(root, Scripted(lambda n: REPLIES[n]), "What port does it use?", 0)
    events = _events(root)
    failed = [e for e in events if e["kind"] == api.PRODUCER_FAILED]
    assert failed and "measure failed" in str(failed[0]["payload"])
    assert any(e["kind"] == v.RETURNED for e in events)


def test_a_jump_in_reply_length_is_a_drift(tmp_path: Path) -> None:
    short = ["One two three four five.", "One two three four five six.", "One two three four."]
    long_reply = " ".join(["This reply is much longer than every reply before it."] * 6)
    root = tmp_path / "record"
    driver = Scripted(lambda n: short[n % 3] if n < 22 else long_reply)
    for turn in range(26):
        _turn(root, driver, f"Question {turn}?", turn)
    drifts = [e for e in _events(root) if e["kind"] == v.LANGUAGE_DRIFT]
    words = [
        e["payload"]
        for e in drifts
        if e["payload"]["measure"] == "words" and e["payload"]["stream"] == "model"
    ]
    assert words and words[0]["direction"] == "up"
    jump = next(
        e["seq"]
        for e in _events(root)
        if e["kind"] == v.MODEL_REPLY and e["payload"]["turn_index"] == 22
    )
    assert words[0]["source_seq"] == jump


def test_a_model_error_turn_is_not_measured(tmp_path: Path) -> None:
    def fail(n: int) -> str:
        raise RuntimeError("driver down")

    root = tmp_path / "record"
    _turn(root, Scripted(fail), "What port does it use?", 0)
    kinds = [e["kind"] for e in _events(root)]
    assert v.LANGUAGE_PROFILE not in kinds and v.RETURNED in kinds
