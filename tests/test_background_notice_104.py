"""UI sprint 104: the model hears when a background task ends.

Invariants 1–4 on process/sprints/sprint-104-the-model-hears-when-a-task-ends.md.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.session_registry import SessionManifest, SessionRegistry
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.tool_loop import tools as T
from substrate.topologies.tool_loop.background import TABLE


class _Recording(DeterministicResponder):
    def __init__(self) -> None:
        super().__init__(seed=0)
        self.prompts: list[str] = []

    async def arespond(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.respond(prompt)


def _registry(tmp_path: Path, responder: Any, script: Any = None) -> SessionRegistry:
    def factory(m: SessionManifest, first: Any = None) -> Any:
        suite = T.full_suite(Path(m.workspace), owner=m.session_id)
        return session_topology(
            driver=responder,
            driver_name="deterministic",
            driver_context_tokens=8192,
            seed="",
            tools={k: suite[k] for k in ("bash", "bash_output", "bash_stop")},
            per_turn="",
            max_turns=50,
            turn_max_steps=6,
            session_id=m.session_id,
            workspace_path=m.workspace,
            record_root=Path(m.record_root),
            script=script,
            first_turn_user_message=first,
        )

    return SessionRegistry(base=tmp_path / "sessions", session_topology_factory=factory)


def _session(reg: SessionRegistry, tmp_path: Path, sid: str) -> str:
    (tmp_path / "ws").mkdir(exist_ok=True)
    reg.create(
        session_id=sid,
        name=None,
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="",
    )
    return sid


def _turn(reg: SessionRegistry, sid: str, text: str) -> Path:
    _, root = reg.turn_sync(
        sid,
        resume_event_builder=lambda _m, _r: UserMessage(
            text=text,
            turn_index=reg.next_turn_index(sid),
            assembled_prompt=text,
            slash_source="user",
        ),
    )
    return root


def _ended_events(root: Path) -> list[dict[str, Any]]:
    return [e for e in api.read_record(root) if e["kind"] == "BackgroundTaskEnded"]


@pytest.fixture(autouse=True)
def _cleanup() -> Any:
    yield
    for sid in ("s_0000000000000104", "s_00000000000001a4", "s_00000000000001b4"):
        TABLE.stop_owner(sid, "test teardown")


def test_1_a_task_that_ends_mid_turn_is_recorded_before_the_next_step(tmp_path: Path) -> None:
    script = [("bash", ["sleep 0.3; echo hi", None, True]), ("bash", ["sleep 1.5"])]
    reg = _registry(tmp_path, DeterministicResponder(seed=0), script=script)
    sid = _session(reg, tmp_path, "s_0000000000000104")
    root = _turn(reg, sid, "go")
    envs = list(api.read_record(root))
    kinds = [e["kind"] for e in envs]
    assert kinds.count("BackgroundTaskEnded") == 1, kinds
    i_ended = kinds.index("BackgroundTaskEnded")
    i_second_result = [i for i, k in enumerate(kinds) if k == "ToolResult"][1]
    i_final = kinds.index("FinalAnswer")
    assert i_second_result < i_ended < i_final, "told after the step that ran past the ending"
    payload = envs[i_ended]["payload"]
    assert (
        payload["status"] == "exited" and payload["exit"] == 0 and payload["stdout_tail"] == "hi\n"
    )


def test_2_and_4_a_task_that_ends_while_parked_is_told_once_at_the_next_turn(
    tmp_path: Path,
) -> None:
    responder = _Recording()
    reg = _registry(tmp_path, responder)
    sid = _session(reg, tmp_path, "s_00000000000001a4")
    _turn(reg, sid, "first")
    r = T._bash(tmp_path, sid, ["sleep 0.2; echo BUILT-104", None, True])
    deadline = time.monotonic() + 5
    while TABLE.get(sid, r["task_id"]).poll() == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
    n_before = len(responder.prompts)
    root = _turn(reg, sid, "second")
    first_step = responder.prompts[n_before]
    assert f"[background task {r['task_id']} (sleep 0.2; echo BUILT-104) exited 0" in first_step
    assert "BUILT-104" in first_step
    _turn(reg, sid, "third")
    assert len(_ended_events(root)) == 1, "an ending is recorded once"


def test_3_a_stop_the_model_asked_for_is_not_reported_but_an_owner_rule_stop_is(
    tmp_path: Path,
) -> None:
    reg = _registry(tmp_path, DeterministicResponder(seed=0))
    sid = _session(reg, tmp_path, "s_00000000000001b4")
    root = _turn(reg, sid, "first")
    asked = T._bash(tmp_path, sid, ["sleep 30", None, True])
    T._bash_stop(sid, [asked["task_id"]])
    ruled = T._bash(tmp_path, sid, ["sleep 30", None, True])
    TABLE.stop(TABLE.get(sid, ruled["task_id"]), "its delegated run ended")
    _turn(reg, sid, "second")
    told = [e["payload"]["task_id"] for e in _ended_events(root)]
    assert told == [ruled["task_id"]], told
