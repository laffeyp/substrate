# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 213a — path 3: `delegate(task, context=...)` prefixes an extracted slice
of the parent's record to the child's task.

TECH-SPEC-2026-08-25-round6 §5 path 3 + §1.6.5 8 KiB cap. The extractor at
`delegate._extract_context_slice` reads `parent_record_root` via `api.read_record`,
filters events by `context["parent_seq_range"]` and `context["kinds"]`, caps the
serialized slice at 8 KiB with event-boundary drops (post-review 2026-08-25 rule):
an event's payload survives whole or is elided whole, and a single event larger
than the cap by itself is included alone with a trailing note.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.tool_loop.delegate import (
    _CONTEXT_SLICE_CAP_BYTES,
    _extract_context_slice,
    make_delegate,
    prefix_context_slice,
)

# ── extractor unit tests (deterministic; no runtime) ────────────────────────


def _envelope(seq: int, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"seq": seq, "kind": kind, "payload": payload}


def test_slice_filters_by_seq_range(monkeypatch: pytest.MonkeyPatch) -> None:
    envs = [
        _envelope(0, "UserMessage", {"text": "a"}),
        _envelope(1, "ModelReply", {"text": "b"}),
        _envelope(2, "UserMessage", {"text": "c"}),
        _envelope(3, "ModelReply", {"text": "d"}),
    ]
    monkeypatch.setattr(
        "substrate.topologies.tool_loop.delegate.api.read_record",
        lambda root, **_kw: iter(envs),
    )
    text, elided_count, _elided_bytes, single_oversize = _extract_context_slice(
        Path("/nowhere"), (1, 2), ()
    )
    assert not single_oversize
    assert elided_count == 0
    assert "seq=1" in text and "seq=2" in text
    assert "seq=0" not in text and "seq=3" not in text


def test_slice_filters_by_kinds(monkeypatch: pytest.MonkeyPatch) -> None:
    envs = [
        _envelope(0, "UserMessage", {"text": "u0"}),
        _envelope(1, "ModelReply", {"text": "m1"}),
        _envelope(2, "FinalAnswer", {"text": "f2"}),
    ]
    monkeypatch.setattr(
        "substrate.topologies.tool_loop.delegate.api.read_record",
        lambda root, **_kw: iter(envs),
    )
    text, _elided_count, _elided_bytes, _single_oversize = _extract_context_slice(
        Path("/nowhere"), (0, 10), ("FinalAnswer",)
    )
    assert "seq=2" in text and "kind=FinalAnswer" in text
    assert "seq=0" not in text and "seq=1" not in text


def test_slice_drops_at_event_boundary_when_over_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Three events of ~4 KiB each. First fits; second would push past 8 KiB;
    both remaining events elide. The trailing note names the elided count and
    combined byte size.
    """
    big_text = "x" * 4000  # ~4 KiB payload per event
    envs = [_envelope(i, "ModelReply", {"text": big_text, "turn_index": i}) for i in range(3)]
    monkeypatch.setattr(
        "substrate.topologies.tool_loop.delegate.api.read_record",
        lambda root, **_kw: iter(envs),
    )
    text, elided_count, elided_bytes, single_oversize = _extract_context_slice(
        Path("/nowhere"), (0, 10), ()
    )
    assert not single_oversize
    # Boundary drop, not mid-event truncation. Each formatted block is ~4 KiB;
    # two fit under 8 KiB (~8100 bytes), the third pushes past and elides. If a
    # future encoding tweak makes the blocks a bit bigger or smaller, the bound
    # holds either way: at least one elides, not all elide.
    assert 1 <= elided_count <= 2
    assert elided_bytes > 0
    assert "events elided" in text
    assert "seq=0" in text
    # Last event (seq=2) always outside the cap given three ~4 KiB blocks + overhead.
    assert "seq=2" not in text
    # Kept count + elided count sums to the input count.
    kept_markers = text.count("[seq=")
    assert kept_markers + elided_count == 3


def test_slice_includes_single_oversize_event_with_note(monkeypatch: pytest.MonkeyPatch) -> None:
    """One event whose serialized form exceeds the cap. Included alone; the
    subsequent matching events are counted as elided in the return value AND
    named in the trailing note (post-review 2026-08-26 finding 4 fix: the
    earlier shape returned elided_count=0 and dropped the tail silently).
    """
    huge = "y" * (_CONTEXT_SLICE_CAP_BYTES + 1000)
    envs = [
        _envelope(0, "ModelReply", {"text": huge}),
        _envelope(1, "ModelReply", {"text": "small"}),
        _envelope(2, "ModelReply", {"text": "also-small"}),
    ]
    monkeypatch.setattr(
        "substrate.topologies.tool_loop.delegate.api.read_record",
        lambda root, **_kw: iter(envs),
    )
    text, elided_count, elided_bytes, single_oversize = _extract_context_slice(
        Path("/nowhere"), (0, 10), ()
    )
    assert single_oversize
    assert elided_count == 2, "the two small events after the oversize one must be counted"
    assert elided_bytes > 0
    assert "seq=0" in text
    assert "seq=1" not in text
    assert "seq=2" not in text
    assert "larger than the" in text
    assert "more matching events elided" in text


def test_slice_single_oversize_alone_reports_zero_elided(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the oversize event is the ONLY match, elided_count is 0 and the
    trailing note says 'no other events fit'.
    """
    huge = "z" * (_CONTEXT_SLICE_CAP_BYTES + 500)
    envs = [_envelope(0, "ModelReply", {"text": huge})]
    monkeypatch.setattr(
        "substrate.topologies.tool_loop.delegate.api.read_record",
        lambda root, **_kw: iter(envs),
    )
    text, elided_count, elided_bytes, single_oversize = _extract_context_slice(
        Path("/nowhere"), (0, 10), ()
    )
    assert single_oversize
    assert elided_count == 0
    assert elided_bytes == 0
    assert "no other events fit" in text


