# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 207 — no TranscriptCompacted fires when K covers the whole record.

Cadence rule per TECH-SPEC §3a and vocabulary-lock §F #6: TranscriptCompacted
fires only when `turns_dropped > 0`. K >= len(turns) short-circuits; the render
returns an empty `compaction_events` list.
"""

from __future__ import annotations

from typing import Any

import pytest

from substrate.topologies.session.transcript import render_transcript


def _envelope(seq: int, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": seq,
        "kind": kind,
        "payload": payload,
        "schema": kind,
        "t": 0.0,
        "producer": None,
    }


def _three_turns() -> list[dict[str, Any]]:
    events = [_envelope(0, "substrate.RunStarted", {})]
    seq = 1
    for turn_index in range(3):
        events.append(
            _envelope(
                seq,
                "UserMessage",
                {
                    "text": f"hi {turn_index}",
                    "turn_index": turn_index,
                    "assembled_prompt": f"h{turn_index}",
                },
            )
        )
        seq += 1
        events.append(
            _envelope(
                seq, "ModelReply", {"text": "ok", "turn_index": turn_index, "model_usage": {}}
            )
        )
        seq += 1
    return events


def test_no_compaction_when_k_covers_all_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    events = _three_turns()
    monkeypatch.setattr(
        "substrate.topologies.session.transcript.read_record", lambda root, **_kw: iter(events)
    )
    # driver_context_tokens=200_000; K well above 3.
    result = render_transcript(
        record_root="/nowhere",
        seed="",
        per_turn="",
        driver_context_tokens=200_000,
        turn_index_now=3,
    )
    assert result.turns_dropped == 0
    assert result.compaction_events == []
    assert result.threaded_from_turn == 0
    for turn_index in range(3):
        assert f"h{turn_index}" in result.prompt_text


def test_no_compaction_on_empty_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "substrate.topologies.session.transcript.read_record", lambda root, **_kw: iter([])
    )
    result = render_transcript(
        record_root="/nowhere",
        seed="seed line",
        per_turn="",
        driver_context_tokens=4096,
        turn_index_now=0,
    )
    assert result.turns_dropped == 0
    assert result.compaction_events == []
    assert result.threaded_from_turn == 0
    assert result.prompt_text.startswith("seed line")


def test_no_compaction_on_single_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        {
            "seq": 0,
            "kind": "substrate.RunStarted",
            "payload": {},
            "schema": "substrate.RunStarted",
            "t": 0.0,
            "producer": None,
        },
        {
            "seq": 1,
            "kind": "UserMessage",
            "payload": {"text": "hi", "turn_index": 0, "assembled_prompt": "hi"},
            "schema": "UserMessage",
            "t": 0.0,
            "producer": None,
        },
    ]
    monkeypatch.setattr(
        "substrate.topologies.session.transcript.read_record", lambda root, **_kw: iter(events)
    )
    result = render_transcript(
        record_root="/nowhere",
        seed="",
        per_turn="",
        driver_context_tokens=200_000,
        turn_index_now=0,
    )
    assert result.turns_dropped == 0
    assert result.compaction_events == []
