# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K356: `turn_sync` can bound its wait for the session's lock.

The quit's sweep ends every session through `turn_sync`, which waited for the session's lock with
no limit: one turn that never returned held the sweep, and Electron killed the backend at 45 s
(review 2026-11-18, § 3.2). With `lock_timeout_seconds` the wait ends with `SessionBusy`.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from substrate.adapters import DeterministicResponder
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session_registry import SessionBusy, SessionManifest, SessionRegistry

SID = "s_00000000000000e3"


def _registry(tmp_path: Path) -> SessionRegistry:
    def factory(manifest: SessionManifest, first_turn_user_message: Any = None) -> Any:
        return session_topology(
            driver=DeterministicResponder(seed=0),
            driver_name="deterministic",
            driver_context_tokens=100_000,
            seed="SEED",
            tools={},
            per_turn="",
            max_turns=200,
            turn_max_steps=4,
            session_id=manifest.session_id,
            workspace_path=manifest.workspace,
            script=None,
            first_turn_user_message=first_turn_user_message,
        )

    reg = SessionRegistry(base=tmp_path / "sessions", session_topology_factory=factory)
    reg.create(
        session_id=SID,
        name=None,
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="SEED",
        make_repository=False,
    )
    return reg


def _build(reg: SessionRegistry) -> Any:
    def build(_m: SessionManifest, _root: Path) -> UserMessage:
        return UserMessage(
            text="hello",
            turn_index=reg.next_turn_index(SID),
            assembled_prompt="hello",
            slash_source="user",
        )

    return build


@pytest.mark.timeout(10)
def test_a_held_lock_ends_the_wait_with_session_busy(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    lock = reg._turn_threading_locks.setdefault(SID, threading.Lock())
    lock.acquire()  # a turn that never returns holds it
    try:
        t0 = time.monotonic()
        with pytest.raises(SessionBusy):
            reg.turn_sync(SID, resume_event_builder=_build(reg), lock_timeout_seconds=0.5)
        assert 0.4 <= time.monotonic() - t0 < 3.0
    finally:
        lock.release()


def test_a_free_lock_runs_the_turn_and_is_released(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.turn_sync(SID, resume_event_builder=_build(reg), lock_timeout_seconds=0.5)
    reg.turn_sync(SID, resume_event_builder=_build(reg), lock_timeout_seconds=0.5)
    assert reg.next_turn_index(SID) == 2
    assert not reg._turn_threading_locks[SID].locked()
