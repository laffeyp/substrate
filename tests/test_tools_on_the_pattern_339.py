# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 339: the built tools say what comes next (research create-topology § 7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.topologies.runs.build import make_build_tool
from substrate.topologies.runs.hold import RunTable, make_run_tool, run_notice
from substrate.topologies.runs.review import make_review_tool
from substrate.topologies.session import ReportWritten, TopologyRunEnded
from substrate.topologies.session.vocabulary import RunOutcome
from substrate.topologies.tool_loop.delegate import make_delegate


def _ended(topology: str, branch: str | None) -> TopologyRunEnded:
    report = ReportWritten(
        outcome=RunOutcome.DONE, reply="did it", files=["b.txt"], branch=branch, commits=["abc"]
    )
    return TopologyRunEnded(
        run_id="r_1", topology=topology, outcome=RunOutcome.DONE, report_seq=9, report=report
    )


def test_a_started_build_or_review_says_what_comes_next(tmp_path: Path) -> None:
    built = make_build_tool(lambda _card: ("r_1", "build/r_1"), tmp_path).run(["add b.txt"])
    assert built["branch"] == "build/r_1"
    assert "report comes to you once" in built["next"]
    assert "run(run_id='r_1', action='stop')" in built["next"]
    reviewed = make_review_tool(lambda _t, styles, _f: ["r_2", "r_3"][: len(styles)]).run(
        [{"target": "main", "styles": ["defects", "design"]}]
    )
    assert reviewed["next"].startswith("each reviewer's report comes to you once")
    assert "<one of r_2, r_3>" in reviewed["next"]


def test_an_ended_build_names_its_branch_moves_and_a_review_its_findings() -> None:
    notice = run_notice(_ended("build", "build/r_1"))
    assert "`git diff HEAD...build/r_1`" in notice
    assert "review(target='build/r_1')" in notice and "`git merge build/r_1`" in notice
    assert "fix it yourself, build(task=…)" in run_notice(_ended("review", None))
    stopped = TopologyRunEnded(
        run_id="r_1", topology="build", outcome=RunOutcome.FAILED, report_seq=None, report=None
    )
    assert run_notice(stopped) == "[run r_1 (build) ended failed]"


def test_the_run_tool_teaches_its_actions_and_lists_ids_on_a_miss() -> None:
    from substrate.topologies.runs import hold

    tool = make_run_tool("s_caller")
    assert "`events` reads its record" in tool.describe and "`replay` checks" in tool.describe
    original = hold.TABLE
    hold.TABLE = RunTable()
    try:
        with pytest.raises(ValueError, match="no run 'r_x'; this session has no runs"):
            tool.run([{"run_id": "r_x", "action": "stop"}])
    finally:
        hold.TABLE = original


def test_delegate_says_when_build_suits_better(tmp_path: Path) -> None:
    tool = make_delegate(
        session_registry=None, parent_session_id="s", parent_record_root=tmp_path / "r"
    )
    assert "for a change you want on its own branch, use build" in tool.describe
