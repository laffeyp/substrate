# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Liveness / termination regression tests (Priority-A safety net).

A self-feeding Trigger — a Producer emitting an event its OWN Trigger subscribes to —
is the kernel's named divergence hazard ("the substrate provides the tools to prevent
it [firing policies, keyed dedup, TerminationPolicy] but does not detect it", kernel §6).
That bug class manifests as a HANG, not a failed assertion, so it must be caught by a
hard timeout. Every test here carries an explicit timeout and asserts the run TERMINATES
with a finite, expected event count when properly bounded.

The suite-wide `timeout = 30` (pyproject) is the backstop; the per-test marks below are
tighter so a regression fails in a couple of seconds, never wedges the machine."""

import pytest
from msgspec import Struct

from substrate.api import (
    Once,
    PerEvent,
    PerKey,
    Runtime,
    Subscription,
    quiescence,
    read_record,
)
from substrate.kernel.triggers import Logical


class Tick(Struct, frozen=True):
    n: int


# ── bounded by Once: a self-feeding Trigger fires exactly once, run terminates ─
async def one_tick(_input):
    yield Tick(n=1)


def _self_feed_once_topo(b):
    # the spawned producer "echo" emits Tick — the SAME kind the trigger subscribes to.
    # Without a bound this loops forever; the Once policy bounds it to a single firing.
    b.producer_kind("seed", schemas=[Tick], schema_version=1, factory=lambda: one_tick)
    b.producer_kind("echo", schemas=[Tick], schema_version=1, factory=lambda: one_tick)
    b.initial("seed", input=None)
    b.trigger(
        "feedback",
        subscription=Subscription(kinds=frozenset({"Tick"})),
        predicate=lambda ctx: True,
        starts="echo",
        input_builder=lambda ctx: None,
        policy=Once(),
    )
    b.termination(quiescence())


@pytest.mark.timeout(10)
async def test_self_feeding_trigger_bounded_by_once_terminates(tmp_path):
    result = await Runtime(tmp_path / "run").run(_self_feed_once_topo)
    assert result.status == "finalised"
    fired = [
        e
        for e in read_record(tmp_path / "run")
        if e["kind"] == "substrate.TriggerFired" and e["payload"]["trigger_id"] == "feedback"
    ]
    assert len(fired) == 1  # Once: exactly one feedback firing, then quiescence


# ── bounded by a logical cooldown: self-feed throttled to a finite count ───────--
async def emit_n(inp):
    for n in range(inp["count"]):
        yield Tick(n=n)


def _self_feed_cooldown_topo(b):
    # seed emits 3 Ticks; each spawned echo emits 1 Tick (also matching). A large cooldown
    # caps the feedback to one firing in the window — proving the cooldown gate bounds the
    # self-feeding loop. (This is the _cooldown_two_topo self-feeding shape the supervisor
    # named, made bounded.)
    b.producer_kind("seed", schemas=[Tick], schema_version=1, factory=lambda: emit_n)
    b.producer_kind("echo", schemas=[Tick], schema_version=1, factory=lambda: one_tick)
    b.initial("seed", input={"count": 3})
    b.trigger(
        "feedback",
        subscription=Subscription(kinds=frozenset({"Tick"})),
        predicate=lambda ctx: True,
        starts="echo",
        input_builder=lambda ctx: None,
        policy=PerEvent(),
        cooldown=Logical(10_000),  # suppresses every refire within the window
    )
    b.termination(quiescence())


@pytest.mark.timeout(10)
async def test_self_feeding_trigger_bounded_by_cooldown_terminates(tmp_path):
    result = await Runtime(tmp_path / "run").run(_self_feed_cooldown_topo)
    assert result.status == "finalised"
    fired = [
        e
        for e in read_record(tmp_path / "run")
        if e["kind"] == "substrate.TriggerFired" and e["payload"]["trigger_id"] == "feedback"
    ]
    assert len(fired) == 1  # cooldown caps the self-feed to one firing


# ── bounded by PerKey dedup: each distinct key fires once, no runaway ──────────--
def _self_feed_perkey_topo(b):
    b.producer_kind("seed", schemas=[Tick], schema_version=1, factory=lambda: emit_n)
    b.producer_kind("echo", schemas=[Tick], schema_version=1, factory=lambda: one_tick)
    b.initial("seed", input={"count": 3})
    # key on the Tick value; echo always emits Tick(n=1), so its feedback dedupes against
    # the seed's Tick(n=1). Distinct keys: seed emits 0,1,2 -> 3 firings; echo's n=1 is a
    # duplicate of seed's n=1, so no extra firing. Bounded.
    b.trigger(
        "feedback",
        subscription=Subscription(kinds=frozenset({"Tick"})),
        predicate=lambda ctx: True,
        starts="echo",
        input_builder=lambda ctx: None,
        policy=PerKey(lambda event: event.payload["n"]),
    )
    b.termination(quiescence())


@pytest.mark.timeout(10)
async def test_self_feeding_trigger_bounded_by_perkey_terminates(tmp_path):
    result = await Runtime(tmp_path / "run").run(_self_feed_perkey_topo)
    assert result.status == "finalised"
    fired = [
        e
        for e in read_record(tmp_path / "run")
        if e["kind"] == "substrate.TriggerFired" and e["payload"]["trigger_id"] == "feedback"
    ]
    # distinct keys 0,1,2 from the seed; echo's n=1 dedupes -> exactly 3 firings, no runaway
    assert len(fired) == 3
