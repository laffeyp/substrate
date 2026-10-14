# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 213a — per-call `baseline` merges into the child's
`TopologyBuilder.baseline(**merged)` at build time.

TECH-SPEC-2026-08-25-round6 §5: baseline per-call falls through to
`TopologyBuilder.baseline(**baseline)` at build time (`topology.py:376`). The
child's `substrate.RunStarted.payload.baseline` carries the merged shape —
per-call fields + provenance (`parent_session_id`, `parent_seq_at_call` when
they are set at construction time).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.tool_loop.delegate import make_delegate


def _read_baseline(record_root: Path) -> dict[str, Any]:
    run_started = next(
        e for e in api.read_record(record_root) if e["kind"] == "substrate.RunStarted"
    )
    payload = run_started["payload"]
    baseline_raw = payload.get("baseline") or {}
    if not isinstance(baseline_raw, dict):
        return {}
    return dict(baseline_raw)


def test_per_call_baseline_lands_on_child_record(tmp_path: Path) -> None:
    d = make_delegate(responder=DeterministicResponder(seed=0), root=tmp_path)
    result = d.run([{"task": "hi", "baseline": {"foo": "bar", "n": 7}}])
    baseline = _read_baseline(Path(result["child_root"]))
    assert baseline["foo"] == "bar"
    assert baseline["n"] == 7


def test_bare_task_child_has_empty_or_absent_baseline(tmp_path: Path) -> None:
    """A pre-sprint-213 caller passing a bare string never sets baseline. The
    child's RunStarted baseline stays empty (or absent). Backwards compat.
    """
    d = make_delegate(responder=DeterministicResponder(seed=0), root=tmp_path)
    result = d.run(["hi"])
    baseline = _read_baseline(Path(result["child_root"]))
    # No provenance kwargs and no per-call baseline → nothing to merge.
    assert baseline == {}


def test_non_dict_per_call_baseline_is_ignored(tmp_path: Path) -> None:
    """A malformed baseline (list, string) is treated as absent, not crashy."""
    d = make_delegate(responder=DeterministicResponder(seed=0), root=tmp_path)
    result = d.run([{"task": "hi", "baseline": "not a dict"}])
    baseline = _read_baseline(Path(result["child_root"]))
    assert baseline == {}


def test_provenance_from_constructor_lands_on_child_baseline(tmp_path: Path) -> None:
    """`parent_session_id` at construction time propagates into every child's
    baseline. `parent_seq_at_call` is None here because `parent_record_root`
    was not set — the None fields are simply absent.
    """
    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=tmp_path,
        parent_session_id="s_parent_alpha",
    )
    result = d.run(["hi"])
    baseline = _read_baseline(Path(result["child_root"]))
    assert baseline["parent_session_id"] == "s_parent_alpha"
    assert "parent_seq_at_call" not in baseline


@pytest.mark.asyncio
async def test_parent_seq_at_call_reads_the_parent_record_tail(tmp_path: Path) -> None:
    """When `parent_record_root` is set at construction, delegate reads
    `parent_seq_at_call = last_seq_on_parent_record` at Tool.run time and
    threads it into the child's baseline. Downstream `trace_ancestry` walks
    parent → child via this number.
    """
    from collections.abc import AsyncIterator

    from msgspec import Struct

    class Bumper(Struct, frozen=True):
        n: int

    async def _emit(inp: Any) -> AsyncIterator[Bumper]:
        del inp
        for i in range(5):
            yield Bumper(n=i)

    def parent_topology(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "emitter",
            schemas=[Bumper],
            schema_version=1,
            factory=lambda: _emit,
            deterministic=True,
        )
        b.initial("emitter", input={})
        b.termination(api.threshold_count("Bumper", 5))

    parent_root = tmp_path / "parent-record"
    await api.Runtime(parent_root).run(parent_topology)

    parent_envelope_count = sum(1 for _ in api.read_record(parent_root))
    expected_seq_at_call = parent_envelope_count - 1

    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=tmp_path / "delegates",
        parent_session_id="s_parent_beta",
        parent_record_root=parent_root,
    )
    result = d.run(["hi"])
    baseline = _read_baseline(Path(result["child_root"]))
    assert baseline["parent_session_id"] == "s_parent_beta"
    assert baseline["parent_seq_at_call"] == expected_seq_at_call


def test_per_call_baseline_and_provenance_merge_together(tmp_path: Path) -> None:
    """When both are set, both land on the child. Per-call values do NOT overwrite
    provenance keys — the merge order is: per_call_baseline first, then provenance
    keys on top. A caller cannot spoof `parent_session_id`.
    """
    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=tmp_path,
        parent_session_id="s_authoritative",
    )
    result = d.run(
        [
            {
                "task": "hi",
                "baseline": {
                    "topic": "reviewer notes",
                    "parent_session_id": "s_MALICIOUS",  # attempt to override provenance
                },
            }
        ]
    )
    baseline = _read_baseline(Path(result["child_root"]))
    assert baseline["topic"] == "reviewer notes"
    assert baseline["parent_session_id"] == "s_authoritative"


def test_per_call_baseline_cannot_spoof_provenance_when_constructor_did_not_set_it(
    tmp_path: Path,
) -> None:
    """Post-review 2026-08-26 finding 6 fix. Before: a delegate constructed with
    `parent_session_id=None` accepted a per-call baseline setting
    `parent_session_id="s_MALICIOUS"` and forwarded it to the child. Now the
    provenance keys are STRIPPED from per_call_baseline before the merge, so a
    caller-supplied `parent_session_id` cannot land on the child even when the
    constructor left the field unset.
    """
    d = make_delegate(responder=DeterministicResponder(seed=0), root=tmp_path)
    result = d.run(
        [
            {
                "task": "hi",
                "baseline": {
                    "topic": "unrelated",
                    "parent_session_id": "s_SPOOFED",
                    "parent_seq_at_call": 99999,
                },
            }
        ]
    )
    baseline = _read_baseline(Path(result["child_root"]))
    assert baseline["topic"] == "unrelated"
    assert "parent_session_id" not in baseline
    assert "parent_seq_at_call" not in baseline
