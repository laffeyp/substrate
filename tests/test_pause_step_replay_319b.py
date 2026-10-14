# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 319b: the caller pauses, resumes, steps through and replays a run it holds, and its
model does so through the `run` tool (vocabulary v0.12.3)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.topologies.runs.hold import RunTable, make_run_tool
from substrate.topologies.session.vocabulary import RunLimits, RunOutcome

from tests.test_callers_hold_319 import WRITE_AND_COMMIT, _driven_factory, _session, _wait

pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")


def _until(pred: Any, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while not pred():
        assert time.monotonic() < deadline, "the condition did not hold in time"
        time.sleep(0.05)


def _kinds(root: Path) -> list[str]:
    return [
        str(e["kind"]) for e in api.read_record(root) if not str(e["kind"]).startswith("substrate.")
    ]


def test_a_paused_run_takes_no_next_turn_and_resumes(tmp_path: Path) -> None:
    table = RunTable()
    root = tmp_path / "run"
    factory = _driven_factory(
        tmp_path, commands=["test -f never.txt"], script=[], limits=RunLimits(6, 99)
    )
    table.start("caller", "r_p", "build", _session("r_p", root), factory, root)
    table.pause("caller", "r_p")
    _until(lambda: not table.running("caller", "r_p"))
    assert table.paused("caller", "r_p")
    assert table.drain_ended("caller") == []  # paused is not ended
    kinds = _kinds(root)
    assert (
        "RunPaused" in kinds and kinds[-1] == "ChecksRun"
    )  # no message after the checks it paused at
    paused_at = kinds.count("ChecksRun")
    assert paused_at < 6
    table.resume("caller", "r_p")
    _wait(table, "caller", "r_p")
    kinds = _kinds(root)
    assert "RunResumed" in kinds and kinds.count("ChecksRun") == 6
    (ended,) = table.drain_ended("caller")
    assert ended.outcome is RunOutcome.STUCK


def test_resuming_a_run_that_is_not_paused_is_refused(tmp_path: Path) -> None:
    table = RunTable()
    root = tmp_path / "run"
    factory = _driven_factory(
        tmp_path, commands=["test -f b.txt"], script=WRITE_AND_COMMIT, limits=RunLimits(5, 2)
    )
    table.start("caller", "r_n", "build", _session("r_n", root), factory, root)
    _wait(table, "caller", "r_n")
    with pytest.raises(ValueError, match="is not paused"):
        table.resume("caller", "r_n")


def test_stepping_and_replaying_a_finished_run(tmp_path: Path) -> None:
    table = RunTable()
    root = tmp_path / "run"
    factory = _driven_factory(
        tmp_path, commands=["test -f b.txt"], script=WRITE_AND_COMMIT, limits=RunLimits(5, 2)
    )
    table.start("caller", "r_s", "build", _session("r_s", root), factory, root)
    _wait(table, "caller", "r_s")
    rows = table.events("caller", "r_s", from_seq=3, limit=5)
    assert [r["seq"] for r in rows] == [3, 4, 5, 6, 7]
    everything = table.events("caller", "r_s", limit=10_000)
    assert [r["seq"] for r in everything] == list(range(len(everything)))
    assert everything[-1]["kind"] == "substrate.RunFinalised"
    replayed = table.replay("caller", "r_s")
    assert replayed["complete"] is True and replayed["mismatches"] == []
    assert replayed["decisions_verified"] > 0


def test_the_run_tool_controls_its_own_sessions_runs_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from substrate.topologies.runs import hold

    table = RunTable()
    monkeypatch.setattr(hold, "TABLE", table)
    root = tmp_path / "run"
    factory = _driven_factory(
        tmp_path,
        commands=["test -f never.txt"],
        script=[("bash", ["sleep 30"])],
        limits=RunLimits(50, 50),
    )
    table.start("s_mine", "r_t", "build", _session("r_t", root), factory, root)
    theirs = make_run_tool("s_other")
    with pytest.raises(ValueError, match="holds no run 'r_t'"):
        theirs.run([{"run_id": "r_t", "action": "stop"}])
    mine = make_run_tool("s_mine")
    with pytest.raises(ValueError, match="action must be one of"):
        mine.run([{"run_id": "r_t", "action": "delete"}])
    time.sleep(0.5)
    assert mine.run([{"run_id": "r_t", "action": "stop"}]) == {
        "run_id": "r_t",
        "action": "stop",
        "ok": True,
    }
    _wait(table, "s_mine", "r_t", timeout=30)
    assert table.drain_ended("s_mine")[0].outcome is RunOutcome.STOPPED
    assert mine.run([{"run_id": "r_t", "action": "events", "limit": 2}])["events"][0]["seq"] == 0
