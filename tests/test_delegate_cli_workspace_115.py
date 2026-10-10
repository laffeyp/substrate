# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""UI sprint 115: a delegated child on a CLI driver runs in its own workspace.

The CLI prints its working directory and nothing else, so the child's tool loop takes that line
as its answer. Before the sprint a fresh child (path 4) ran in the parent's directory, a `model=`
child (path 2) in whatever directory the resolver gave it (the server's, for the daemon), and a
nested delegate lost `model_resolver`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from substrate.adapters import DeterministicResponder
from substrate.adapters.models import CliResponder
from substrate.topologies.tool_loop import delegate as delegate_module
from substrate.topologies.tool_loop.delegate import make_delegate

_PWD = [sys.executable, "-c", "import os; print(os.getcwd())"]


def _child_workspace(result: dict[str, Any]) -> Path:
    return Path(result["child_root"]).parent / "workspace"


def test_at_returns_a_new_responder_in_the_new_folder(tmp_path: Path) -> None:
    base = CliResponder(_PWD, name="pwd", cwd=tmp_path / "a")
    moved = base.at(tmp_path)
    assert moved is not base
    assert moved.name == "pwd"
    assert Path(moved.respond("hi")) == tmp_path.resolve()
    assert base._cwd == tmp_path / "a"  # the original is untouched


def test_fresh_child_runs_in_its_own_workspace(tmp_path: Path) -> None:
    parent_ws = tmp_path / "parent"
    parent_ws.mkdir()
    tool = make_delegate(responder=CliResponder(_PWD, cwd=parent_ws), root=parent_ws)
    result = tool.run([{"task": "where are you"}])
    assert Path(result["answer"]) == _child_workspace(result).resolve()


def test_model_child_runs_in_its_own_workspace(tmp_path: Path) -> None:
    parent_ws = tmp_path / "parent"
    parent_ws.mkdir()
    tool = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=parent_ws,
        model_resolver=lambda name: CliResponder(_PWD, name=name),  # no folder, as the daemon's
    )
    result = tool.run([{"task": "where are you", "model": "claude"}])
    assert Path(result["answer"]) == _child_workspace(result).resolve()


def test_a_nested_delegate_keeps_the_model_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}
    real = delegate_module.make_delegate

    def spy(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return real(**kwargs)

    def resolver(name: str) -> CliResponder:
        return CliResponder(_PWD, name=name)

    factory = delegate_module._default_child_factory(
        CliResponder(_PWD),
        delegate_module.full_suite,
        0,
        5,
        16,
        64,
        {"remaining": 64},
        6,
        None,
        resolver,
    )
    monkeypatch.setattr(delegate_module, "make_delegate", spy)
    factory("task", tmp_path / "d1-c0" / "workspace")
    assert seen["model_resolver"] is resolver
