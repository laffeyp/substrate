# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""parent_context fragment source — sprint 063.

Fires once at session open. Reads a bound parent record via
`api.read_record`, filters events by `parent_seq_range` (inclusive) and
optional `kinds` set, formats each matching event as
`[seq=N kind=K] {payload_json}`, joins with newlines, caps at
`_CONTEXT_SLICE_CAP_BYTES` at the event boundary (never mid-payload),
and yields one `PromptFragment(source=parent_context, precedence=30,
provenance={parent_record_root, parent_seq_range, kinds, elided_count,
elided_bytes, single_oversize})`. Empty slice yields nothing.

This module mirrors `delegate.py::_extract_context_slice` and `_format_
context_event` semantics — the extraction logic is correct; the packaging
is what changes. The child topology binds this producer via
`session_topology(parent_context={parent_record_root: ..., parent_seq_
range: [lo, hi], kinds: [...]})`.

Deferred to a follow-up card: the delegate.py rewrite. Today delegate
still calls `_prefix_context_slice` to build a string that prepends to
`assembled_prompt`. Sprint 063 makes the fragment-producer path
available as a session_topology parameter, so a caller that wires it
directly (test, CI wrapper, future delegate-to-session-child migration)
gets a typed fragment on the record instead of a string prefix.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from ... import api
from . import PromptFragment
from .vocabulary import PromptSource


_PRECEDENCE = 30  # reserved band from session-vocabulary.md § I
_CONTEXT_SLICE_CAP_BYTES = 64 * 1024  # matches delegate.py's default


def _format_context_event(env: dict[str, Any]) -> str:
    seq = env.get("seq", "?")
    kind = env.get("kind", "?")
    payload = env.get("payload") or {}
    if isinstance(payload, dict):
        payload_repr = json.dumps(payload, sort_keys=True)
    else:
        payload_repr = repr(payload)
    return f"[seq={seq} kind={kind}] {payload_repr}"


def _extract_slice(
    record_root: Path,
    seq_range: tuple[int, int],
    kinds: tuple[str, ...],
    cap_bytes: int = _CONTEXT_SLICE_CAP_BYTES,
) -> tuple[str, int, int, bool]:
    """Return `(text, elided_count, elided_bytes, single_oversize)`. Same
    contract as `delegate.py::_extract_context_slice` — the delegate's
    version stays in place for backward compat until its own rewrite.
    """
    lo, hi = seq_range
    kinds_set = set(kinds) if kinds else None
    matching: list[dict[str, Any]] = []
    for env in api.read_record(record_root, resolve_blobs=True):  # Sprint 095
        seq = int(env.get("seq", -1))
        if seq < lo or seq > hi:
            continue
        if kinds_set is not None and env.get("kind") not in kinds_set:
            continue
        matching.append(env)
    if not matching:
        return "", 0, 0, False
    kept: list[str] = []
    kept_bytes = 0
    elided: list[int] = []
    for i, env in enumerate(matching):
        block = _format_context_event(env)
        block_bytes = len(block.encode("utf-8"))
        if not kept and block_bytes > cap_bytes:
            rest_bytes = [
                len(_format_context_event(other).encode("utf-8")) for other in matching[i + 1 :]
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


def parent_context_producer_factory(
    parent_context: dict[str, Any] | None,
) -> Callable[[], Any]:
    """Return the parent_context fragment-source Producer body factory.

    `parent_context` is the dict the caller passes at
    `session_topology(parent_context={...})`. Keys:
      - `parent_record_root: str | Path` (required)
      - `parent_seq_range: (int, int) | [int, int]` (default (0, 2**31))
      - `kinds: tuple[str, ...] | list[str]` (default empty — no kind filter)
      - `cap_bytes: int` (default `_CONTEXT_SLICE_CAP_BYTES`)

    None yields no producer body (empty generator).
    """

    async def _parent_context(_inp: Any) -> AsyncIterator[PromptFragment]:
        if parent_context is None:
            return
        raw_root = parent_context.get("parent_record_root")
        if raw_root is None:
            return
        record_root = Path(raw_root)
        seq_range_raw = parent_context.get("parent_seq_range")
        if isinstance(seq_range_raw, (list, tuple)) and len(seq_range_raw) == 2:
            seq_range: tuple[int, int] = (int(seq_range_raw[0]), int(seq_range_raw[1]))
        else:
            seq_range = (0, 2**31)
        kinds_raw = parent_context.get("kinds") or ()
        kinds: tuple[str, ...] = tuple(str(k) for k in kinds_raw) if kinds_raw else ()
        cap_bytes = int(parent_context.get("cap_bytes", _CONTEXT_SLICE_CAP_BYTES))
        text, elided_count, elided_bytes, single_oversize = _extract_slice(
            record_root, seq_range, kinds, cap_bytes=cap_bytes
        )
        if not text:
            return
        yield PromptFragment(
            source=PromptSource.PARENT_CONTEXT,
            text=text,
            precedence=_PRECEDENCE,
            provenance={
                "parent_record_root": str(record_root),
                "parent_seq_range": [seq_range[0], seq_range[1]],
                "kinds": list(kinds),
                "elided_count": elided_count,
                "elided_bytes": elided_bytes,
                "single_oversize": single_oversize,
            },
        )

    return lambda: _parent_context


__all__ = [
    "_extract_slice",
    "_format_context_event",
    "parent_context_producer_factory",
]
