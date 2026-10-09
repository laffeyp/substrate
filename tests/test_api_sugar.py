# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Authoring-API sugar (review #23 items 2-4, Architect-ratified): producer_kind(start=fn)
+ public ProducerFactory; b.instrument() builder helper; Responder on substrate.api.

These are additive, non-breaking ergonomics. The tests pin: the sugar RUNS (start= is
equivalent to factory=lambda: fn), the exactly-one-of validation, that instrument() wires
the producer_kind+trigger+(optional)route triple it claims to, and that the promoted types
are reachable on the public surface and behave structurally.
"""

import pathlib

from msgspec import Struct

from substrate import api
from substrate.api import (
    ProducerFactory,
    Responder,
    Runtime,
    TopologyBuilder,
    read_record,
)
from substrate.kernel.topology import RegistrationError


class Tick(Struct, frozen=True):
    n: int


class Mark(Struct, frozen=True):
    saw: int


async def _ticker(_inp):
    for n in (1, 2):
        yield Tick(n=n)


async def _marker(inp):
    yield Mark(saw=inp["n"])


# ── item 4: Responder on substrate.api ──────────────────────────────────────────────────────
def test_responder_is_on_api_and_is_structural() -> None:
    from substrate.reference import Responder as RefResponder

    # the public Responder IS the one the reference adapters now satisfy (single definition).
    assert Responder is RefResponder
    from substrate.reference import DeterministicResponder

    assert isinstance(DeterministicResponder(seed=1), Responder)  # runtime_checkable, by shape

    class MyModel:
        def respond(self, prompt: str) -> str:
            return prompt.upper()

    assert isinstance(MyModel(), Responder)  # a user model satisfies it by shape, no inheritance


# ── item 2: producer_kind(start=...) + ProducerFactory ──────────────────────────────────────
def test_producer_factory_alias_is_public() -> None:
    # the public alias exists so authors stop redeclaring `_Factory = Callable[[], Any]`.
    fac: ProducerFactory = lambda: _ticker  # noqa: E731 - exercising the alias as an annotation
    assert callable(fac) and fac() is _ticker


def test_start_sugar_runs_and_produces_the_events(tmp_path: pathlib.Path) -> None:
    import asyncio

    def topo(b: TopologyBuilder) -> None:
        b.producer_kind("ticker", schemas=[Tick], schema_version=1, start=_ticker)
        b.initial("ticker", input=None)
        b.termination(api.quiescence())

    root = tmp_path / "a"
    asyncio.run(Runtime(root).run(topo))
    ticks = [e["payload"]["n"] for e in read_record(root) if e["kind"] == "Tick"]
    assert ticks == [1, 2]


def test_start_sugar_records_the_real_producer_in_the_manifest(tmp_path: pathlib.Path) -> None:
    # start=fn is sugar for factory=lambda: fn, but BETTER provenance: the manifest names the
    # actual producer (_ticker), not the opaque wrapper or a bare <lambda>.
    import asyncio
    import json

    def topo(b: TopologyBuilder) -> None:
        b.producer_kind("ticker", schemas=[Tick], schema_version=1, start=_ticker)
        b.initial("ticker", input=None)
        b.termination(api.quiescence())

    root = tmp_path / "a"
    asyncio.run(Runtime(root).run(topo))
    manifest = next(e for e in read_record(root) if e["kind"] == "substrate.RunStarted")["payload"]
    blob = json.dumps(manifest, default=str)
    assert "_ticker" in blob and "_factory" not in blob


def test_producer_kind_rejects_both_start_and_factory() -> None:
    b = TopologyBuilder()
    try:
        b.producer_kind(
            "x", schemas=[Tick], schema_version=1, start=_ticker, factory=lambda: _ticker
        )
    except RegistrationError as e:
        assert "exactly one" in str(e)
    else:
        raise AssertionError("expected RegistrationError for both start= and factory=")


def test_producer_kind_rejects_neither_start_nor_factory() -> None:
    b = TopologyBuilder()
    try:
        b.producer_kind("x", schemas=[Tick], schema_version=1)
    except RegistrationError as e:
        assert "exactly one" in str(e)
    else:
        raise AssertionError("expected RegistrationError for neither start= nor factory=")


# ── item 3: b.instrument() ──────────────────────────────────────────────────────────────────
def _instrumented(into, **instr_kw):
    def topo(b: TopologyBuilder) -> None:
        b.producer_kind("ticker", schemas=[Tick], schema_version=1, start=_ticker)
        b.initial("ticker", input=None)
        b.instrument(
            "marker",
            on="Tick",
            schemas=[Mark],
            start=_marker,
            input_builder=lambda ctx: {"n": ctx.event.payload["n"]},
            into=into,
            **instr_kw,
        )
        b.termination(api.quiescence())

    return topo


def test_instrument_wires_producer_trigger_and_route(tmp_path: pathlib.Path) -> None:
    import asyncio

    root = tmp_path / "r"
    asyncio.run(Runtime(root).run(_instrumented(into="last", via=lambda e: e.payload["saw"])))
    kinds = [e["kind"] for e in read_record(root)]
    # producer_kind + trigger: the marker fired per Tick and emitted Mark...
    assert kinds.count("Mark") == 2
    assert any(
        e["kind"] == "substrate.TriggerFired" and e["payload"].get("factory") == "marker"
        for e in read_record(root)
    )
    # ...and the route staged each Mark (into="last" => an InjectionApplied per Mark).
    injections = [e for e in read_record(root) if e["kind"] == "substrate.InjectionApplied"]
    assert len(injections) == 2 and all(
        i["payload"]["target_input_slot"] == "last" for i in injections
    )


def test_instrument_observation_only_has_no_route(tmp_path: pathlib.Path) -> None:
    import asyncio

    root = tmp_path / "r"
    asyncio.run(Runtime(root).run(_instrumented(into=None)))  # no into= => observation-only
    assert any(e["kind"] == "Mark" for e in read_record(root))
    assert not any(e["kind"] == "substrate.InjectionApplied" for e in read_record(root))


async def _echo(_inp):
    yield Mark(saw=999)  # a DIFFERENT producer emitting the SAME kind the instrument emits


def test_instrument_stage_route_is_scoped_to_its_own_producer(tmp_path: pathlib.Path) -> None:
    # review #27 footgun: subscription matching is OR over kinds/producers, so a kind-scoped
    # stage route would also stage a different producer's same-kind event. The route is scoped
    # to the instrument's OWN producer — only what IT emits is staged.
    import asyncio

    def topo(b: TopologyBuilder) -> None:
        b.producer_kind("ticker", schemas=[Tick], schema_version=1, start=_ticker)
        b.initial("ticker", input=None)
        b.producer_kind("echo", schemas=[Mark], schema_version=1, start=_echo)
        b.initial("echo", input=None)  # also emits Mark — must NOT be staged by the instrument
        b.instrument(
            "marker",
            on="Tick",
            schemas=[Mark],
            start=_marker,
            input_builder=lambda ctx: {"n": ctx.event.payload["n"]},
            into="last",
            via=lambda e: e.payload["saw"],
        )
        b.termination(api.quiescence())

    root = tmp_path / "r"
    asyncio.run(Runtime(root).run(topo))
    marks = sum(1 for e in read_record(root) if e["kind"] == "Mark")
    injections = [e for e in read_record(root) if e["kind"] == "substrate.InjectionApplied"]
    assert marks == 3  # marker emits 2 (one per Tick) + echo emits 1
    assert len(injections) == 2  # ONLY the marker's 2 are staged — echo's Mark is not cross-staged
