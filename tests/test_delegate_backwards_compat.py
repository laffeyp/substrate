# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 212 — every existing `make_delegate(...)` call still works.

The sprint adds three new optional constructor kwargs (`session_registry`,
`parent_session_id`, `parent_record_root`) and grows `Tool.run(a)` to accept
either a string (old shape) or a dict (new shape from `_named_to_positional`
under `x-args-passthrough`). This file locks the backwards-compat contract so
sprint 213's dispatch-path wiring cannot silently break the pre-sprint-212
call surface.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.adapters import DeterministicResponder
from substrate.topologies.tool_loop.delegate import make_delegate


def _mk(root: Path) -> object:
    return make_delegate(responder=DeterministicResponder(seed=0), root=root)


def test_construct_with_only_the_original_kwargs(tmp_path: Path) -> None:
    """A pre-sprint-212 constructor call — no session_registry, no parent_session_id,
    no parent_record_root — builds a Tool with the delegate schema.
    """
    d = _mk(tmp_path)
    assert d.name == "delegate"
    assert "task" in d.schema["properties"]
    assert d.schema["required"] == ["task"]


def test_construct_with_new_optional_kwargs_defaulting_none(tmp_path: Path) -> None:
    """The three new kwargs default `None`. A caller passing them explicitly gets
    the same Tool shape.
    """
    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=tmp_path,
        session_registry=None,
        parent_session_id=None,
        parent_record_root=None,
    )
    assert d.name == "delegate"


def test_run_with_a_bare_string_task_still_works(tmp_path: Path) -> None:
    """Pre-sprint-212 callers passed `run(["hello"])`. That must keep working."""
    d = _mk(tmp_path)
    result = d.run(["hello world"])
    assert isinstance(result, dict)
    assert set(result.keys()) == {"answer", "child_root", "steps"}
    assert Path(result["child_root"]).exists()


def test_run_with_empty_list_does_not_crash(tmp_path: Path) -> None:
    """An empty `a` reads as `task=""` per the old shape."""
    d = _mk(tmp_path)
    result = d.run([])
    assert isinstance(result, dict)
    assert result["answer"] is not None


def test_max_depth_raise_survives_the_new_parse(tmp_path: Path) -> None:
    """Depth-cap refusal fires the same way it did before sprint 212."""
    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=tmp_path,
        depth=2,
        max_depth=2,
    )
    with pytest.raises(ValueError, match="max delegation depth"):
        d.run(["hi"])


def test_max_children_raise_survives_the_new_parse(tmp_path: Path) -> None:
    """Fan-out-cap refusal fires the same way it did before sprint 212."""
    d = make_delegate(
        responder=DeterministicResponder(seed=0),
        root=tmp_path,
        max_children=1,
    )
    d.run(["one"])
    with pytest.raises(ValueError, match="max children"):
        d.run(["two"])
