# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 213a — provenance both ways: parent's ToolResult cites the child, and
the child's `RunStarted.baseline` cites the parent (session_id + seq_at_call).

TECH-SPEC-2026-08-25-round6 §5: provenance both directions so
`api.trace_ancestry` walks parent → child → parent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.tool_loop.delegate import make_delegate


def _child_baseline(child_root: Path) -> dict[str, Any]:
    run_started = next(
        e for e in api.read_record(child_root) if e["kind"] == "substrate.RunStarted"
    )
    baseline = run_started["payload"].get("baseline") or {}
    return dict(baseline) if isinstance(baseline, dict) else {}


def test_parent_toolresult_carries_child_root(tmp_path: Path) -> None:
    d = make_delegate(responder=DeterministicResponder(seed=0), root=tmp_path)
    result = d.run(["hi"])
    assert "child_root" in result
    assert Path(result["child_root"]).exists()
    # child_root is a substrate record directory — RunStarted at seq 0.
    envelopes = list(api.read_record(Path(result["child_root"])))
    assert envelopes[0]["kind"] == "substrate.RunStarted"


def test_child_baseline_carries_parent_session_id(tmp_path: Path) -> None:
    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=tmp_path,
        parent_session_id="s_parent_alpha",
    )
    result = d.run(["hi"])
    baseline = _child_baseline(Path(result["child_root"]))
    assert baseline["parent_session_id"] == "s_parent_alpha"


@pytest.mark.asyncio
async def test_child_baseline_carries_parent_seq_at_call(tmp_path: Path) -> None:
    from collections.abc import AsyncIterator

    from msgspec import Struct

    class Tick(Struct, frozen=True):
        n: int

    async def _emit(inp: Any) -> AsyncIterator[Tick]:
        del inp
        for i in range(3):
            yield Tick(n=i)

    def parent_topology(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "emitter",
            schemas=[Tick],
            schema_version=1,
            factory=lambda: _emit,
            deterministic=True,
        )
        b.initial("emitter", input={})
        b.termination(api.threshold_count("Tick", 3))

    parent_root = tmp_path / "parent"
    await api.Runtime(parent_root).run(parent_topology)

    parent_envs = list(api.read_record(parent_root))
    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=tmp_path / "delegates",
        parent_session_id="s_parent_beta",
        parent_record_root=parent_root,
    )
    result = d.run(["hi"])
    baseline = _child_baseline(Path(result["child_root"]))
    assert baseline["parent_session_id"] == "s_parent_beta"
    assert baseline["parent_seq_at_call"] == len(parent_envs) - 1


def test_delegate_without_parent_provenance_omits_the_keys(tmp_path: Path) -> None:
    """A delegate with no constructor-time provenance leaves the child's
    baseline free of `parent_*` keys — no spurious empty values.
    """
    d = make_delegate(responder=DeterministicResponder(seed=0), root=tmp_path)
    result = d.run(["hi"])
    baseline = _child_baseline(Path(result["child_root"]))
    assert "parent_session_id" not in baseline
    assert "parent_seq_at_call" not in baseline


def test_child_root_from_toolresult_can_be_re_read(tmp_path: Path) -> None:
    """`api.read_record` on the returned `child_root` yields the child's own
    envelope stream — the substrate primitive walks parent → child through this
    path (sprint 213b's `trace_ancestry` seam builds on it).
    """
    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=tmp_path,
        parent_session_id="s_parent_gamma",
    )
    parent_result = d.run(["compute something"])
    child_root = Path(parent_result["child_root"])
    child_envs = list(api.read_record(child_root))
    assert child_envs[0]["kind"] == "substrate.RunStarted"
    baseline = child_envs[0]["payload"].get("baseline") or {}
    assert baseline["parent_session_id"] == "s_parent_gamma"
