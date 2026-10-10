# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""A text slice of a record, for a prompt: delegate's per-call context and a session's
`parent_context` source (K263: one extractor; the session kept a copy before).

`extract_context_slice` reads the events in a seq range whose kind is in `kinds`, renders each
as `[seq=N kind=K] {payload_json}`, and stops at `cap_bytes` on an event boundary. Each caller
passes its own cap.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ... import api
from ..tool_loop.kinds import FINAL_ANSWER
from .vocabulary import MODEL_REPLY, StopReason


def slice_kind_matches(env: Mapping[str, Any], kinds: set[str]) -> bool:
    """A slice filter naming `FinalAnswer` also takes a session record's turn replies: since
    vocabulary v0.3 (§ K.3) a session writes no FinalAnswer, and its reply is the ModelReply whose
    `stop_reason` is not `tool_use`."""
    kind = env.get("kind")
    if kind in kinds:
        return True
    payload = env.get("payload") or {}
    return (
        FINAL_ANSWER in kinds
        and kind == MODEL_REPLY
        and isinstance(payload, Mapping)
        and "stop_reason" in payload
        and payload["stop_reason"] != StopReason.TOOL_USE
    )


def extract_context_slice(
    record_root: Path,
    parent_seq_range: tuple[int, int],
    kinds: tuple[str, ...],
    cap_bytes: int,
) -> tuple[str, int, int, bool]:
    """Read `record_root` and produce a text slice of events matching seq range + kinds,
    capped at `cap_bytes`. Drops at the event boundary — an event's payload survives
    whole or is elided whole (post-review 2026-08-25 large-event rule).

    Returns `(text, elided_count, elided_bytes, single_oversize)`.

    Iterates events in seq order; accumulates until the next event would push the
    running total past `cap_bytes`; stops. A single event larger than `cap_bytes`
    by itself is included alone (its content is what the caller asked for) with a
    trailing note.
    """
    lo, hi = parent_seq_range
    kinds_set = set(kinds) if kinds else None
    matching: list[dict[str, Any]] = []
    for env in api.read_record(record_root, resolve_blobs=True):  # Sprint 095
        seq = int(env.get("seq", -1))
        if seq < lo or seq > hi:
            continue
        if kinds_set is not None and not slice_kind_matches(env, kinds_set):
            continue
        matching.append(env)
    if not matching:
        return "", 0, 0, False
    kept: list[str] = []
    kept_bytes = 0
    elided: list[int] = []
    for i, env in enumerate(matching):
        block = format_context_event(env)
        block_bytes = len(block.encode("utf-8"))
        if not kept and block_bytes > cap_bytes:
            # The first matching event alone exceeds the cap. Include it whole
            # (its content is what the caller asked for; truncation would defeat
            # the request), then account for every other matching event as
            # elided rather than dropping them silently (review finding 4).
            rest_bytes = [
                len(format_context_event(other).encode("utf-8")) for other in matching[i + 1 :]
            ]
            rest_count = len(rest_bytes)
            rest_bytes_total = sum(rest_bytes)
            note = (
                f"\n... this single event is {block_bytes} bytes, larger than the "
                f"{cap_bytes}-byte slice cap"
            )
            if rest_count:
                note += f"; {rest_count} more matching events elided ({rest_bytes_total} bytes)"
            else:
                note += "; no other events fit"
            return block + note, rest_count, rest_bytes_total, True
        if kept_bytes + block_bytes > cap_bytes:
            elided.append(block_bytes)
            continue
        kept.append(block)
        kept_bytes += block_bytes
    text = "\n".join(kept)
    if elided:
        elided_bytes = sum(elided)
        text += f"\n... {len(elided)} events elided; narrow the range ({elided_bytes} bytes)"
    return text, len(elided), sum(elided), False


def format_context_event(env: dict[str, Any]) -> str:
    seq = env.get("seq", "?")
    kind = env.get("kind", "?")
    payload = env.get("payload") or {}
    if isinstance(payload, dict):
        payload_repr = json.dumps(payload, sort_keys=True)
    else:
        payload_repr = repr(payload)
    return f"[seq={seq} kind={kind}] {payload_repr}"


__all__ = ["extract_context_slice", "format_context_event", "slice_kind_matches"]
