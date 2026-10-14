# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 314: session vocabulary v0.12 (§ X, topology runs) as types. Written before the
types existed."""

from __future__ import annotations

import msgspec

from substrate.topologies.session import (
    CardAccepted,
    ChecksRun,
    ReportWritten,
    TopologyRunEnded,
    TopologyRunStarted,
)
from substrate.topologies.session import vocabulary as v
from substrate.topologies.session.vocabulary import CardCheck, CheckResult, RunLimits, RunSession


def test_the_kinds_enums_producers_and_triggers_are_in_the_vocabulary() -> None:
    kinds = (
        v.TOPOLOGY_RUN_STARTED,
        v.TOPOLOGY_RUN_ENDED,
        v.CARD_ACCEPTED,
        v.CHECKS_RUN,
        v.REPORT_WRITTEN,
    )
    assert kinds == (
        "TopologyRunStarted",
        "TopologyRunEnded",
        "CardAccepted",
        "ChecksRun",
        "ReportWritten",
    )
    assert set(kinds) <= v.SESSION_KINDS
    producers = (
        v.PRODUCER_KIND_CARD,
        v.PRODUCER_KIND_CHECKS,
        v.PRODUCER_KIND_CONTINUE,
        v.PRODUCER_KIND_REPORT,
    )
    assert producers == ("card", "checks", "continue", "report")
    assert set(producers) <= v.SESSION_PRODUCER_KINDS
    triggers = (
        v.TRIGGER_ID_CHECKS_ON_RETURNED,
        v.TRIGGER_ID_CONTINUE_ON_CHECKS,
        v.TRIGGER_ID_REPORT_ON_CHECKS,
    )
    assert triggers == ("checks-on-returned", "continue-on-checks", "report-on-checks")
    assert set(triggers) <= v.SESSION_TRIGGER_IDS
    assert v.DRIVEN_SESSION_TRIGGER_IDS == set(triggers)
    assert [o.value for o in v.RunOutcome] == [
        "done",
        "partly_done",
        "needs_user",
        "stuck",
        "failed",
        "stopped",
    ]
    assert [r.value for r in v.RunRole] == ["worker", "reviewer"]
    assert [f.value for f in v.CardForm] == ["plain", "sdd"]
    assert [k.value for k in v.CheckKind] == ["command", "statement"]
    assert v.DRIVEN_SLASH_SOURCE == "driven"
    assert v.SessionEndReason.CALLER_STOP == "caller_stop"
    for name in (
        "TOPOLOGY_RUN_STARTED",
        "TOPOLOGY_RUN_ENDED",
        "CARD_ACCEPTED",
        "CHECKS_RUN",
        "REPORT_WRITTEN",
        "PRODUCER_KIND_CARD",
        "PRODUCER_KIND_CHECKS",
        "PRODUCER_KIND_CONTINUE",
        "PRODUCER_KIND_REPORT",
        "TRIGGER_ID_CHECKS_ON_RETURNED",
        "TRIGGER_ID_CONTINUE_ON_CHECKS",
        "TRIGGER_ID_REPORT_ON_CHECKS",
        "RunOutcome",
        "RunRole",
        "CardForm",
        "CheckKind",
        "DRIVEN_SLASH_SOURCE",
    ):
        assert name in v.__all__


def _round_trip(value: object, kind: type) -> None:
    assert msgspec.json.decode(msgspec.json.encode(value), type=kind) == value


def test_the_caller_events_round_trip() -> None:
    started = TopologyRunStarted(
        run_id="r_1",
        topology="build",
        call_seq=40,
        sessions=[
            RunSession(session_id="s_w", role=v.RunRole.WORKER, record_root="/r/w", driven=True)
        ],
    )
    _round_trip(started, TopologyRunStarted)
    result = CheckResult(
        index=0, kind=v.CheckKind.COMMAND, passed=True, exit=0, output_tail="1 passed", note=""
    )
    report = ReportWritten(
        outcome=v.RunOutcome.DONE,
        asked="add a --json flag",
        done="added the flag and its test",
        files=["cli.py", "tests/test_cli.py"],
        checks=[result],
        left="",
        branch="substrate/build/r_1",
        commits=["abc1234"],
    )
    ended = TopologyRunEnded(
        run_id="r_1", topology="build", outcome=v.RunOutcome.DONE, report_seq=88, report=report
    )
    _round_trip(ended, TopologyRunEnded)
    stopped = TopologyRunEnded(
        run_id="r_2", topology="build", outcome=v.RunOutcome.STOPPED, report_seq=None, report=None
    )
    _round_trip(stopped, TopologyRunEnded)


def test_the_run_events_round_trip() -> None:
    card = CardAccepted(
        form=v.CardForm.PLAIN,
        what="add a --json flag to the CLI",
        where=["cli.py", "tests/test_cli.py"],
        checks=[
            CardCheck(kind=v.CheckKind.COMMAND, text="pytest tests/test_cli.py"),
            CardCheck(kind=v.CheckKind.STATEMENT, text="--help lists --json"),
        ],
        text="what: add a --json flag\nwhere: cli.py\ndone when: pytest passes",
        limits=RunLimits(max_stops=40, stall_stops=3),
    )
    _round_trip(card, CardAccepted)
    checks = ChecksRun(
        after_seq=31,
        results=[
            CheckResult(
                index=0,
                kind=v.CheckKind.COMMAND,
                passed=False,
                exit=1,
                output_tail="1 failed",
                note="",
            ),
            CheckResult(
                index=1,
                kind=v.CheckKind.STATEMENT,
                passed=None,
                exit=None,
                output_tail="",
                note="judged by a reviewer",
            ),
        ],
        record_problems=[],
        passed=False,
    )
    _round_trip(checks, ChecksRun)
