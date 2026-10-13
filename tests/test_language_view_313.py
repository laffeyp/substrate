# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 313: the language view on a built record with a length change and a jump."""

from __future__ import annotations

import asyncio
import statistics
from pathlib import Path
from typing import Any

from substrate import api, app
from substrate.language.drift import DEFAULT_DRIFT
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session import vocabulary as v

SHORT = ["One two three four five.", "One two three four five six.", "One two three four."]
LONG = " ".join(["This reply is much longer than every reply before it."] * 6)


class Scripted:
    name = "scripted"

    def __init__(self) -> None:
        self.n = 0

    def respond(self, prompt: str) -> str:
        text = SHORT[self.n % 3] if self.n < 22 else LONG
        self.n += 1
        return text


def _turn(root: Path, driver: Any, turn: int, *, language: bool, length: str) -> None:
    um = UserMessage(
        text=f"Question {turn}?", turn_index=turn, assembled_prompt="", slash_source="chat"
    )
    topo = session_topology(
        driver=driver,
        driver_name="scripted",
        driver_context_tokens=100_000,
        seed="SEED",
        tools={},
        session_id="s_313",
        workspace_path=str(root.parent),
        first_turn_user_message=um if turn == 0 else None,
        language=language,
        length=length,
        tone="neutral",
    )
    rt = api.Runtime(root, persistent=True)
    asyncio.run(rt.run(topo, name="session") if turn == 0 else rt.resume(topo, resume_event=um))


def _record(tmp_path: Path, *, language: bool = True) -> Path:
    root, driver = tmp_path / "record", Scripted()
    for turn in range(26):
        _turn(root, driver, turn, language=language, length="normal" if turn < 22 else "full")
    return root


def test_warm_up_mean_sd_and_deviations(tmp_path: Path) -> None:
    view = app.language_view(_record(tmp_path))
    lane = view["lanes"]["model"]["words"]
    values = [p["value"] for p in lane["points"]]
    assert len(values) == 26 and lane["warmup_span"] == DEFAULT_DRIFT.warmup
    assert lane["mean"] == statistics.fmean(values[:20]) and lane["sd"] == statistics.stdev(
        values[:20]
    )
    for p in lane["points"]:
        assert p["deviation"] == (p["value"] - lane["mean"]) / lane["sd"]


def test_shifts_and_changes_carry_their_turns(tmp_path: Path) -> None:
    root = _record(tmp_path)
    view = app.language_view(root)
    drifts = [e for e in api.read_record(root) if e["kind"] == v.LANGUAGE_DRIFT]
    assert [s["seq"] for s in view["shifts"]] == [e["seq"] for e in drifts]
    words = next(s for s in view["shifts"] if s["measure"] == "words" and s["stream"] == "model")
    assert words["turn"] == 22 and words["direction"] == "up"
    length = [c for c in view["changes"] if c["field"] == v.Control.LENGTH]
    assert [(c["turn"], c["old"], c["new"]) for c in length] == [(22, "normal", "full")]


def test_a_count_window_reads_per_text(tmp_path: Path) -> None:
    lane = app.language_view(_record(tmp_path))["lanes"]["model"]["words"]
    # Every reply before the jump is 4-6 words, so the window average stays in that range.
    assert all(4 <= p["window"] <= 6 for p in lane["points"][:22])


def test_a_record_without_language_events(tmp_path: Path) -> None:
    view = app.language_view(_record(tmp_path, language=False))
    assert view["shifts"] == [] and len(view["lanes"]["user"]["words"]["points"]) == 26
