"""UI sprint 107: glob and grep stop at their caps and at the user's interrupt.

A model in the Axis B shakeout called `glob("**/*", "/")`. The tool sorted every match on the
disk before applying its 200-hit cap (grep sorted `rglob("*")` the same way), and the walk ran in
a worker thread that the interrupt could not reach, so the turn ran past the flow's 300 s limit.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from substrate.topologies.tool_loop import tools
from substrate.topologies.tool_loop.tools import ToolCancelled, _glob, _grep


def test_glob_from_the_filesystem_root_stops_at_the_cap() -> None:
    t0 = time.monotonic()
    hits = _glob(Path("/"), ["**/*", "/"])
    assert time.monotonic() - t0 < 10
    assert len(hits) == tools._MAX_GLOB_HITS + 1
    assert hits[-1].startswith("… (more than")


def test_grep_stops_at_the_cap(tmp_path: Path) -> None:
    for i in range(30):
        (tmp_path / f"f{i:02}.txt").write_text("needle\n" * 10)
    hits = _grep(tmp_path, ["needle"])
    assert len(hits) == tools._MAX_GREP_HITS + 1
    assert hits[-1].startswith("… (capped at")


def test_a_cancel_stops_the_walk_between_directories(tmp_path: Path) -> None:
    """run_tool runs the hooks a tool registered when its call is cancelled; the walk's hook sets
    an event it checks at every directory."""
    (tmp_path / "first.txt").write_text("x")
    for i in range(50):
        (tmp_path / f"d{i:02}").mkdir()
        (tmp_path / f"d{i:02}" / "f.txt").write_text("x")
    hooks: list = []
    token = tools._TOOL_CANCEL_HOOKS.set(hooks)
    try:
        walk = tools._walk_files(tmp_path)
        assert next(walk).name == "first.txt"
        assert len(hooks) == 1, "the walk registered its stop with run_tool"
        hooks[0]()  # what run_tool does when the user interrupts
        with pytest.raises(ToolCancelled):
            next(walk)
    finally:
        tools._TOOL_CANCEL_HOOKS.reset(token)
