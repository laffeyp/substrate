# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 322: the checking role judges a card's statement checks (vocabulary § X.3
v0.12.4). One model call apart from the worker reads the card, the diff and the worker's reply;
its answer per statement is the statement's result; a statement that fails keeps the run going."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.runs.card import read_card
from substrate.topologies.runs.checks import read_verdicts
from substrate.topologies.runs.driven import DrivenRun
from substrate.topologies.runs.hold import RunTable
from substrate.topologies.session import session_topology
from substrate.topologies.session.vocabulary import (
    CheckKind,
    RunLimits,
    RunOutcome,
    RunRole,
    RunSession,
)
from substrate.topologies.tool_loop.tools import full_suite
from substrate.topologies.workspace import ensure_repository

pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")

STATEMENT = "b.txt says hello"
WRITE_AND_COMMIT = [
    ("write_file", ["b.txt", "hello\n"]),
    ("bash", ["git add -A && git commit -qm b"]),
]


def _run(tmp_path: Path, judge_says: str, limits: RunLimits) -> tuple[Any, list[dict[str, Any]]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("a\n")
    ensure_repository(repo)
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    card = read_card(
        what="add b.txt",
        where=["b.txt"],
        commands=["test -f b.txt"],
        statements=[STATEMENT],
        limits=limits,
    )
    factory = session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=4096,
        seed="",
        tools=full_suite(repo),
        session_id="s_run",
        workspace_path=str(repo),
        script=WRITE_AND_COMMIT,
        driven=DrivenRun(
            card=card,
            worktree=repo,
            base=base,
            check_timeout_s=30,
            first_message="go",
            judge=DeterministicResponder(seed=0, menu=[judge_says]),
        ),
    )
    table = RunTable()
    root = tmp_path / "run"
    session = RunSession(
        session_id="s_run", role=RunRole.WORKER, record_root=str(root), driven=True
    )
    table.start("caller", "r", "build", [session], factory, root)
    deadline = time.monotonic() + 60
    while table.running("caller", "r"):
        assert time.monotonic() < deadline, "the run did not end"
        time.sleep(0.05)
    (ended,) = table.drain_ended("caller")
    return ended, list(api.read_record(root, resolve_blobs=True))


def test_a_statement_that_holds_ends_the_run_done(tmp_path: Path) -> None:
    ended, events = _run(
        tmp_path, "S1: holds — b.txt is added with the line hello", RunLimits(3, 3)
    )
    assert ended.outcome is RunOutcome.DONE
    statement = next(c for c in ended.report.checks if c.kind is CheckKind.STATEMENT)
    assert statement.passed is True and statement.note == "b.txt is added with the line hello"
    checks = [e["payload"] for e in events if e["kind"] == "ChecksRun"]
    judge = checks[-1]["judge"]
    assert judge["model"] and judge["reply"].startswith("S1: holds")
    assert f"S1: {STATEMENT}" in judge["prompt"] and "+hello" in judge["prompt"]


def test_a_statement_that_does_not_hold_keeps_the_run_going(tmp_path: Path) -> None:
    ended, events = _run(tmp_path, "S1: does not hold — it says hi", RunLimits(2, 5))
    assert ended.outcome is RunOutcome.STUCK
    turns = [e["payload"]["text"] for e in events if e["kind"] == "UserMessage"]
    assert len(turns) == 2
    assert f"- {STATEMENT}: does not hold (it says hi)" in turns[1]
    assert all(e["payload"]["passed"] is False for e in events if e["kind"] == "ChecksRun")


def test_a_judge_reply_that_does_not_answer_fails_the_statement(tmp_path: Path) -> None:
    ended, _ = _run(tmp_path, "looks fine to me", RunLimits(1, 1))
    assert ended.outcome is RunOutcome.STUCK
    statement = next(c for c in ended.report.checks if c.kind is CheckKind.STATEMENT)
    assert statement.passed is False and statement.note == "the judge's reply did not answer S1"


def test_verdicts_are_read_line_by_line() -> None:
    card = read_card(
        what="x",
        where=["x"],
        commands=["true"],
        statements=["one", "two", "three"],
        limits=RunLimits(1, 1),
    )
    reply = "**S1: Holds** — fine\n- S2: does not hold: missing\nS2: holds - changed my mind\n"
    assert read_verdicts(card, reply) == {
        1: (True, "fine"),
        2: (True, "changed my mind"),
        3: (False, "the judge's reply did not answer S3"),
    }
