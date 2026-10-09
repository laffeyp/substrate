# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Kernel sprint 251: runtime liveness and one copy of each rule.

Each test is one lens-audit finding:
- F016: `cancel_producer` returns the instance's real parent, not None;
- F018: a relative and an absolute spelling of one record root find the same live runtime;
- F024: `Budget.event_counts` stops a Producer at its cap (it was stored and only warned about);
- F028: a factory that raises when built is refused at registration, not swallowed;
- F037: one subscription rule, on `Subscription.matches`;
- F022, F033: one copy of the run-outcome and run-failure strings.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from msgspec import Struct

from substrate import api
from substrate.kernel.runstate import RunPhase


class Start(Struct, frozen=True):
    n: int


class Tick(Struct, frozen=True):
    n: int


async def _head(_inp: object) -> AsyncIterator[Start]:
    yield Start(n=1)


async def _slow(_inp: object) -> AsyncIterator[Tick]:
    for i in range(1, 1000):
        await asyncio.sleep(0.2)
        yield Tick(n=i)


def _parent_child(b: api.TopologyBuilder) -> None:
    b.producer_kind("head", schemas=[Start], schema_version=1, factory=lambda: _head)
    b.producer_kind("slow", schemas=[Tick], schema_version=1, factory=lambda: _slow)
    b.initial("head", input=None)
    b.trigger(
        "start-slow",
        subscription=api.Subscription(kinds=frozenset({"Start"})),
        predicate=lambda ctx: True,
        starts="slow",
        input_builder=lambda ctx: {},
        policy=api.PerEvent(),
    )
    b.termination(api.quiescence())


async def _live(runtime: api.Runtime, kind: str) -> str:
    for _ in range(200):
        st = runtime._st  # noqa: SLF001 — test-only introspection of run state
        for inst, k in st.kind_by_instance.items():
            if k == kind:
                return inst
        await asyncio.sleep(0.01)
    raise AssertionError(f"no live {kind}")


async def test_cancel_producer_returns_the_real_parent(tmp_path: Path) -> None:
    runtime = api.Runtime(tmp_path / "rec")
    got: dict[str, Any] = {}

    async def _cancel() -> None:
        inst = await _live(runtime, "slow")
        got["ref"] = runtime.cancel_producer(inst, cause="external")

    await asyncio.gather(runtime.run(_parent_child), _cancel())
    started = [
        e["payload"]["producer"]
        for e in api.read_record(tmp_path / "rec")
        if e["kind"] == api.PRODUCER_STARTED
    ]
    head = next(p for p in started if p["kind"] == "head")
    assert got["ref"]["parent"] == head["instance"]


async def test_a_relative_root_finds_the_live_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    runtime = api.Runtime(Path("rec"))
    found: dict[str, Any] = {}

    async def _look() -> None:
        inst = await _live(runtime, "slow")
        found["abs"] = api.find_active_runtime(tmp_path / "rec")
        found["rel"] = api.find_active_runtime("rec")
        runtime.cancel_producer(inst)

    await asyncio.gather(runtime.run(_parent_child), _look())
    assert found["abs"] is runtime and found["rel"] is runtime


async def _three_ticks(_inp: object) -> AsyncIterator[Tick]:
    for i in range(3):
        yield Tick(n=i)


async def test_event_counts_stops_a_producer_at_its_cap(tmp_path: Path) -> None:
    budget = api.Budget(event_counts={"Tick": api.Cap(limit=2, reason="two ticks at most")})

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "ticker",
            schemas=[Tick],
            schema_version=1,
            factory=lambda: _three_ticks,
            deterministic=True,
            budget=budget,
        )
        b.initial("ticker", input=None)
        b.termination(api.quiescence())

    await api.Runtime(tmp_path / "rec").run(topo)
    envs = list(api.read_record(tmp_path / "rec"))
    assert [e["payload"]["n"] for e in envs if e["kind"] == "Tick"] == [0, 1]
    failed = [e["payload"] for e in envs if e["kind"] == api.PRODUCER_FAILED]
    assert len(failed) == 1
    assert failed[0]["budget_exceeded"] == {
        "axis": "event_counts",
        "kind": "Tick",
        "limit": 2,
        "reason": "two ticks at most",
    }


def test_a_factory_that_raises_is_refused_at_registration() -> None:
    def broken() -> Any:
        raise OSError("no socket at build time")

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind("bad", schemas=[Tick], schema_version=1, factory=broken)

    with pytest.raises(api.RegistrationError, match="no socket at build time"):
        topo(api.TopologyBuilder())


def test_one_subscription_rule() -> None:
    ref = api.ProducerRef(kind="writer", instance="i-1", parent=None)
    event = api.Event(seq=0, kind="Note", schema="Note@1", producer=ref, t=0.0, payload={})
    assert api.Subscription(kinds=frozenset({"Note"})).matches(event)
    assert api.Subscription(producers=frozenset({"writer"})).matches(event)
    assert api.Subscription(producers=frozenset({"i-1"})).matches(event)
    assert not api.Subscription(kinds=frozenset({"Other"})).matches(event)
    bare = api.Event(seq=1, kind="Note", schema="Note@1", producer=None, t=0.0, payload={})
    assert not api.Subscription(producers=frozenset({"writer"})).matches(bare)
    env = {
        "seq": 0,
        "kind": "Note",
        "schema": "Note@1",
        "t": 0.0,
        "payload": {},
        "producer": {"kind": "writer", "instance": "i-1", "parent": None},
    }
    assert api.Event.from_envelope(env) == event


def test_one_copy_of_the_outcome_strings() -> None:
    for phase, status in (
        (RunPhase.PAUSED, api.RunStatus.PAUSED),
        (RunPhase.FINALISED, api.RunStatus.FINALISED),
        (RunPhase.FAILED, api.RunStatus.FAILED),
    ):
        assert phase.value == status.value
    assert {r.value for r in api.RunFailureReason} == {
        "view_failure",
        "kernel_error",
        "stuck_quiescent",
    }


def test_quiescence_takes_no_timer() -> None:
    policy = api.quiescence()
    assert policy.name == "quiescence"
    assert not hasattr(policy, "watchdog_seconds")
