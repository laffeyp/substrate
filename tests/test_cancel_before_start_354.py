# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K354: a producer cancelled before it starts is recorded, and its run goes on.

The runtime counts a producer in flight when it creates its task, and the count falls only when
the producer's end frame is recorded. A task cancelled before its first step never runs its body,
so it wrote neither `ProducerStarted` nor `ProducerCancelled`: the count stayed up and the run
never ended. An Esc during a session turn's bootstrap does this — the cancel waits in the loop's
queue behind the bootstrap and runs before the new model task's first step (research
`RESEARCH-2026-11-18-core-stalls.md`). These tests put the cancel at that point: right after the
run creates the task, before the task runs.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from msgspec import Struct

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.constants import PRODUCER_CANCELLED, PRODUCER_STARTED, RUN_FINALISED
from substrate.kernel.runtime import Runtime
from substrate.topologies.session import UserMessage, session_topology
from substrate.topologies.session_registry import SessionManifest, SessionRegistry


class Tick(Struct, frozen=True):
    n: int


async def _ticks(_inp: object) -> AsyncIterator[Tick]:
    yield Tick(n=1)


@pytest.fixture
def cancel_on_creation(monkeypatch: pytest.MonkeyPatch) -> Iterator[set[str]]:
    """Cancel every new task of the kinds put in the returned set the moment the run creates it,
    as a cancel queued during a bootstrap does."""
    kinds: set[str] = set()
    flush = Runtime._flush_scheduled

    def flush_then_cancel(self: Runtime) -> None:
        before = set(self._st.task_by_instance)
        flush(self)
        for inst in set(self._st.task_by_instance) - before:
            if self._st.kind_by_instance.get(inst) in kinds:
                self.cancel_producer(inst, cause="external", caller="test:bootstrap-esc")

    monkeypatch.setattr(Runtime, "_flush_scheduled", flush_then_cancel)
    yield kinds


def test_a_run_whose_producer_is_cancelled_before_it_starts_ends(
    tmp_path: Path, cancel_on_creation: set[str]
) -> None:
    cancel_on_creation.add("tick")

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind("tick", schemas=[Tick], schema_version=1, factory=lambda: _ticks)
        b.initial("tick", input=None)
        b.termination(api.quiescence())

    result = asyncio.run(asyncio.wait_for(Runtime(tmp_path / "rec").run(topo), timeout=10))
    assert result.status == "finalised"
    events = list(api.read_record(tmp_path / "rec"))
    kinds = [e["kind"] for e in events]
    assert "Tick" not in kinds  # the body never ran
    (started,) = [e for e in events if e["kind"] == PRODUCER_STARTED]
    (cancelled,) = [e for e in events if e["kind"] == PRODUCER_CANCELLED]
    assert started["seq"] < cancelled["seq"]
    assert cancelled["payload"]["producer"] == started["payload"]["producer"]
    assert cancelled["payload"]["cause"] == "external"
    assert cancelled["payload"]["caller"] == "test:bootstrap-esc"
    assert kinds[-1] == RUN_FINALISED


def test_a_producer_that_ran_records_what_it_did_before(tmp_path: Path) -> None:
    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind("tick", schemas=[Tick], schema_version=1, factory=lambda: _ticks)
        b.initial("tick", input=None)
        b.termination(api.quiescence())

    asyncio.run(Runtime(tmp_path / "rec").run(topo))
    kinds = [e["kind"] for e in api.read_record(tmp_path / "rec")]
    assert kinds.count(PRODUCER_STARTED) == 1 and "Tick" in kinds
    assert PRODUCER_CANCELLED not in kinds


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

    return SessionRegistry(base=tmp_path / "sessions", session_topology_factory=factory)


def test_a_turn_interrupted_during_its_bootstrap_ends_interrupted(
    tmp_path: Path, cancel_on_creation: set[str]
) -> None:
    reg = _registry(tmp_path)
    sid = "s_00000000000000c1"
    manifest = reg.create(
        session_id=sid,
        name=None,
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="SEED",
        make_repository=False,
    )

    def build(_m: SessionManifest, _root: Path, text: str = "first") -> UserMessage:
        return UserMessage(
            text=text,
            turn_index=reg.next_turn_index(sid),
            assembled_prompt=text,
            slash_source="user",
        )

    reg.turn_sync(sid, resume_event_builder=build)  # the first turn, uninterrupted
    cancel_on_creation.add("model")
    final, _root = reg.turn_sync(
        sid, resume_event_builder=lambda m, r: build(m, r, "second"), timeout_seconds=30
    )
    events = list(api.read_record(manifest.record_root))
    tail = [e["kind"] for e in events[-6:]]
    assert tail == [
        PRODUCER_STARTED,
        PRODUCER_CANCELLED,
        "substrate.TriggerFired",
        PRODUCER_STARTED,
        "Returned",
        "substrate.TerminationMatched",
    ]
    assert events[-2]["payload"]["reason"] == "interrupted"
    assert final.status == "parked"
    # The session takes its next turn: nothing was left holding it.
    cancel_on_creation.clear()
    reg.turn_sync(sid, resume_event_builder=lambda m, r: build(m, r, "third"), timeout_seconds=30)
    replies = [e for e in api.read_record(manifest.record_root) if e["kind"] == "ModelReply"]
    assert replies[-1]["payload"]["turn_index"] == 2
