# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K355: an interrupt the turn cannot take yet is kept, and says so.

`SessionRegistry.interrupt` answered None, "no turn in flight", while a turn was in flight: when
the turn's loop was busy (a bootstrap reading the record, 9.4 s on a 4 MB record) its one-second
wait ran out, and when the turn's worker had not yet made its loop the cancel was dropped. It now
answers `PENDING_INTERRUPT` and the cancel runs once the loop is free, ending the turn `Returned`
`interrupted` (K354).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

import substrate.topologies.session_registry as registry_mod
from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.kernel.runtime import Runtime
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session_registry import (
    PENDING_INTERRUPT,
    SessionManifest,
    SessionRegistry,
)

SID = "s_00000000000000d1"


def _session(tmp_path: Path) -> tuple[SessionRegistry, SessionManifest]:
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
    manifest = reg.create(
        session_id=SID,
        name=None,
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="SEED",
        make_repository=False,
    )
    reg.turn_sync(SID, resume_event_builder=_message(reg, "first"))
    return reg, manifest


def _message(reg: SessionRegistry, text: str) -> Any:
    def build(_m: SessionManifest, _root: Path) -> UserMessage:
        return UserMessage(
            text=text,
            turn_index=reg.next_turn_index(SID),
            assembled_prompt=text,
            slash_source="user",
        )

    return build


def _ended_interrupted(manifest: SessionManifest) -> bool:
    events = list(api.read_record(manifest.record_root))
    return [e["kind"] for e in events[-2:]] == ["Returned", "substrate.TerminationMatched"] and (
        events[-2]["payload"]["reason"] == "interrupted"
    )


def test_an_interrupt_while_the_loop_is_busy_is_pending_and_lands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reg, manifest = _session(tmp_path)
    bootstrap = Runtime._resume_bootstrap

    def slow_bootstrap(self: Runtime, reg_: Any, resume_event: Any) -> None:
        time.sleep(2.0)  # the loop thread is busy, as reading a large record keeps it
        bootstrap(self, reg_, resume_event)

    monkeypatch.setattr(Runtime, "_resume_bootstrap", slow_bootstrap)
    answers: list[Any] = []

    def esc() -> None:
        for _ in range(300):
            handle = reg._running_handles.get(SID)
            if handle is not None and handle.loop is not None:
                break
            time.sleep(0.01)
        time.sleep(0.3)
        answers.append(reg.interrupt(SID))

    t = threading.Thread(target=esc)
    t.start()
    reg.turn_sync(SID, resume_event_builder=_message(reg, "second"), timeout_seconds=30)
    t.join()
    assert answers == [PENDING_INTERRUPT]
    assert _ended_interrupted(manifest)


def test_an_interrupt_before_the_loop_exists_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reg, manifest = _session(tmp_path)
    answers: list[Any] = []
    run = registry_mod._run_resume_sync

    def interrupt_first(*args: Any, **kwargs: Any) -> Any:
        # The handle is registered and its loop not yet made: the moment the cancel was dropped.
        answers.append(reg.interrupt(SID))
        return run(*args, **kwargs)

    monkeypatch.setattr(registry_mod, "_run_resume_sync", interrupt_first)
    reg.turn_sync(SID, resume_event_builder=_message(reg, "second"), timeout_seconds=30)
    assert answers == [PENDING_INTERRUPT]
    assert _ended_interrupted(manifest)


def test_an_idle_session_still_has_nothing_to_interrupt(tmp_path: Path) -> None:
    reg, _manifest = _session(tmp_path)
    assert reg.interrupt(SID) is None
