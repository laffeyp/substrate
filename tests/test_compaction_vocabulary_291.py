# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K291: TranscriptCompacted v0.7 (session vocabulary § S.4).

A record written before v0.7 still decodes, with nothing cleared and a scale of 1.0; the new fields
round-trip; the strategy and reason values are the vocabulary's constants.
"""

from __future__ import annotations

import msgspec

from substrate.topologies.session.transcript import TranscriptCompacted
from substrate.topologies.session.vocabulary import (
    COMPACTION_REASON_WINDOW_EXCEEDED,
    COMPACTION_ROLLING_WINDOW,
    COMPACTION_TOOL_OUTPUT_CLEARED,
)

# The payload of seq 150 in codex session s_b8dab6b0cfd443cdba9bc8b3, written before v0.7.
_V06 = (
    b'{"dropped_seq_range": [17, 146], "kept_seq_start": 147, "reason": "driver_window_exceeded",'
    b' "strategy": "rolling_window", "tokens_after": 9322, "tokens_before": 228114}'
)


def test_a_record_before_v07_decodes() -> None:
    ev = msgspec.json.decode(_V06, type=TranscriptCompacted)
    assert ev.dropped_seq_range == (17, 146)
    assert ev.cleared_through_seq is None and ev.token_scale == 1.0
    assert (
        ev.strategy == COMPACTION_ROLLING_WINDOW and ev.reason == COMPACTION_REASON_WINDOW_EXCEEDED
    )


def test_v07_fields_round_trip() -> None:
    ev = TranscriptCompacted(
        strategy=COMPACTION_TOOL_OUTPUT_CLEARED,
        kept_seq_start=17,
        reason=COMPACTION_REASON_WINDOW_EXCEEDED,
        tokens_before=70_000,
        tokens_after=28_000,
        cleared_through_seq=120,
        token_scale=1.19,
    )
    back = msgspec.json.decode(msgspec.json.encode(ev), type=TranscriptCompacted)
    assert back == ev and back.dropped_seq_range is None
