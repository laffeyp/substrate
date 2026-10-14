# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 338: the three create-topology tools (research create-topology § 5, § 6)."""

from __future__ import annotations

import asyncio
import itertools
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.compose.check import check
from substrate.topologies.compose.parts import Deps
from substrate.topologies.compose.run import agent_starter, start_composed
from substrate.topologies.compose.tools import SAVED_DIR, make_topology_tools, remember
from substrate.topologies.compose.vocabulary import Plan
from substrate.topologies.runs import build
from substrate.topologies.runs.hold import RunTable, run_notice
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session.vocabulary import RunOutcome
from substrate.topologies.workspace import ensure_repository

pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")

DRAFT_AND_CRITIQUE = """name: dac
draft: model "Write the function the user asks for."
critic: model on Draft "List the defects in this draft, or say NONE."
fix: model on Critic with Draft if Critic.text has no NONE max 3 "Fix the listed defects."
end: first Fix"""


class Says:
    def __init__(self, answers: list[str]) -> None:
        self.answers = itertools.cycle(answers)

    def respond(self, prompt: str) -> str:
        return next(self.answers)


def _wait(table: RunTable, owner: str, run_id: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while table.running(owner, run_id):
        assert time.monotonic() < deadline, f"run {run_id} did not end"
        time.sleep(0.05)


def _tools(tmp_path: Path, table: RunTable, owner: str, answers: list[str]) -> dict[str, Any]:
    says = Says(answers)  # one model for every step, answering in turn
    deps = Deps(responder=lambda _step: says, start_agent=lambda _c: {}, workdir=tmp_path)
    ids = itertools.count(1)

    def start(plan: Plan, run_input: str) -> str:
        run_id = f"r_{next(ids)}"
        start_composed(
            table,
            owner=owner,
            run_id=run_id,
            plan=plan,
            run_input=run_input,
            deps=deps,
            records=tmp_path / "runs",
        )
        return run_id

    return make_topology_tools(tmp_path, start)


def test_a_session_plans_runs_the_fixed_plan_and_is_told_the_end_once(tmp_path: Path) -> None:
    from substrate.topologies.runs import hold

    table = RunTable()
    tools = _tools(tmp_path, table, "s_caller", ["def add(a, b): return a - b", "subtracts"])
    checked = check(DRAFT_AND_CRITIQUE)
    assert checked.fixed is not None and checked.fixed.plan is not None
    fixed_id = remember(checked.fixed.plan)

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
                caller(
                    [
                        ("topology_plan", [{"lines": DRAFT_AND_CRITIQUE}]),
                        ("topology_run", [{"plan_id": fixed_id, "input": "add two numbers"}]),
                    ]
                ),
                resume_event=UserMessage(
                    text="make it", turn_index=0, assembled_prompt="", slash_source="chat"
                ),
            )
        )
        _wait(table, "s_caller", "r_1")
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
    results = {e["payload"]["tool"]: e["payload"] for e in events if e["kind"] == "ToolResult"}
    planned = results["topology_plan"]["output"]
    assert planned["fixed_plan_id"] == fixed_id
    assert planned["findings"][0].startswith("never_ends · ")
    assert "topology_run(plan_id=" in planned["next"]
    assert results["topology_run"]["output"]["run_id"] == "r_1"
    starts = [e["payload"] for e in events if e["kind"] == "TopologyRunStarted"]
    ends = [e["payload"] for e in events if e["kind"] == "TopologyRunEnded"]
    assert [s["topology"] for s in starts] == ["dac"] and starts[0]["sessions"] == []
    assert len(ends) == 1 and ends[0]["outcome"] == "done"
    result = ends[0]["result"]
    assert result["ended_on"] == "Fix" and result["counts"] == {"draft": 1, "critic": 1, "fix": 1}
    assert result["event"] == {"text": "def add(a, b): return a - b"}


