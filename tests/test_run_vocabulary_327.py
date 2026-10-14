# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 327: session vocabulary v0.14 § Z, topology runs (research r9 § 3, § 4, § 7)."""

from __future__ import annotations

import msgspec

from substrate.topologies.session import ReportWritten, TopologyRunEnded, TopologyRunStarted
from substrate.topologies.session.vocabulary import (
    REPORT_WRITTEN,
    RUN_SLASH_SOURCE,
    SESSION_KINDS,
    TOPOLOGY_RUN_ENDED,
    TOPOLOGY_RUN_STARTED,
    RunOutcome,
    RunRole,
    RunSession,
)


def test_the_outcomes_and_roles() -> None:
    assert [o.value for o in RunOutcome] == ["done", "failed", "stopped"]
    assert [r.value for r in RunRole] == ["worker", "reviewer"]
    assert RUN_SLASH_SOURCE == "run"
    assert {TOPOLOGY_RUN_STARTED, TOPOLOGY_RUN_ENDED, REPORT_WRITTEN} <= SESSION_KINDS


def test_the_events_round_trip() -> None:
    report = ReportWritten(
        outcome=RunOutcome.DONE,
        reply="added b.txt",
        files=["b.txt"],
        branch="build/r_1",
        commits=["abc1234"],
    )
    started = TopologyRunStarted(
        run_id="r_1",
        topology="build",
        call_seq=12,
        sessions=[RunSession(session_id="s_r_1", role=RunRole.WORKER, record_root="/x")],
    )
    ended = TopologyRunEnded(
        run_id="r_1", topology="build", outcome=RunOutcome.DONE, report_seq=20, report=report
    )
    for event in (report, started, ended):
        assert msgspec.json.decode(msgspec.json.encode(event), type=type(event)) == event
    assert msgspec.to_builtins(started)["sessions"][0] == {
        "session_id": "s_r_1",
        "role": "worker",
        "record_root": "/x",
    }
