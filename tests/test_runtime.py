# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""End-to-end runtime tests against the design-spec event-sequence oracle (§3.2, §3.3).

These are the anti-drift proof: a topology runs, and the persisted record's event
sequence is asserted exactly (single-producer) or by event/count (concurrent)."""

from msgspec import Struct

from substrate.api import (
    PerEvent,
    Runtime,
    Subscription,
    assert_event,
    assert_no_event,
    assert_sequence,
    quiescence,
    read_record,
    threshold_count,
)


class CountReached(Struct, frozen=True):
    n: int


class Doubled(Struct, frozen=True):
    original: int
    doubled: int


async def counter(_input):
    for n in range(1, 4):
        yield CountReached(n=n)


async def doubler(inp):
    yield Doubled(original=inp["n"], doubled=inp["n"] * 2)


def _count_to_three(b):
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.initial("counter", input=None)
    b.termination(threshold_count("substrate.ProducerCompleted", 1))


async def test_count_to_three_exact_sequence(tmp_path):
    # design spec §3.2 — the canonical oracle.
    result = await Runtime(tmp_path / "run").run(_count_to_three)
    assert result.status == "finalised"
    assert_sequence(
        tmp_path / "run",
        [
            "substrate.RunStarted",
            "substrate.TriggerFired",
            "substrate.ProducerStarted",
            "CountReached",
            "CountReached",
            "CountReached",
            "substrate.ProducerCompleted",
            "substrate.TerminationMatched",
            "substrate.RunFinalised",
        ],
    )
    # seq density: 0..8, dense, no gaps
    seqs = [e["seq"] for e in read_record(tmp_path / "run")]
    assert seqs == list(range(9))
    # the spawned Producer is identified in the lifecycle payload (P-SUBJECT-ID)
    started = assert_event(tmp_path / "run", "substrate.ProducerStarted")
    assert started["payload"]["producer"]["kind"] == "counter"


def _doubler_topo(b):
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.producer_kind("doubler", schemas=[Doubled], schema_version=1, factory=lambda: doubler)
    b.initial("counter", input=None)
    b.trigger(
        "double-each",
        subscription=Subscription(kinds=frozenset({"CountReached"})),
        predicate=lambda ctx: True,
        starts="doubler",
        input_builder=lambda ctx: {"n": ctx.event.payload["n"]},
        policy=PerEvent(),
    )
    b.termination(quiescence())


async def test_trigger_fires_a_producer_per_event(tmp_path):
    # design spec §3.3 — a Trigger spawns a doubler per CountReached. Concurrent, so
    # assert by event/count rather than exact order.
    result = await Runtime(tmp_path / "run").run(_doubler_topo)
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    doubled = [e for e in envs if e["kind"] == "Doubled"]
    assert sorted(d["payload"]["doubled"] for d in doubled) == [2, 4, 6]
    assert_event(tmp_path / "run", "Doubled", original=3, doubled=6)
    # provenance: every doubler ProducerStarted has the counter as parent
    starts = [e for e in envs if e["kind"] == "substrate.ProducerStarted"]
    doubler_starts = [e for e in starts if e["payload"]["producer"]["kind"] == "doubler"]
    assert len(doubler_starts) == 3
    assert all(e["payload"]["producer"]["parent"] is not None for e in doubler_starts)


class Undeclared(Struct, frozen=True):
    x: int


async def emits_undeclared(_input):
    yield Undeclared(x=1)  # the producer only declared CountReached


def _invalid_topo(b):
    b.producer_kind("p", schemas=[CountReached], schema_version=1, factory=lambda: emits_undeclared)
    b.initial("p", input=None)
    b.termination(quiescence())


async def test_invalid_emission_becomes_logged_event(tmp_path):
    # conformance check 4 core: an undeclared kind becomes a sequenced
    # substrate.ProducerEmittedInvalidEvent with raw payload preserved.
    await Runtime(tmp_path / "run").run(_invalid_topo)
    inv = assert_event(
        tmp_path / "run", "substrate.ProducerEmittedInvalidEvent", reason="unknown_kind"
    )
    assert inv["payload"]["raw_payload"] == {"x": 1}
    assert_no_event(tmp_path / "run", "Undeclared")


async def test_backpressure_liveness_with_bound_one(tmp_path):
    # conformance check 3 core: emissions through a bound-1 admission queue all land.
    result = await Runtime(tmp_path / "run", admission=1).run(_count_to_three)
    assert result.status == "finalised"
    counted = [e for e in read_record(tmp_path / "run") if e["kind"] == "CountReached"]
    assert [e["payload"]["n"] for e in counted] == [1, 2, 3]
