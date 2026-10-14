"""UI sprint 103: supervised background commands for the bash tool.

One test per invariant on process/sprints/sprint-103-supervised-background-commands.md. Reference
behaviour: Claude Code's Bash tool (code.claude.com/docs/en/tools-reference, "Background commands").
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest

from substrate.topologies.tool_loop import tools as T
from substrate.topologies.tool_loop.background import TABLE


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait(pred: Any, seconds: float = 10.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


@pytest.fixture
def owner(tmp_path: Path) -> Any:
    who = f"test:{tmp_path}"
    yield who
    TABLE.stop_owner(who, "test teardown")


def test_1_run_in_background_returns_at_once_and_output_is_read_later(
    tmp_path: Path, owner: str
) -> None:
    t0 = time.monotonic()
    r = T._bash(tmp_path, owner, ["sleep 1; echo built", None, True])
    assert time.monotonic() - t0 < 2
    assert r["status"] == "running" and r["task_id"].startswith("bg_")
    assert _wait(lambda: T._bash_output(owner, [r["task_id"]])["status"] == "exited")
    out = T._bash_output(owner, [r["task_id"]])
    assert out["exit"] == 0 and out["stdout"] == "built\n"
    nxt = T._bash_output(owner, [r["task_id"], out["next_offset"]])
    assert nxt["stdout"] == "", "reading from next_offset returns only new output"


def test_2_foreground_timeout_moves_to_background_except_sleep(tmp_path: Path, owner: str) -> None:
    killed = T._bash(tmp_path, owner, ["sleep 5; echo never", 1])
    assert killed.get("timed_out") is True and "never" not in killed["stdout"]

    moved = T._bash(
        tmp_path, owner, ["python3 -c \"import time; time.sleep(3); print('done')\"", 1]
    )
    assert moved["moved_to_background"] is True and moved["exit"] is None
    tid = moved["task_id"]
    assert _wait(lambda: T._bash_output(owner, [tid])["status"] == "exited", 15)
    assert T._bash_output(owner, [tid])["stdout"] == "done\n"


def test_3_stop_kills_the_group_and_a_descendant_that_left_it(tmp_path: Path, owner: str) -> None:
    pidfile = tmp_path / "setsid.pid"
    cmd = (
        f'python3 -c "import os,time; os.setsid(); time.sleep(60)" & echo $! > {pidfile}; sleep 60'
    )
    r = T._bash(tmp_path, owner, [cmd, None, True])
    assert _wait(lambda: pidfile.exists() and pidfile.read_text().strip() != "")
    escapee = int(pidfile.read_text())
    assert _wait(lambda: _alive(escapee))
    stopped = T._bash_stop(owner, [r["task_id"]])
    assert stopped["status"] == "stopped"
    assert _wait(lambda: not _alive(escapee), 5), "a child that called setsid() survived bash_stop"


def test_4_leftover_children_become_a_task_the_owner_stops(tmp_path: Path, owner: str) -> None:
    pidfile = tmp_path / "child.pid"
    t0 = time.monotonic()
    r = T._bash(tmp_path, owner, [f"sleep 30 & echo $! > {pidfile}; echo hi"])
    assert time.monotonic() - t0 < 3, "a backgrounded child held the call open"
    assert r["exit"] == 0 and r["stdout"] == "hi\n"
    tid = r["background_task_id"]
    assert T._bash_output(owner, [tid])["status"] == "running"
    child = int(pidfile.read_text())
    assert TABLE.stop_owner(owner, "session ended") == 1
    assert _wait(lambda: not _alive(child), 5), "the leftover child outlived its owner"


def test_5_a_delegated_childs_tasks_stop_when_the_child_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from substrate.adapters import DeterministicResponder
    from substrate.topologies.tool_loop import delegate as D

    started: dict[str, Any] = {}

    def fake_child(topology: Any, record_root: Path, *, timeout_seconds: Any) -> tuple[str, int]:
        workspace = record_root.parent / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        r = T._bash(workspace, str(workspace.resolve()), ["sleep 30", None, True])
        started["owner"], started["task"] = str(workspace.resolve()), r["task_id"]
        return "done", 1

    monkeypatch.setattr(D, "_run_child_to_answer", fake_child)
    tool = D.make_delegate(responder=DeterministicResponder(seed=0), root=tmp_path)
    out = tool.run([{"task": "start a server"}])
    assert out["answer"] == "done"
    task = TABLE.get(started["owner"], started["task"])
    assert task.poll() == "stopped" and task.stopped_because == "its delegated run ended"


def test_6_session_end_and_delete_stop_the_sessions_tasks(tmp_path: Path) -> None:
    from substrate.adapters import DeterministicResponder
    from substrate.topologies.session import SessionEndRequested, UserMessage, session_topology
    from substrate.topologies.session_registry import SessionManifest, SessionRegistry

    def factory(m: SessionManifest, first: Any = None) -> Any:
        return session_topology(
            driver=DeterministicResponder(seed=0),
            driver_name="deterministic",
            driver_context_tokens=4096,
            seed="",
            tools={},
            per_turn="",
            max_turns=200,
            turn_max_steps=4,
            session_id=m.session_id,
            workspace_path=m.workspace,
            script=None,
            first_turn_user_message=first,
        )

    reg = SessionRegistry(base=tmp_path / "sessions", session_topology_factory=factory)
    for sid, how in (("s_00000000000000e1", "end"), ("s_00000000000000d1", "delete")):
        reg.create(
            session_id=sid,
            name=None,
            driver="deterministic",
            workspace=str(tmp_path),
            workspace_shape="flat",
            bundle=None,
            seed="",
        )
        reg.turn_sync(
            sid, UserMessage(text="hi", turn_index=0, assembled_prompt="hi", slash_source="user")
        )
        r = T._bash(tmp_path, sid, ["sleep 30", None, True])
        if how == "end":
            reg.turn_sync(sid, SessionEndRequested(session_id=sid, source="user"))
            because = "its session ended"
        else:
            reg.delete(sid)
            because = "its session was deleted"
        task = TABLE.get(sid, r["task_id"])
        assert task.poll() == "stopped" and task.stopped_because == because, how


def test_7_output_over_the_cap_stops_the_task(
    tmp_path: Path, owner: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(TABLE, "_cap", 20_000)
    cmd = "python3 -c \"import sys,time\nwhile True:\n sys.stdout.write('x'*1000); sys.stdout.flush(); time.sleep(0.005)\""
    r = T._bash(tmp_path, owner, [cmd, None, True])
    assert _wait(lambda: T._bash_output(owner, [r["task_id"]])["status"] == "stopped", 10)
    out = T._bash_output(owner, [r["task_id"]])
    assert "output passed 20000 bytes" in (out["stopped_because"] or "")
    assert (
        "output passed 20000 bytes" in Path(TABLE.get(owner, r["task_id"]).stderr_file).read_text()
    )


def test_8_status_never_says_running_after_the_end(tmp_path: Path, owner: str) -> None:
    done = T._bash(tmp_path, owner, ["true", None, True])
    stopped = T._bash(tmp_path, owner, ["sleep 30", None, True])
    T._bash_stop(owner, [stopped["task_id"]])
    assert _wait(lambda: T._bash_output(owner, [done["task_id"]])["status"] == "exited")
    assert T._bash_output(owner, [stopped["task_id"]])["status"] == "stopped"
    statuses = {t["task_id"]: t["status"] for t in T._bash_tasks(owner, [])}
    assert statuses == {done["task_id"]: "exited", stopped["task_id"]: "stopped"}


def test_another_owner_cannot_see_or_stop_a_task(tmp_path: Path, owner: str) -> None:
    r = T._bash(tmp_path, owner, ["sleep 30", None, True])
    with pytest.raises(KeyError):
        T._bash_stop("someone-else", [r["task_id"]])
    assert T._bash_tasks("someone-else", []) == []
