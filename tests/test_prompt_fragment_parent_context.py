# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""parent_context fragment source — sprint 063 tests.

Verifies:
 - parent_context binding on session_topology emits one PromptFragment
   (source=parent_context) with the extracted slice from the parent
   record.
 - Provenance carries parent_record_root, parent_seq_range, kinds,
   elided_count, elided_bytes, single_oversize.
 - Empty parent_context yields zero fragments.
 - Kinds filter drops non-matching events.

Deferred: delegate.py rewrite that swaps prefix_context_slice for the
producer path. Sprint 063 makes the fragment path available on
session_topology; a follow-up card migrates delegate itself.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from substrate import api
from substrate.topologies.session.ci import ci_session_topology
from substrate.topologies.session.parent_context_producer import (
    _extract_slice,
    _format_context_event,
)


def _write_parent_record(tmp_path: Path) -> Path:
    """Build a small parent record by running a CI session. Returns the
    parent record root."""

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("parent-hello", "/exit"),
            session_id="s_parent",
        )
        await api.Runtime(tmp_path / "parent").run(topology)

    asyncio.run(_run())
    return tmp_path / "parent"


def test_parent_context_fragment_lands(tmp_path: Path) -> None:
    """A child session opened with parent_context bound to the parent
    record emits one PromptFragment(source=parent_context) whose text
    includes seq/kind markers from the parent record."""
    parent_root = _write_parent_record(tmp_path)

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("child-hello", "/exit"),
            session_id="s_child",
            parent_context={
                "parent_record_root": str(parent_root),
                "parent_seq_range": [0, 1000],
                "kinds": ["UserMessage", "SessionStarted"],
            },
        )
        await api.Runtime(tmp_path / "child").run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "child"))
    frags = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "parent_context"
    ]
    assert len(frags) == 1
    payload = frags[0]["payload"]
    assert "seq=" in payload["text"]
    assert "kind=UserMessage" in payload["text"] or "kind=SessionStarted" in payload["text"]
    assert payload["precedence"] == 30
    prov = payload["provenance"]
    assert prov["parent_record_root"] == str(parent_root)
    assert prov["parent_seq_range"] == [0, 1000]
    assert prov["kinds"] == ["UserMessage", "SessionStarted"]
    assert prov["elided_count"] == 0
    assert prov["single_oversize"] is False


def test_parent_context_absent_yields_zero_fragments(tmp_path: Path) -> None:
    """No parent_context kwarg → zero parent_context fragments."""

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("hi", "/exit"),
            session_id="s_no_parent",
        )
        await api.Runtime(tmp_path / "ci").run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "ci"))
    frags = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "parent_context"
    ]
    assert len(frags) == 0


def test_kinds_filter_drops_non_matching_events(tmp_path: Path) -> None:
    """A child bound with kinds=["Park"] gets only Park events in the
    fragment text; UserMessage and other kinds are filtered out."""
    parent_root = _write_parent_record(tmp_path)

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("child", "/exit"),
            session_id="s_child_kinds",
            parent_context={
                "parent_record_root": str(parent_root),
                "parent_seq_range": [0, 1000],
                "kinds": ["Park"],
            },
        )
        await api.Runtime(tmp_path / "child").run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "child"))
    frags = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "parent_context"
    ]
    if frags:  # parent may have zero Park events, in which case zero fragments
        text = frags[0]["payload"]["text"]
        # Only assert on the `kind=X` marker — payload contents may
        # mention other kind names as strings (Park.awaiting names
        # "UserMessage" for example). The kind filter operates on the
        # envelope's kind field, not on payload text.
        assert "kind=UserMessage" not in text
        assert "kind=SessionStarted" not in text
        # Every included event has kind=Park.
        for line in text.splitlines():
            if line.startswith("[seq="):
                assert "kind=Park]" in line, f"non-Park line survived filter: {line}"


def test_extract_slice_pure_function_empty(tmp_path: Path) -> None:
    """The pure _extract_slice returns ('', 0, 0, False) when no events
    match. Locks the empty-response contract."""
    parent_root = _write_parent_record(tmp_path)
    text, elided_count, elided_bytes, single_oversize = _extract_slice(
        parent_root, (9999, 9999), (), cap_bytes=64 * 1024
    )
    assert text == ""
    assert elided_count == 0
    assert elided_bytes == 0
    assert single_oversize is False


def test_format_context_event_shape() -> None:
    """The event formatter returns `[seq=N kind=K] {payload_json}` in
    canonical form with sorted keys."""
    env = {
        "seq": 5,
        "kind": "UserMessage",
        "payload": {"text": "hello", "turn_index": 0},
    }
    formatted = _format_context_event(env)
    assert formatted.startswith("[seq=5 kind=UserMessage]")
    # sorted keys → text before turn_index
    assert '"text"' in formatted
    assert formatted.index('"text"') < formatted.index('"turn_index"')
