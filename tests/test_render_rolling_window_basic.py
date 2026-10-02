# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 207 — rolling-window renderer keeps K most recent turns.

Ten synthetic turns, K forced to 5 via a small `driver_context_tokens`. The last
five turns land in the prompt; the first five drop into a `TranscriptCompacted`
whose `dropped_seq_range` spans exactly the dropped seqs. `kept_seq_start` names
the seq of the first kept turn's `UserMessage`.
"""

from __future__ import annotations

from typing import Any

import pytest

from substrate.topologies.session.transcript import (
    _compute_k,
    render_transcript,
)


def _envelope(seq: int, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": seq,
        "kind": kind,
        "payload": payload,
        "schema": kind,
        "t": 0.0,
        "producer": None,
    }


def _ten_turns() -> list[dict[str, Any]]:
    events = [
        _envelope(0, "substrate.RunStarted", {}),
        _envelope(1, "SessionStarted", {"session_id": "s", "seed": "x"}),
    ]
    seq = 2
    for turn_index in range(10):
        events.append(
            _envelope(
                seq,
                "UserMessage",
                {
                    "text": f"user {turn_index}",
                    "turn_index": turn_index,
                    "assembled_prompt": f"u{turn_index}",
                },
            )
        )
        seq += 1
        events.append(
            _envelope(
                seq,
                "ModelReply",
                {"text": f"reply {turn_index}", "turn_index": turn_index, "model_usage": {}},
            )
        )
        seq += 1
        events.append(_envelope(seq, "FinalAnswer", {"text": f"final {turn_index}", "steps": 1}))
        seq += 1
        events.append(
            _envelope(
                seq,
                "Park",
                {"awaiting": "UserMessage", "turn_index": turn_index, "reason": "final_answer"},
            )
        )
        seq += 1
    return events


def test_k_five_keeps_last_five_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    events = _ten_turns()
    monkeypatch.setattr(
        "substrate.topologies.session.transcript.read_record", lambda root, **_kw: iter(events)
    )
    # Force K = 5. `_compute_k` uses avg_turn_tokens=800; a budget of 4000 tokens
    # divides to 5. driver_context_tokens * 0.6 = 4000 → driver_context_tokens = 6666.
    k = _compute_k(driver_context_tokens=6667, seed_tokens=0, per_turn_tokens=0)
    assert k == 5
    result = render_transcript(
        record_root="/nowhere",
        seed="",
        per_turn="",
        driver_context_tokens=6667,
        turn_index_now=10,
    )
    assert result.turns_dropped == 5
    assert len(result.compaction_events) == 1
    comp = result.compaction_events[0]
    assert comp.strategy == "rolling_window"
    assert comp.reason == "driver_window_exceeded"
    # Dropped turns are turn_index 0..4 (each 4 events wide starting at seq 2).
    # First dropped event: turn 0's UserMessage at seq 2. Last dropped event: turn 4's Park at seq 21.
    assert comp.dropped_seq_range == (2, 21)
    # Kept turns are turn_index 5..9. First kept event is turn 5's UserMessage at seq 22.
    assert comp.kept_seq_start == 22
    assert result.threaded_from_turn == 5


def test_prompt_lines_reflect_kept_turns_only(monkeypatch: pytest.MonkeyPatch) -> None:
    events = _ten_turns()
    monkeypatch.setattr(
        "substrate.topologies.session.transcript.read_record", lambda root, **_kw: iter(events)
    )
    # driver_context_tokens=8000 leaves K=5 even with the seed cost
    # (headroom 4800 - seed_tokens 4 = 4796; 4796 // 800 = 5).
    result = render_transcript(
        record_root="/nowhere",
        seed="you are a companion",
        per_turn="",
        driver_context_tokens=8000,
        turn_index_now=10,
    )
    for dropped_turn_idx in range(5):
        assert f"user {dropped_turn_idx}" not in result.prompt_text
    for kept_turn_idx in range(5, 10):
        assert f"u{kept_turn_idx}" in result.prompt_text
        assert f"reply {kept_turn_idx}" in result.prompt_text
    assert "you are a companion" in result.prompt_text
    assert "[transcript: turns 5..9]" in result.prompt_text


def test_dropped_range_is_contiguous_and_strictly_below_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _ten_turns()
    monkeypatch.setattr(
        "substrate.topologies.session.transcript.read_record", lambda root, **_kw: iter(events)
    )
    result = render_transcript(
        record_root="/nowhere",
        seed="",
        per_turn="",
        driver_context_tokens=6667,
        turn_index_now=10,
    )
    comp = result.compaction_events[0]
    assert comp.dropped_seq_range[0] <= comp.dropped_seq_range[1] < comp.kept_seq_start
