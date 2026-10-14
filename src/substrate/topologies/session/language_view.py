# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The language view: what the app's language page draws, from one session record (sprint K313).

The lines of `language_lines`, plus, for the user and model streams and each watched measure, the
detector's warm-up (how many values it took, their mean and standard deviation) and every value in
those standard deviations; and the record's LanguageDrift and SessionChanged events with the turn
each belongs to. The detector's rules stay in `substrate.language.drift`; nothing here re-derives
them.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ... import api
from ...language.catalog import CATALOG
from ...language.drift import DEFAULT_DRIFT, WATCHED, warmup_span
from .language_lines import language_lines
from .vocabulary import (
    LANGUAGE_DRIFT,
    SESSION_CHANGED,
    USER_MESSAGE,
    LanguageStream,
    StopReason,
)

_FINAL_STOPS = (StopReason.END_TURN, StopReason.WRAP_UP)


def _series_lines(lines: list[dict[str, Any]], stream: LanguageStream) -> list[dict[str, Any]]:
    """The texts a stream's detector series holds, in order: each user message, or each turn's
    final reply (the last whose stop reason is end_turn or wrap_up; the last reply when the record
    holds no stop reasons)."""
    if stream is LanguageStream.USER:
        return [x for x in lines if x["stream"] == LanguageStream.USER]
    by_turn: dict[int, list[dict[str, Any]]] = {}
    for x in lines:
        if x["stream"] == LanguageStream.MODEL:
            by_turn.setdefault(int(x["turn"]), []).append(x)
    out = []
    for turn in sorted(by_turn):
        replies = by_turn[turn]
        finals = [x for x in replies if x.get("stop_reason") in _FINAL_STOPS]
        out.append((finals or replies)[-1])
    return out


def _lane(series: list[dict[str, Any]], measure: str) -> dict[str, Any]:
    points = [(x, float(v)) for x in series if (v := x["values"]["text"].get(measure)) is not None]
    values = [v for _, v in points]
    span = warmup_span(values, DEFAULT_DRIFT.warmup)
    mean = sd = None
    if span is not None:
        mean = statistics.fmean(values[:span])
        sd = statistics.stdev(values[:span])
    return {
        "warmup_span": span,
        "warmup_end_seq": points[span - 1][0]["seq"] if span is not None else None,
        "mean": mean,
        "sd": sd,
        "points": [
            {
                "seq": x["seq"],
                "turn": x["turn"],
                "value": v,
                "window": _window_value(x, measure),
                "deviation": (v - mean) / sd if mean is not None and sd else None,
            }
            for x, v in points
        ],
    }


def _window_value(line: Mapping[str, Any], measure: str) -> float | None:
    """The trailing window's value; for a count, its average per text in the window."""
    window = line["values"].get("window") or {}
    value = window.get(measure)
    if value is None:
        return None
    if CATALOG[measure].count:
        return float(value) / max(int(window.get("window_texts") or 1), 1)
    return float(value)


def language_view(record: Path) -> dict[str, Any]:
    """Everything the language page draws for one session record."""
    events = list(api.read_record(record, resolve_blobs=True))
    lines = list(language_lines(events))
    turn = -1
    shifts: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    turn_of_seq: dict[int, int] = {}
    for e in events:
        if e["kind"] == USER_MESSAGE:
            turn = int(e["payload"]["turn_index"])
        turn_of_seq[int(e["seq"])] = turn
        if e["kind"] == SESSION_CHANGED:
            changes.append({"seq": e["seq"], "turn": turn, **_payload(e)})
    for e in events:
        if e["kind"] == LANGUAGE_DRIFT:
            p = _payload(e)
            shifts.append({"seq": e["seq"], "turn": turn_of_seq.get(int(p["source_seq"]), -1), **p})
    lanes = {
        str(stream): {m: _lane(_series_lines(lines, stream), m) for m in WATCHED}
        for stream in (LanguageStream.USER, LanguageStream.MODEL)
    }
    return {
        "lines": lines,
        "lanes": lanes,
        "shifts": shifts,
        "changes": changes,
        "warmup": DEFAULT_DRIFT.warmup,
        "last_seq": int(events[-1]["seq"]) if events else -1,
    }


def _payload(e: Mapping[str, Any]) -> dict[str, Any]:
    return dict(e["payload"]) if isinstance(e["payload"], Mapping) else {}
