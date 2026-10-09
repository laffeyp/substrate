"""UI sprint 101: the bash tool's deadline covers the whole command.

2026-10-02, session s_74df6e70…, turn 28: the model ran `node server.js & … kill %1`. In a
non-interactive shell `%1` names no job, so the server kept the tool's stdout pipe open; the
tool's read loop had no deadline (its 60 s limit applied only after stdout closed), and the turn
sat for ten minutes until the daemon's turn cap cancelled it. Cancelling did not stop the tool's
thread, so the server was still listening on :3001 after the turn was cancelled.
"""

from __future__ import annotations

import os
import signal
import threading
import time
from pathlib import Path

import pytest

from substrate.topologies.tool_loop.background import TABLE
from substrate.topologies.tool_loop.tools import (
    _TOOL_CANCEL_HOOKS,
    BASH_MAX_TIMEOUT_S,
    _bash,
)

OWNER = "test:bash_deadline_101"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_background_child_holding_the_pipe_does_not_block(tmp_path: Path) -> None:
    pidfile = tmp_path / "child.pid"
    t0 = time.monotonic()
    out = _bash(tmp_path, OWNER, [f"sleep 30 & echo $! > {pidfile}; echo hi"])
    elapsed = time.monotonic() - t0
    child = int(pidfile.read_text())
    try:
        assert elapsed < 5, f"bash waited {elapsed:.1f} s on a backgrounded child"
        assert out["exit"] == 0 and out["stdout"] == "hi\n"
        # UI sprint 103: the leftover child becomes a background task, still running
        assert out["background_task_id"].startswith("bg_")
        assert _alive(child), "a backgrounded child keeps running, as in a terminal"
    finally:
        TABLE.stop_owner(OWNER, "test teardown")


def test_deadline_kills_the_command_and_everything_it_started(tmp_path: Path) -> None:
    pidfile = tmp_path / "child.pid"
    t0 = time.monotonic()
    out = _bash(tmp_path, OWNER, [f"sleep 30 & echo $! > {pidfile}; echo started; sleep 30", 1])
    elapsed = time.monotonic() - t0
    assert elapsed < 5, f"a 1 s deadline took {elapsed:.1f} s"
    assert out["timed_out"] is True
    assert out["stdout"] == "started\n", "output before the deadline comes back"
    assert "killed after 1 s" in out["stderr"]
    time.sleep(0.2)
    assert not _alive(int(pidfile.read_text())), "the backgrounded child died with the group"


def test_timeout_bounds(tmp_path: Path) -> None:
    for bad in (0, -1, BASH_MAX_TIMEOUT_S + 1):
        with pytest.raises(ValueError, match="timeout_s"):
            _bash(tmp_path, OWNER, ["true", bad])


def test_a_full_stderr_pipe_does_not_deadlock(tmp_path: Path) -> None:
    # stderr was read only after stdout closed; 200 KB fills a 64 KB pipe and blocks the writer.
    out = _bash(
        tmp_path,
        OWNER,
        ["python3 -c \"import sys; sys.stderr.write('x' * 200000); print('done')\""],
    )
    assert out["exit"] == 0 and out["stdout"] == "done\n"


def test_killing_the_registered_group_ends_the_call(tmp_path: Path) -> None:
    # run_tool's cancel path: it runs every hook the call registered in _TOOL_CANCEL_HOOKS.
    hooks: list = []
    box: dict = {}

    def call() -> None:
        _TOOL_CANCEL_HOOKS.set(hooks)
        box["out"] = _bash(tmp_path, OWNER, ["sleep 30"])

    worker = threading.Thread(target=call)
    t0 = time.monotonic()
    worker.start()
    while not hooks and time.monotonic() - t0 < 5:
        time.sleep(0.05)
    hooks[0]()
    worker.join(5)
    assert not worker.is_alive(), "the tool thread returned once its process group died"
    assert time.monotonic() - t0 < 5
    assert box["out"]["exit"] == -signal.SIGKILL