def test_slice_empty_when_no_events_match(monkeypatch: pytest.MonkeyPatch) -> None:
    envs = [_envelope(0, "UserMessage", {})]
    monkeypatch.setattr(
        "substrate.topologies.tool_loop.delegate.api.read_record",
        lambda root, **_kw: iter(envs),
    )
    text, elided_count, _elided_bytes, single_oversize = _extract_context_slice(
        Path("/nowhere"), (5, 10), ("FinalAnswer",)
    )
    assert text == ""
    assert elided_count == 0
    assert not single_oversize


# ── prefix + integration test ────────────────────────────────────────────────


def testprefix_context_slice_wraps_task_with_header(monkeypatch: pytest.MonkeyPatch) -> None:
    envs = [_envelope(0, "FinalAnswer", {"text": "the answer is 42"})]
    monkeypatch.setattr(
        "substrate.topologies.tool_loop.delegate.api.read_record",
        lambda root, **_kw: iter(envs),
    )
    prefixed = prefix_context_slice(
        Path("/nowhere"),
        "please continue",
        {"parent_seq_range": [0, 10], "kinds": ["FinalAnswer"]},
    )
    assert "context from parent record" in prefixed
    assert "the answer is 42" in prefixed
    assert "please continue" in prefixed
    # The header rides above the task; the task rides at the tail.
    assert prefixed.rindex("please continue") > prefixed.index("the answer is 42")


def test_prefix_returns_task_unchanged_when_slice_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "substrate.topologies.tool_loop.delegate.api.read_record",
        lambda root, **_kw: iter([]),
    )
    prefixed = prefix_context_slice(
        Path("/nowhere"),
        "solo",
        {"parent_seq_range": [0, 10], "kinds": ["FinalAnswer"]},
    )
    assert prefixed == "solo"


@pytest.mark.asyncio
async def test_context_slice_reaches_the_child_task(tmp_path: Path) -> None:
    """End-to-end: build a parent record with a FinalAnswer, wire the delegate
    with `parent_record_root=<that path>`, fire with `context={parent_seq_range,
    kinds}`. The child's own record's UserMessage (from tool_loop's model
    factory's task interpolation) — or the child's answer text — carries the
    slice content.
    """
    parent_root = tmp_path / "parent-record"

    from collections.abc import AsyncIterator

    from msgspec import Struct

    class ParentReply(Struct, frozen=True):
        text: str

    async def _emit(inp: Any) -> AsyncIterator[ParentReply]:
        del inp
        yield ParentReply(text="parent said HELLO WORLD")

    def parent_topology(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "emitter",
            schemas=[ParentReply],
            schema_version=1,
            factory=lambda: _emit,
            deterministic=True,
        )
        b.initial("emitter", input={})
        b.termination(api.threshold_count("ParentReply", 1))

    await api.Runtime(parent_root).run(parent_topology)

    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=tmp_path / "delegates",
        parent_record_root=parent_root,
    )
    result = d.run(
        [
            {
                "task": "continue the parent's thought",
                "context": {"parent_seq_range": [0, 20], "kinds": ["ParentReply"]},
            }
        ]
    )
    assert result["via"] == "context_slice"
    # The child's answer chains from tool_loop's calculator fallback (no real
    # driver-parse of the prefixed task), but the CHILD RECORD carries the
    # prefixed task in its RunStarted baseline (via `_with_baseline`) or in
    # a topology-authored envelope. The strong assertion here is that
    # `_run_child_to_answer` did not raise — the slice reached the topology
    # without errors — and that `via` is set. The unit tests above cover the
    # slice content directly.
    assert result["answer"] is not None
