# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K340 (editor shared item 0(d)): an application event appended to a session's record during a
turn or between turns.

`api.append_at_rest` appends to a PAUSED record without resuming it: the event, then the pause
restated, so the record still ends paused (kernel vocabulary v0.4, AT-REST APPEND).
`SessionRegistry.append_event` picks it between turns and the running turn's
`Runtime.inject_event` during one.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

import pytest
from msgspec import Struct

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.constants import BLOB_THRESHOLD_BYTES
from substrate.topologies.session import FileWritten, UserMessage, session_topology
from substrate.topologies.session_registry import (
    SessionManifest,
    SessionRegistry,
    SessionStatus,
    _scan_record_status,
)
from tests.test_resume import ApprovalGranted, pause_resume_topology


class Note(Struct, frozen=True):
    text: str


async def _paused(root: Path) -> list[dict[str, Any]]:
    result = await api.Runtime(root, persistent=True).run(pause_resume_topology)
    assert result.status == "paused"
    return list(api.read_record(root))


# ── the kernel call ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_append_at_rest_appends_the_event_and_restates_the_pause(tmp_path: Path) -> None:
    root = tmp_path / "rec"
    before = await _paused(root)
    pause = before[-1]
    assert pause["kind"] == api.TERMINATION_MATCHED

    seq = api.append_at_rest(root, Note(text="saved a.py"))

    after = list(api.read_record(root))
    assert after[: len(before)] == before, "nothing already on the record moves"
    assert seq == pause["seq"] + 1
    added = after[len(before) :]
    assert [e["kind"] for e in added] == ["Note", api.TERMINATION_MATCHED]
    assert added[0]["seq"] == seq and added[0]["producer"] is None
    assert added[0]["payload"] == {"text": "saved a.py"}
    assert added[1]["seq"] == seq + 1
    assert added[1]["payload"] == pause["payload"], "the pause is restated as it was"


@pytest.mark.asyncio
async def test_a_record_appended_at_rest_still_resumes(tmp_path: Path) -> None:
    root = tmp_path / "rec"
    await _paused(root)
    api.append_at_rest(root, Note(text="one"))
    api.append_at_rest(root, Note(text="two"))

    result = await api.Runtime(root, persistent=True).resume(
        pause_resume_topology, resume_event=ApprovalGranted(approved=True)
    )
    assert result.status == "finalised"
    envs = list(api.read_record(root))
    assert [e["seq"] for e in envs] == list(range(len(envs))), "one dense sequence"
    kinds = [e["kind"] for e in envs]
    assert kinds.count("Note") == 2
    assert kinds.index("Stage2Done") > kinds.index("ApprovalGranted") > kinds.index("Note")


@pytest.mark.asyncio
async def test_an_oversized_event_goes_to_the_blob_store(tmp_path: Path) -> None:
    root = tmp_path / "rec"
    await _paused(root)
    big = "x" * (BLOB_THRESHOLD_BYTES + 1)
    api.append_at_rest(root, Note(text=big))
    raw = [e for e in api.read_record(root) if e["kind"] == "Note"][0]
    assert "$blob" in raw["payload"]
    resolved = [e for e in api.read_record(root, resolve_blobs=True) if e["kind"] == "Note"][0]
    assert resolved["payload"] == {"text": big}


@pytest.mark.asyncio
async def test_refusals_leave_the_record_unchanged(tmp_path: Path) -> None:
    with pytest.raises(api.RecordNotAtRestError):
        api.append_at_rest(tmp_path / "none", Note(text="x"))

    class _Reserved(Struct, frozen=True):
        x: int

    _Reserved.__name__ = "substrate.Forged"
    root = tmp_path / "rec"
    await _paused(root)
    before = list(api.read_record(root))
    with pytest.raises(api.RegistrationError):
        api.append_at_rest(root, _Reserved(x=1))
    assert list(api.read_record(root)) == before

    finalised = tmp_path / "fin"
    result = await api.Runtime(finalised, persistent=True).run(
        lambda b: (
            b.producer_kind(
                "stage1",
                schemas=[api_stage1_done()],
                schema_version=1,
                factory=lambda: _stage1,
            ),
            b.initial("stage1", input=None),
        )
    )
    assert result.status == "finalised"
    ended = list(api.read_record(finalised))
    with pytest.raises(api.RecordNotAtRestError, match="RunFinalised"):
        api.append_at_rest(finalised, Note(text="x"))
    assert list(api.read_record(finalised)) == ended


def api_stage1_done() -> type:
    from tests.test_resume import Stage1Done

    return Stage1Done


async def _stage1(_input: Any) -> Any:
    from tests.test_resume import Stage1Done

    yield Stage1Done(value=1)