def test_save_then_run_by_name_and_help_lists_it(tmp_path: Path) -> None:
    table = RunTable()
    tools = _tools(tmp_path, table, "s_x", ["v1", "NONE"])
    planned = tools["topology_plan"].run([{"lines": DRAFT_AND_CRITIQUE}])
    started = tools["topology_run"].run([{"plan_id": planned["fixed_plan_id"], "save": "mine"}])
    _wait(table, "s_x", started["run_id"])
    assert (tmp_path / SAVED_DIR / "mine.json").is_file()
    again = tools["topology_run"].run([{"name": "mine", "input": "x"}])
    assert again["topology"] == "mine"
    _wait(table, "s_x", again["run_id"])
    (ended,) = [e for e in table.drain_ended("s_x") if e.run_id == again["run_id"]]
    assert ended.outcome is RunOutcome.DONE and ended.result is not None
    assert ended.result.ended_on is None and ended.result.counts == {"draft": 1, "critic": 1}
    assert "ended when nothing was left to run" in run_notice(ended)
    text = tools["topology_help"].run([{}])["help"]
    for word in ("model:", "agent:", "command:", "collect:", "split:", "best_of_n", "mine"):
        assert word in text
    assert "critic: model on Draft" in tools["topology_help"].run([{"topic": "mine"}])["help"]
    assert "Its event: items." in tools["topology_help"].run([{"topic": "collect"}])["help"]


def test_from_a_named_plan_with_a_change(tmp_path: Path) -> None:
    tools = _tools(tmp_path, RunTable(), "s_y", ["x"])
    out = tools["topology_plan"].run([{"from": "best_of_n", "lines": "end: first All"}])
    assert out["lines"][-2] == "end: first All"
    assert any(f.startswith("unread · pick") for f in out["findings"])
    with pytest.raises(ValueError, match="no plan named 'nope'; there are"):
        tools["topology_plan"].run([{"from": "nope"}])
    with pytest.raises(ValueError, match="no plan 'p_missing'"):
        tools["topology_run"].run([{"plan_id": "p_missing"}])


def test_a_stopped_composed_run_ends_stopped(tmp_path: Path) -> None:
    table = RunTable()
    tools = _tools(tmp_path, table, "s_z", ["x"])
    planned = tools["topology_plan"].run(
        [{"lines": "wait: command \"sh -c 'echo $$ > child.pid; exec sleep 30'\""}]
    )
    started = tools["topology_run"].run([{"plan_id": planned["plan_id"]}])
    pid_file = tmp_path / "child.pid"
    deadline = time.monotonic() + 10
    while not pid_file.is_file() or not pid_file.read_text().strip():
        assert time.monotonic() < deadline
        time.sleep(0.05)
    table.stop("s_z", started["run_id"])
    _wait(table, "s_z", started["run_id"], timeout=10)
    (ended,) = table.drain_ended("s_z")
    assert ended.outcome is RunOutcome.STOPPED
    # The stop ended the command too, not just the shell that started it.
    pid = int(pid_file.read_text())
    deadline = time.monotonic() + 5
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        assert time.monotonic() < deadline, f"the stopped command {pid} still runs"
        time.sleep(0.05)


def test_an_agent_step_builds_on_a_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("a\n")
    ensure_repository(repo)
    table = RunTable()
    ids = itertools.count(1)

    def start_build(card: build.Card, model: str) -> tuple[str, str]:
        return build.start_build(
            table,
            owner="s_a",
            run_id=f"r_b{next(ids)}",
            repo=repo,
            card=card,
            driver_for=lambda _wt: DeterministicResponder(seed=0),
            driver_name="deterministic",
            driver_context_tokens=8192,
            model_class="large",
            bundle=None,
            worktrees=tmp_path / "wt",
            records=tmp_path / "records",
            script=[("write_file", ["b.txt", "b\n"]), ("bash", ["git add -A && git commit -qm b"])],
        )

    deps = Deps(
        responder=lambda _s: Says(["x"]),
        start_agent=agent_starter(table, "s_a", repo, start_build, lambda *_a: []),
        workdir=repo,
    )
    plan = check('make: agent as build "Add b.txt."').plan
    assert plan is not None
    start_composed(
        table,
        owner="s_a",
        run_id="r_c",
        plan=plan,
        run_input="",
        deps=deps,
        records=tmp_path / "runs",
    )
    _wait(table, "s_a", "r_c")
    ended = {e.run_id: e for e in table.drain_ended("s_a")}
    assert ended["r_b1"].outcome is RunOutcome.DONE  # the agent step's own run, told too
    result = ended["r_c"].result
    assert result is not None and result.ended_on is None
    assert result.event is not None and result.event["branch"] == "build/r_b1"
    assert result.event["files"] == ["b.txt"]
    head = subprocess.run(
        ["git", "-C", str(repo), "branch", "--show-current"], capture_output=True, text=True
    ).stdout.strip()
    assert head != "build/r_b1"
