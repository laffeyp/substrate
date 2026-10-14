# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 330: the caller's hold on its runs (vocabulary § Z.1, research r9 § 4). A run
returns at once; its start lands in the caller's record when it starts and its end at the caller's
next model step, once; the caller can stop, step through and replay it; ending the caller stops
its runs."""

from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.runs.hold import RunTable, make_run_tool, run_notice
from substrate.topologies.runs.run import RunSpec
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.vocabulary import RunOutcome, RunRole, RunSession
from substrate.topologies.tool_loop.tools import Tool, full_suite
from substrate.topologies.workspace import ensure_repository

pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")

WRITE_AND_COMMIT = [("write_file", ["b.txt", "b\n"]), ("bash", ["git add -A && git commit -qm b"])]
SLOW = [("bash", ["sleep 30"])]


def _factory(tmp_path: Path, script: list[tuple[str, list[Any]]], sid: str = "s_run") -> Any:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    (repo / "a.txt").write_text("a\n")
    ensure_repository(repo)
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    return session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=4096,
        seed="",
        tools=full_suite(repo),
        session_id=sid,
        workspace_path=str(repo),
        script=script,
        run=RunSpec(worktree=repo, base=base, first_message="add b.txt"),
    )


def _session(run_id: str, root: Path) -> list[RunSession]:
    return [RunSession(session_id=f"s_{run_id}", role=RunRole.WORKER, record_root=str(root))]


def _wait(table: RunTable, owner: str, run_id: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while table.running(owner, run_id):
        assert time.monotonic() < deadline, "the run did not end"
        time.sleep(0.05)


def test_a_run_returns_at_once_and_its_end_is_told_once(tmp_path: Path) -> None:
    table = RunTable()
    root = tmp_path / "run"
    started = time.monotonic()
    table.start(
        "caller", "r_1", "build", _session("r_1", root), _factory(tmp_path, WRITE_AND_COMMIT), root
    )
    assert time.monotonic() - started < 2
    _wait(table, "caller", "r_1")
    (ended,) = table.drain_ended("caller")
    assert ended.outcome is RunOutcome.DONE and ended.report is not None
    assert ended.report.files == ["b.txt"] and ended.report_seq is not None
    assert table.drain_ended("caller") == []
    assert run_notice(ended).startswith("[run r_1 (build) ended done: ")


def test_the_caller_stops_a_run_and_ending_the_caller_stops_its_runs(tmp_path: Path) -> None:
    table = RunTable()
    root = tmp_path / "run"
    table.start("caller", "r_2", "build", _session("r_2", root), _factory(tmp_path, SLOW), root)
    time.sleep(1.0)
    assert table.running("caller", "r_2")
    table.stop("caller", "r_2")
    _wait(table, "caller", "r_2", timeout=30)
    (ended,) = table.drain_ended("caller")
    assert ended.outcome is RunOutcome.STOPPED
    ends = [e["payload"] for e in api.read_record(root) if e["kind"] == "SessionEnded"]
    assert ends and ends[-1]["reason"] == "caller_stop"
    root3 = tmp_path / "run3"
    table.start(
        "caller", "r_3", "build", _session("r_3", root3), _factory(tmp_path, SLOW, "s_3"), root3
    )
    time.sleep(1.0)
    assert table.stop_owner("caller") == 1
    _wait(table, "caller", "r_3", timeout=30)


def test_stepping_replaying_and_the_listing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from substrate.topologies.runs import hold

    table = RunTable()
    monkeypatch.setattr(hold, "TABLE", table)  # the run tool reads the process's table
    root = tmp_path / "run"
    table.start(
        "caller", "r_4", "build", _session("r_4", root), _factory(tmp_path, WRITE_AND_COMMIT), root
    )
    (row,) = table.listing("caller")
    assert row["run_id"] == "r_4" and row["sessions"][0]["role"] == "worker"
    _wait(table, "caller", "r_4")
    (row,) = table.listing("caller")
    assert row["running"] is False and row["outcome"] == "done"
    tool = make_run_tool("caller")
    steps = tool.run([{"run_id": "r_4", "action": "events", "from_seq": 3, "limit": 5}])["events"]
    assert [e["seq"] for e in steps] == [3, 4, 5, 6, 7]
    replay = tool.run([{"run_id": "r_4", "action": "replay"}])
    assert replay["complete"] and not replay["mismatches"]
    with pytest.raises(ValueError, match="holds no run"):
        make_run_tool("someone else").run([{"run_id": "r_4", "action": "stop"}])
    with pytest.raises(ValueError, match="action must be one of"):
        tool.run([{"run_id": "r_4", "action": "pause"}])
    assert len(table.drain_ended("caller")) == 1  # the listing reported nothing


def test_a_caller_session_records_the_start_and_is_told_the_end(tmp_path: Path) -> None:
    from substrate.topologies.runs import hold

    table = RunTable()
    run_root = tmp_path / "run"
    factory = _factory(tmp_path, WRITE_AND_COMMIT)

    def _start(_args: Any) -> dict[str, Any]:
        table.start("s_caller", "r_5", "build", _session("r_5", run_root), factory, run_root)
        return {"run_id": "r_5"}

    tools = {
        "start_run": Tool(name="start_run", describe="start_run()", deterministic=False, run=_start)
    }

    def caller(script: list[tuple[str, list[Any]]]) -> Any:
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
    hold.TABLE = table
    try:
        root = tmp_path / "caller"
        asyncio.run(
            api.Runtime(root, persistent=True).resume(
                caller([("start_run", [])]),
                resume_event=UserMessage(
                    text="build it", turn_index=0, assembled_prompt="", slash_source="chat"
                ),
            )
        )
        _wait(table, "s_caller", "r_5")
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
    calls = [e for e in events if e["kind"] == "ToolCall"]
    starts = [e for e in events if e["kind"] == "TopologyRunStarted"]
    ends = [e for e in events if e["kind"] == "TopologyRunEnded"]
    assert (
        len(calls) == 1 and len(starts) == 1 and starts[0]["payload"]["call_seq"] == calls[0]["seq"]
    )
    assert len(ends) == 1 and ends[0]["payload"]["outcome"] == "done"
    second = next(
        e["seq"] for e in events if e["kind"] == "UserMessage" and e["payload"]["turn_index"] == 1
    )
    assert ends[0]["seq"] > second