@pytest.mark.asyncio
async def test_a_live_run_holds_the_lock(tmp_path: Path) -> None:
    root = tmp_path / "rec"
    entered = asyncio.Event()
    release = asyncio.Event()

    async def _waits(_input: Any) -> Any:
        from tests.test_resume import Stage1Done

        entered.set()
        await release.wait()
        yield Stage1Done(value=1)

    def topology(b: api.TopologyBuilder) -> None:
        from tests.test_resume import Stage1Done

        b.producer_kind("stage1", schemas=[Stage1Done], schema_version=1, factory=lambda: _waits)
        b.initial("stage1", input=None)

    task = asyncio.create_task(api.Runtime(root, persistent=True).run(topology))
    await asyncio.wait_for(entered.wait(), timeout=10)
    with pytest.raises(api.BusLockedError):
        api.append_at_rest(root, Note(text="x"))
    release.set()
    assert (await task).status == "finalised"
    assert "Note" not in [e["kind"] for e in api.read_record(root)]


# ── the session registry ─────────────────────────────────────────────────────


class _HoldsOnCue(DeterministicResponder):
    """Blocks the model step on the prompt that says HOLD until the test releases it."""

    def __init__(self) -> None:
        super().__init__(seed=0)
        self.entered = threading.Event()
        self.release = threading.Event()

    async def arespond(self, prompt: str) -> str:
        if "HOLD" in prompt and not self.release.is_set():
            self.entered.set()
            await asyncio.to_thread(self.release.wait, 30)
        return self.respond(prompt)


def _registry(tmp_path: Path, responder: DeterministicResponder) -> SessionRegistry:
    def factory(manifest: SessionManifest, first_turn_user_message: Any = None) -> Any:
        return session_topology(
            driver=responder,
            driver_name="deterministic",
            driver_context_tokens=4096,
            seed=manifest.seed,
            tools={},
            per_turn="",
            max_turns=200,
            turn_max_steps=4,
            session_id=manifest.session_id,
            workspace_path=manifest.workspace,
            script=None,
            first_turn_user_message=first_turn_user_message,
        )

    return SessionRegistry(base=tmp_path / "sessions", session_topology_factory=factory)


def _create(reg: SessionRegistry, tmp_path: Path) -> str:
    return reg.create(
        session_id="s_0123456789abcdef",
        name=None,
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="",
    ).session_id


def _turn(reg: SessionRegistry, sid: str, text: str) -> Any:
    def build(_m: SessionManifest, _root: Path) -> UserMessage:
        return UserMessage(
            text=text,
            turn_index=reg.next_turn_index(sid),
            assembled_prompt=text,
            slash_source="user",
        )

    return reg.turn_sync(sid, resume_event_builder=build)


_EDIT = FileWritten(path="a.py", old_text="x = 1\n", new_text="x = 2\n", view="editor")


def test_between_turns_the_edit_is_appended_and_the_session_stays_parked(tmp_path: Path) -> None:
    reg = _registry(tmp_path, DeterministicResponder(seed=0))
    sid = _create(reg, tmp_path)
    with pytest.raises(api.RecordNotAtRestError):
        reg.append_event(sid, _EDIT)  # no record before the first turn

    _, root = _turn(reg, sid, "first")
    out = reg.append_event(sid, _EDIT)
    assert out["written"] == "at_rest"
    envs = list(api.read_record(root))
    assert envs[out["seq"]]["kind"] == "FileWritten"
    assert envs[out["seq"]]["payload"] == {
        "path": "a.py",
        "old_text": "x = 1\n",
        "new_text": "x = 2\n",
        "view": "editor",
    }
    assert _scan_record_status(root) == SessionStatus.PARKED

    m2, _ = _turn(reg, sid, "second")
    assert m2.status == SessionStatus.PARKED
    indexes = [
        e["payload"]["turn_index"] for e in api.read_record(root) if e["kind"] == "UserMessage"
    ]
    assert indexes == [0, 1]


def test_during_a_turn_the_edit_goes_through_the_live_run(tmp_path: Path) -> None:
    responder = _HoldsOnCue()
    reg = _registry(tmp_path, responder)
    sid = _create(reg, tmp_path)
    _turn(reg, sid, "first")

    done: dict[str, Any] = {}
    worker = threading.Thread(target=lambda: done.update(r=_turn(reg, sid, "HOLD second")))
    worker.start()
    try:
        assert responder.entered.wait(30), "the second turn's model step started"
        out = reg.append_event(sid, _EDIT)
    finally:
        responder.release.set()
        worker.join(60)
    assert out == {"written": "live", "seq": None}
    m2, root = done["r"]
    assert m2.status == SessionStatus.PARKED
    envs = list(api.read_record(root))
    kinds = [e["kind"] for e in envs]
    second = [i for i, e in enumerate(envs) if e["kind"] == "UserMessage"][1]
    edit = kinds.index("FileWritten")
    returned = [i for i, k in enumerate(kinds) if k == "Returned"][1]
    assert second < edit < returned, "the edit is inside the second turn"
    assert envs[edit]["producer"] is None
