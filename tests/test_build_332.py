# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 332: Build (research r9 § 2, § 8.1). One task worked in its own worktree on a new
branch; only the task is required; whatever else the caller gives is laid out for the worker; the
report and branch come back; nothing is merged and nothing grades it."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.runs.build import Card, card_from_form, make_build_tool, start_build
from substrate.topologies.runs.hold import RunTable
from substrate.topologies.session.vocabulary import RunOutcome
from substrate.topologies.workspace import ensure_repository

pytestmark = pytest.mark.filterwarnings(r"ignore:session_topology\(record_root=None\)")

WRITE_AND_COMMIT = [("write_file", ["b.txt", "b\n"]), ("bash", ["git add -A && git commit -qm b"])]


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


def _build(
    tmp_path: Path, repo: Path, card: Card, model_class: str = "large"
) -> tuple[RunTable, str]:
    table = RunTable()
    run_id, branch = start_build(
        table,
        owner="caller",
        run_id="r_b",
        repo=repo,
        card=card,
        driver_for=lambda _wt: DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=8192,
        model_class=model_class,
        bundle=None,
        worktrees=tmp_path / "wt",
        records=tmp_path / "records",
        script=WRITE_AND_COMMIT,
    )
    deadline = time.monotonic() + 60
    while table.running("caller", run_id):
        assert time.monotonic() < deadline, "the build did not end"
        time.sleep(0.05)
    assert branch == "build/r_b"
    return table, run_id


def _events(tmp_path: Path) -> list[dict[str, Any]]:
    return list(api.read_record(tmp_path / "records" / "r_b", resolve_blobs=True))


def test_a_bare_task_builds_on_its_branch_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    (home / "memory").mkdir(parents=True)
    (home / "memory" / "MEMORY.md").write_text("- a note the builder must not read\n")
    monkeypatch.setenv("SUBSTRATE_HOME", str(home))
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD")
    table, run_id = _build(tmp_path, repo, Card(task="add b.txt"))
    (ended,) = table.drain_ended("caller")
    report = ended.report
    assert ended.outcome is RunOutcome.DONE and report is not None
    assert report.branch == "build/r_b" and report.files == ["b.txt"] and len(report.commits) == 1
    assert _git(repo, "rev-parse", "HEAD") == head and not (repo / "b.txt").exists()  # not merged
    events = _events(tmp_path)
    first = next(e for e in events if e["kind"] == "UserMessage")["payload"]["text"]
    assert "build/r_b" in first and "Task: add b.txt" in first and "Files:" not in first
    sources = {e["payload"]["source"] for e in events if e["kind"] == "PromptFragment"}
    assert "memory" not in sources  # the worktree is the only context
    roles = [
        e for e in events if e["kind"] == "PromptFragment" and e["payload"]["source"] == "role"
    ]
    assert roles[0]["payload"]["provenance"]["role_name"] == "default"


def test_every_field_given_reaches_the_builder(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    card = Card(
        task="add b.txt",
        files=["b.txt"],
        read_first=["a.txt"],
        notes="keep it short",
        text="## scope\nb",
    )
    _build(tmp_path, repo, card, model_class="small")
    events = _events(tmp_path)
    first = next(e for e in events if e["kind"] == "UserMessage")["payload"]["text"]
    for part in ("Files: b.txt", "Read first: a.txt", "keep it short", "## scope"):
        assert part in first
    roles = [
        e for e in events if e["kind"] == "PromptFragment" and e["payload"]["source"] == "role"
    ]
    assert roles[0]["payload"]["provenance"]["role_name"] == "default-small"


def test_the_tool_takes_a_task_alone_or_a_card(tmp_path: Path) -> None:
    started: list[Card] = []
    tool = make_build_tool(lambda c: started.append(c) or ("r", "build/r"), tmp_path)
    assert tool.run([{"task": "add b.txt"}]) == {"run_id": "r", "branch": "build/r"}
    assert started[-1] == Card(task="add b.txt")
    tool.run(["add c.txt"])  # a bare string is the task
    assert started[-1].task == "add c.txt"
    (tmp_path / "card.md").write_text("## scope\nadd d.txt\n")
    assert card_from_form({"task": "d", "card_file": "card.md"}, tmp_path).text.startswith(
        "## scope"
    )
    with pytest.raises(ValueError, match="task"):
        tool.run([{"files": ["x"]}])
    with pytest.raises(ValueError, match="outside the workspace"):
        card_from_form({"task": "x", "card_file": "../card.md"}, tmp_path / "sub")
    assert tool.schema["required"] == ["task"]
    assert set(tool.schema["properties"]) == {
        "task",
        "files",
        "read_first",
        "notes",
        "card",
        "card_file",
    }
