# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Routes + same-cycle staging (kernel Decision #8) and the unsealable-input path."""

from msgspec import Struct

from substrate.api import (
    PerEvent,
    Runtime,
    Subscription,
    assert_event,
    quiescence,
    read_record,
)


class CountReached(Struct, frozen=True):
    n: int


class Echoed(Struct, frozen=True):
    echoed: int


async def counter(_input):
    for n in (1, 2, 3):
        yield CountReached(n=n)


async def echo(inp):
    yield Echoed(echoed=inp["last_n"])


def _route_topo(b):
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.producer_kind("echo", schemas=[Echoed], schema_version=1, factory=lambda: echo)
    b.initial("counter", input=None)
    b.route(
        "stash-n",
        subscription=Subscription(kinds=frozenset({"CountReached"})),
        slot="last_n",
        transform=lambda event: event.payload["n"],
    )
    b.trigger(
        "echo-it",
        subscription=Subscription(kinds=frozenset({"CountReached"})),
        predicate=lambda ctx: True,
        starts="echo",
        # reads the message the Route staged from the SAME event (step 4 before step 5)
        input_builder=lambda ctx: {"last_n": ctx.staged["last_n"]},
        policy=PerEvent(),
    )
    b.termination(quiescence())


async def test_route_staged_message_visible_same_cycle(tmp_path):
    # Decision #8: a Route's staged message is visible to a Trigger firing in the same
    # append cycle. Each echo sees the n staged by the route on the same CountReached.
    await Runtime(tmp_path / "r").run(_route_topo)
    envs = list(read_record(tmp_path / "r"))
    echoed = sorted(e["payload"]["echoed"] for e in envs if e["kind"] == "Echoed")
    assert echoed == [1, 2, 3]
    assert_event(tmp_path / "r", "substrate.InjectionApplied", target_input_slot="last_n")


def _unsealable_topo(b):
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.producer_kind("echo", schemas=[Echoed], schema_version=1, factory=lambda: echo)
    b.initial("counter", input=None)
    b.trigger(
        "bad-build",
        subscription=Subscription(kinds=frozenset({"CountReached"})),
        predicate=lambda ctx: True,
        starts="echo",
        input_builder=lambda ctx: object(),  # not sealable (§8.3)
        policy=PerEvent(),
    )
    b.termination(quiescence())


async def test_unsealable_input_becomes_input_build_failed(tmp_path):
    await Runtime(tmp_path / "r").run(_unsealable_topo)
    assert_event(tmp_path / "r", "substrate.InputBuildFailed", trigger_id="bad-build")
    started = [
        e
        for e in read_record(tmp_path / "r")
        if e["kind"] == "substrate.ProducerStarted" and e["payload"]["producer"]["kind"] == "echo"
    ]
    assert started == []  # no Producer starts when sealing fails
