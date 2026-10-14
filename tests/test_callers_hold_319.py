# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 319: the caller's hold on a run (vocabulary § X.2). A run returns at once, its start
lands in the caller's record when it starts and its end at the caller's next model step, once; the
caller can stop it; ending the caller stops its runs. Written before `topologies/runs/hold.py`
existed."""

from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.runs.card import read_card
from substrate.topologies.runs.driven import DrivenRun
from substrate.topologies.runs.hold import RunTable
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.vocabulary import RunLimits, RunOutcome, RunRole, RunSession
from substrate.topologies.tool_loop.tools import Tool, full_suite
from substrate.topologies.workspace import ensure_repository

pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")


def _driven_factory(
    tmp_path: Path, *, commands: list[str], script: list[tuple[str, list[Any]]], limits: RunLimits
) -> Any:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    (repo / "a.txt").write_text("a\n")
    ensure_repository(repo)
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    card = read_card(
        what="add b.txt", where=["b.txt"], commands=commands, statements=[], limits=limits
    )
    return session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=4096,
        seed="",
        tools=full_suite(repo),
        session_id="s_run",
        workspace_path=str(repo),
        script=script,
        driven=DrivenRun(
            card=card, worktree=repo, base=base, check_timeout_s=30, first_message="go"
        ),
    )


def _wait(table: RunTable, owner: str, run_id: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while table.running(owner, run_id):
        assert time.monotonic() < deadline, "the run did not end"
        time.sleep(0.05)


def _session(run_id: str, root: Path) -> list[RunSession]:
    return [
        RunSession(
            session_id=f"s_{run_id}", role=RunRole.WORKER, record_root=str(root), driven=True
        )
    ]


WRITE_AND_COMMIT = [("write_file", ["b.txt", "b\n"]), ("bash", ["git add -A && git commit -qm b"])]


def test_a_run_returns_at_once_and_its_end_is_told_once(tmp_path: Path) -> None:
    table = RunTable()
    factory = _driven_factory(
        tmp_path, commands=["test -f b.txt"], script=WRITE_AND_COMMIT, limits=RunLimits(5, 2)
    )
    root = tmp_path / "run"
    started = time.monotonic()
    table.start("caller", "r_1", "build", _session("r_1", root), factory, root)
    assert time.monotonic() - started < 2  # it did not wait for the run
    _wait(table, "caller", "r_1")
    ended = table.drain_ended("caller")
    assert len(ended) == 1 and ended[0].run_id == "r_1" and ended[0].outcome is RunOutcome.DONE
    assert ended[0].report is not None and ended[0].report.files == ["b.txt"]
    assert ended[0].report_seq is not None
    assert table.drain_ended("caller") == []  # told once


def _slow_factory(tmp_path: Path) -> Any:
    return _driven_factory(
        tmp_path,
        commands=["test -f never.txt"],
        script=[("bash", ["sleep 30"])],
        limits=RunLimits(50, 50),
    )


def test_the_caller_stops_a_run(tmp_path: Path) -> None:
    table = RunTable()
    root = tmp_path / "run"
    table.start("caller", "r_2", "build", _session("r_2", root), _slow_factory(tmp_path), root)
    time.sleep(1.0)
    assert table.running("caller", "r_2")
    table.stop("caller", "r_2")
    _wait(table, "caller", "r_2", timeout=30)
    (ended,) = table.drain_ended("caller")
    assert ended.outcome is RunOutcome.STOPPED and ended.report is None
    ends = [e["payload"] for e in api.read_record(root) if e["kind"] == "SessionEnded"]
    assert ends and ends[-1]["reason"] == "caller_stop"


def test_ending_the_caller_stops_its_runs(tmp_path: Path) -> None:
    table = RunTable()
    root = tmp_path / "run"
    table.start("caller", "r_3", "build", _session("r_3", root), _slow_factory(tmp_path), root)
    time.sleep(1.0)
    assert table.stop_owner("caller") == 1
    _wait(table, "caller", "r_3", timeout=30)
    assert table.drain_ended("caller")[0].outcome is RunOutcome.STOPPED


def test_a_caller_session_records_the_start_and_is_told_the_end(tmp_path: Path) -> None:
    from substrate.topologies.runs import hold

    table = RunTable()
    run_root = tmp_path / "run"
    factory = _driven_factory(
        tmp_path, commands=["test -f b.txt"], script=WRITE_AND_COMMIT, limits=RunLimits(5, 2)
    )

    def _start(_args: Any) -> dict[str, Any]:
        table.start("s_caller", "r_4", "build", _session("r_4", run_root), factory, run_root)
        return {"run_id": "r_4"}

    tools = {
        "start_run": Tool(name="start_run", describe="start_run()", deterministic=False, run=_start)
    }

    def caller(script: list[tuple[str, list[Any]]]) -> Any:
        # A script restarts at step 0 every turn; the second turn's caller calls no tool.
        return session_topology(
            driver=DeterministicResponder(seed=0),
            driver_name="deterministic",
            driver_context_tokens=4096,
            seed="",
            tools=tools,
            session_id="s_caller",
            workspace_path=str(tmp_path),
            script=script,
        )

    original = hold.TABLE
    hold.TABLE = table  # the model step reads the module's table
    try:
        root = tmp_path / "caller"
        rt = api.Runtime(root, persistent=True)
        asyncio.run(
            rt.resume(
                caller([("start_run", [])]),
                resume_event=UserMessage(
                    text="build it", turn_index=0, assembled_prompt="", slash_source="chat"
                ),
            )
        )
        _wait(table, "s_caller", "r_4")
        asyncio.run(
            api.Runtime(root, persistent=True).resume(
                caller([]),
                resume_event=UserMessage(
                    text="and?", turn_index=1, assembled_prompt="", slash_source="chat"
                ),
            )
        )
    finally:
        hold.TABLE = original
    events = list(api.read_record(root, resolve_blobs=True))
    starts = [e for e in events if e["kind"] == "TopologyRunStarted"]
    ends = [e for e in events if e["kind"] == "TopologyRunEnded"]
    calls = [e for e in events if e["kind"] == "ToolCall"]
    assert len(calls) == 1
    assert len(starts) == 1 and starts[0]["payload"]["call_seq"] == calls[0]["seq"]
    assert len(ends) == 1 and ends[0]["payload"]["outcome"] == "done"
    second_turn = next(
        e["seq"] for e in events if e["kind"] == "UserMessage" and e["payload"]["turn_index"] == 1
    )
    assert ends[0]["seq"] > second_turn  # written at the caller's next model step


def test_a_run_id_is_held_once(tmp_path: Path) -> None:
    table = RunTable()
    root = tmp_path / "run"
    table.start("caller", "r_5", "build", _session("r_5", root), _slow_factory(tmp_path), root)
    with pytest.raises(ValueError, match="already holds a run 'r_5'"):
        table.start("caller", "r_5", "build", _session("r_5", root), _slow_factory(tmp_path), root)
    table.stop("caller", "r_5")
    _wait(table, "caller", "r_5", timeout=30)
