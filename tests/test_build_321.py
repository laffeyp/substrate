# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 321: Build. One card worked in its own worktree on a new branch until its checks
pass or it cannot close; the report and the branch come back to the caller; nothing is merged."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.runs.build import (
    DEFAULT_LIMITS,
    card_from_form,
    make_build_tool,
    start_build,
)
from substrate.topologies.runs.card import read_card
from substrate.topologies.runs.hold import RunTable
from substrate.topologies.session.vocabulary import RunLimits, RunOutcome
from substrate.topologies.workspace import ensure_repository

pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")

FIXTURES = Path(__file__).parent / "fixtures" / "cards"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("a\n")
    ensure_repository(repo)
    return repo


def _wait(table: RunTable, run_id: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while table.running("caller", run_id):
        assert time.monotonic() < deadline, "the run did not end"
        time.sleep(0.05)


def _build(
    table: RunTable,
    tmp_path: Path,
    repo: Path,
    *,
    commands: list[str],
    script: list[tuple[str, list[Any]]],
    limits: RunLimits = DEFAULT_LIMITS,
    model_class: str = "large",
    context_tokens: int = 8192,
) -> tuple[str, str]:
    card = read_card(
        what="add b.txt", where=["b.txt"], commands=commands, statements=[], limits=limits
    )
    return start_build(
        table,
        owner="caller",
        run_id="r_b",
        repo=repo,
        card=card,
        driver_for=lambda _wt: DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=context_tokens,
        model_class=model_class,
        bundle=None,
        worktrees=tmp_path / "wt",
        records=tmp_path / "records",
        check_timeout_s=30,
        script=script,
    )


WRITE_AND_COMMIT = [("write_file", ["b.txt", "b\n"]), ("bash", ["git add -A && git commit -qm b"])]


def test_a_build_ends_done_with_its_branch_commits_and_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    (home / "memory").mkdir(parents=True)
    (home / "memory" / "MEMORY.md").write_text("- a note the worker must not read\n")
    monkeypatch.setenv("SUBSTRATE_HOME", str(home))
    repo = _repo(tmp_path)
    head_before = _git(repo, "rev-parse", "HEAD")
    table = RunTable()
    run_id, branch = _build(
        table, tmp_path, repo, commands=["test -f b.txt"], script=WRITE_AND_COMMIT
    )
    assert (run_id, branch) == ("r_b", "build/r_b")
    _wait(table, run_id)
    (ended,) = table.drain_ended("caller")
    assert ended.outcome is RunOutcome.DONE and ended.report is not None
    report = ended.report
    assert report.branch == "build/r_b" and report.files == ["b.txt"] and len(report.commits) == 1
    assert report.checks[0].passed is True
    assert _git(repo, "rev-parse", "build/r_b~1") == head_before  # one commit on the branch
    assert _git(repo, "rev-parse", "HEAD") == head_before  # never merged
    assert not (repo / "b.txt").exists()
    events = list(api.read_record(tmp_path / "records" / run_id))
    roles = [
        e for e in events if e["kind"] == "PromptFragment" and e["payload"]["source"] == "role"
    ]
    assert roles and roles[0]["payload"]["provenance"]["role_name"] == "default"
    sources = {e["payload"]["source"] for e in events if e["kind"] == "PromptFragment"}
    assert "memory" not in sources  # the worktree is the only context
    first = next(e for e in events if e["kind"] == "UserMessage")["payload"]["text"]
    assert "build/r_b" in first and "What to do: add b.txt" in first and "- test -f b.txt" in first


def test_a_small_model_reads_the_small_role(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    table = RunTable()
    run_id, _ = _build(
        table,
        tmp_path,
        repo,
        commands=["test -f b.txt"],
        script=WRITE_AND_COMMIT,
        model_class="small",
    )
    _wait(table, run_id)
    events = list(api.read_record(tmp_path / "records" / run_id))
    roles = [
        e for e in events if e["kind"] == "PromptFragment" and e["payload"]["source"] == "role"
    ]
    assert roles[0]["payload"]["provenance"]["role_name"] == "default-small"


def test_a_card_whose_check_cannot_pass_ends_stuck(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    table = RunTable()
    run_id, _ = _build(
        table,
        tmp_path,
        repo,
        commands=["test -f never.txt"],
        script=WRITE_AND_COMMIT,
        limits=RunLimits(max_stops=3, stall_stops=2),
    )
    _wait(table, run_id)
    (ended,) = table.drain_ended("caller")
    assert ended.outcome is RunOutcome.STUCK and ended.report is not None
    assert ended.report.left and ended.report.checks[0].passed is False


def test_a_card_bigger_than_the_model_holds_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    table = RunTable()
    with pytest.raises(ValueError, match="split the card"):
        _build(
            table,
            tmp_path,
            repo,
            commands=["test -f b.txt " + "x" * 4000],
            script=[],
            context_tokens=1000,
        )
    assert not (tmp_path / "wt").exists()


def test_the_build_tool_reads_a_plain_or_sdd_card(tmp_path: Path) -> None:
    started: list[Any] = []
    tool = make_build_tool(lambda card: started.append(card) or ("r", "build/r"), tmp_path)
    assert tool.run([{"what": "x", "where": ["a"], "commands": ["true"], "max_turns": 2}]) == {
        "run_id": "r",
        "branch": "build/r",
    }
    assert started[-1].limits == RunLimits(max_stops=2, stall_stops=DEFAULT_LIMITS.stall_stops)
    with pytest.raises(ValueError, match="how to tell it is done"):
        tool.run([{"what": "x", "where": ["a"]}])
    sdd = next(FIXTURES.glob("*.md"))
    (tmp_path / "card.md").write_text(sdd.read_text())
    card = card_from_form({"card_file": "card.md"}, tmp_path)
    assert card.form.value == "sdd"
    with pytest.raises(ValueError, match="outside the workspace"):
        card_from_form({"card_file": "../card.md"}, tmp_path / "sub")
