# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 315: every workspace is a git repository; worktrees come from the kernel.
Written before `topologies/workspace.py` existed."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from substrate.topologies.session_registry import SessionRegistry
from substrate.topologies.workspace import ensure_repository, make_worktree, worktree_diff


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    ).stdout


def _commits(path: Path) -> int:
    return int(_git(path, "rev-list", "--count", "HEAD").strip())


def test_a_plain_folder_becomes_a_repository_with_one_commit_of_what_it_holds(
    tmp_path: Path,
) -> None:
    ws = tmp_path / "notes"
    ws.mkdir()
    (ws / "a.txt").write_text("hello\n")
    assert ensure_repository(ws) is True
    assert (ws / ".git").is_dir()
    assert _commits(ws) == 1
    assert _git(ws, "ls-files").split() == ["a.txt"]
    assert _git(ws, "status", "--porcelain") == ""


def test_an_empty_folder_gets_an_empty_first_commit(tmp_path: Path) -> None:
    ws = tmp_path / "empty"
    ws.mkdir()
    assert ensure_repository(ws) is True
    assert _commits(ws) == 1


def test_a_repository_and_a_folder_inside_one_are_left_alone(tmp_path: Path) -> None:
    ws = tmp_path / "repo"
    ws.mkdir()
    (ws / "a.txt").write_text("a\n")
    ensure_repository(ws)
    (ws / "b.txt").write_text("b\n")
    assert ensure_repository(ws) is False
    assert _commits(ws) == 1  # nothing committed on the user's behalf
    inner = ws / "sub"
    inner.mkdir()
    assert ensure_repository(inner) is False
    assert not (inner / ".git").exists()  # no repository nested in another


def test_a_worktree_on_its_own_branch_and_its_diff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("hello\n")
    ensure_repository(repo)
    wt = make_worktree(repo, "substrate/build/r_1", tmp_path / "wt" / "r_1")
    assert (wt / "a.txt").read_text() == "hello\n"
    assert _git(wt, "rev-parse", "--abbrev-ref", "HEAD").strip() == "substrate/build/r_1"
    assert make_worktree(repo, "substrate/build/r_1", tmp_path / "wt" / "r_1") == wt  # idempotent
    (wt / "a.txt").write_text("changed\n")
    (wt / "new.py").write_text("print('hi')\n")
    before = _git(wt, "status", "--porcelain")
    d = worktree_diff(wt)
    assert "a.txt" in d["diff"] and "new.py" in d["diff"]
    assert any("new.py" in f for f in d["files"])
    assert _git(wt, "status", "--porcelain") == before  # the worktree's index is not written
    with pytest.raises(ValueError, match="not a git repository"):
        make_worktree(tmp_path / "nope", "b", tmp_path / "wt" / "nope")


def test_the_registry_makes_every_workspace_a_repository_and_a_branch_on_request(
    tmp_path: Path,
) -> None:
    reg = SessionRegistry(base=tmp_path / "sessions")
    ws = tmp_path / "project"
    ws.mkdir()
    (ws / "main.py").write_text("x = 1\n")
    m = reg.create(
        session_id="s_aaaaaaaa",
        name=None,
        driver="deterministic",
        workspace=str(ws),
        workspace_shape="flat",
        bundle=None,
        seed="",
    )
    assert m.workspace == str(ws) and (ws / ".git").is_dir() and _commits(ws) == 1
    b = reg.create(
        session_id="s_bbbbbbbb",
        name=None,
        driver="deterministic",
        workspace=str(ws),
        workspace_shape="flat",
        bundle=None,
        seed="",
        branch="substrate/build/r_2",
    )
    assert b.workspace_shape == "worktree" and b.workspace != str(ws)
    assert (
        _git(Path(b.workspace), "rev-parse", "--abbrev-ref", "HEAD").strip()
        == "substrate/build/r_2"
    )
    assert (Path(b.workspace) / "main.py").read_text() == "x = 1\n"


def test_two_sessions_opening_on_one_folder_at_once_make_one_repository(tmp_path: Path) -> None:
    # Found by the app's /api/agent concurrency test: the second `git commit` hit the first's
    # index.lock and the session failed to open.
    import threading

    ws = tmp_path / "shared"
    ws.mkdir()
    (ws / "a.txt").write_text("a\n")
    made: list[bool] = []
    errors: list[BaseException] = []

    def open_it() -> None:
        try:
            made.append(ensure_repository(ws))
        except BaseException as exc:  # noqa: BLE001 — collected for the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=open_it) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert errors == []
    assert sorted(made) == [False] * 7 + [True]
    assert _commits(ws) == 1
