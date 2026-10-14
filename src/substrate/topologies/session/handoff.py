# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The handoff control's measure (session vocabulary § Y.3, kernel sprint 324): per turn of a
session record, how many times the model handed work to a topology (`HANDOFF_TOOLS`), with the
turn's handoff position. Read across sessions it gives calls per turn by position and by model."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ..tool_loop.kinds import TOOL_CALL
from .vocabulary import (
    HANDOFF_DEFAULT,
    HANDOFF_TOOLS,
    SESSION_CHANGED,
    SESSION_STARTED,
    USER_MESSAGE,
    Control,
)


def handoff_calls(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One row per turn: `turn` (its index), `position` (the handoff position the turn ran
    under), `model`, `calls` (topology calls in the turn) and `tools` (their names, in order)."""
    position = str(HANDOFF_DEFAULT)
    model = ""
    rows: list[dict[str, Any]] = []
    for e in events:
        kind = e.get("kind")
        payload = e.get("payload") or {}
        if kind == SESSION_STARTED:
            position = str(payload.get("handoff") or HANDOFF_DEFAULT)
            model = str(payload.get("driver_model") or "")
        elif kind == SESSION_CHANGED and payload.get("field") in (Control.HANDOFF, "driver"):
            # A change is recorded at its turn's first model step, after the turn's message: it
            # applies to the turn already open (§ P.4).
            key = "position" if payload.get("field") == Control.HANDOFF else "model"
            value = str(payload.get("new") or (HANDOFF_DEFAULT if key == "position" else model))
            if key == "position":
                position = value
            else:
                model = value
            if rows:
                rows[-1][key] = value
        elif kind == USER_MESSAGE:
            turn = int(payload.get("turn_index", len(rows)))
            rows.append(
                {"turn": turn, "position": position, "model": model, "calls": 0, "tools": []}
            )
        elif kind == TOOL_CALL and rows and payload.get("tool") in HANDOFF_TOOLS:
            rows[-1]["calls"] += 1
            rows[-1]["tools"].append(str(payload.get("tool")))
    return rows


__all__ = ["handoff_calls"]
