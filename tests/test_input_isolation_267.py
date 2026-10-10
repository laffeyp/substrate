# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""K267: a Producer's input is its own copy of the recorded input.

Before: the kernel recorded and hashed the input's canonical form but handed the Producer
`seal(input)` (read-only MappingProxyType, tuples), a second form. Now the Producer gets a fresh
decode of the same canonical bytes the record holds: equal to the record by construction, and
private, so a Producer that changes it touches nothing else.
"""

from __future__ import annotations

from typing import Any

from msgspec import Struct

from substrate.api import PerEvent, Runtime, Subscription, quiescence, read_record

SEEN: dict[str, list[Any]] = {}


class Ok(Struct, frozen=True):
    n: int


class Order(Struct, frozen=True):
    item: str
    qty: int


def _recorder(name: str) -> Any:
    async def body(inp: Any) -> Any:
        SEEN.setdefault(name, []).append(inp)
        if isinstance(inp, dict):
            inp["mutated_by"] = name  # a Producer may change its own copy
            if isinstance(inp.get("items"), list):
                inp["items"].append("added")
        yield Ok(n=1)

    return lambda: body


def _two_producers_one_input(b: Any) -> None:
    shared = {"items": ["a", "b"], "nested": {"k": [1, 2.5]}}
    b.producer_kind("first", schemas=[Ok], schema_version=1, factory=_recorder("first"))
    b.producer_kind("second", schemas=[Ok], schema_version=1, factory=_recorder("second"))
    b.initial("first", input=shared)
    b.initial("second", input=shared)
    b.termination(quiescence())


async def test_each_producer_gets_a_private_plain_copy_equal_to_the_record(tmp_path: Any) -> None:
    SEEN.clear()
    await Runtime(tmp_path / "run").run(_two_producers_one_input)
    first, second = SEEN["first"][0], SEEN["second"][0]
    # plain types, as the record holds them
    assert (
        type(first) is dict and type(first["nested"]) is dict and type(first["nested"]["k"]) is list
    )
    # private: the first Producer's changes are not in the second's copy
    assert first is not second
    assert second.get("mutated_by") == "second"
    assert second["items"] == ["a", "b", "added"]
    assert first["items"] == ["a", "b", "added"] and first["mutated_by"] == "first"
    # equal to the record: what was recorded is the input before any Producer touched it
    recorded = [
        e["payload"]["resolved_input"]
        for e in read_record(tmp_path / "run")
        if e["kind"] == "substrate.TriggerFired"
    ]
    assert recorded == [{"items": ["a", "b"], "nested": {"k": [1, 2.5]}}] * 2


def _view_feeds_input(b: Any) -> None:
    from substrate.api import KindBuffer

    b.producer_kind("seed", schemas=[Ok], schema_version=1, factory=lambda: _emit_two)
    b.producer_kind("reader", schemas=[], schema_version=1, factory=_view_reader)
    b.view("oks", KindBuffer("Ok"))
    b.initial("seed", input=None)
    b.trigger(
        "t",
        subscription=Subscription(kinds=frozenset({"Ok"})),
        predicate=lambda ctx: True,
        starts="reader",
        input_builder=lambda ctx: {"oks": ctx.views["oks"].value()},
        policy=PerEvent(),
    )
    b.termination(quiescence())


async def _emit_two(_inp: Any) -> Any:
    yield Ok(n=1)
    yield Ok(n=2)


def _view_reader() -> Any:
    async def body(inp: Any) -> Any:
        SEEN.setdefault("reader", []).append([dict(o) for o in inp["oks"]])
        inp["oks"].clear()  # cannot reach the View
        return
        yield

    return body


async def test_a_producer_changing_its_input_cannot_change_a_view(tmp_path: Any) -> None:
    SEEN.clear()
    await Runtime(tmp_path / "run").run(_view_feeds_input)
    sizes = sorted(len(seen) for seen in SEEN["reader"])
    assert sizes == [1, 2], SEEN["reader"]  # the second firing still saw both Ok events


def _struct_input(b: Any) -> None:
    b.producer_kind("p", schemas=[Ok], schema_version=1, factory=_recorder("struct"))
    b.initial("p", input=Order(item="tea", qty=2))
    b.termination(quiescence())


async def test_a_frozen_struct_input_arrives_as_a_fresh_struct_of_its_type(tmp_path: Any) -> None:
    SEEN.clear()
    await Runtime(tmp_path / "run").run(_struct_input)
    got = SEEN["struct"][0]
    assert isinstance(got, Order) and got == Order(item="tea", qty=2)


def _bad(value: Any) -> Any:
    def topo(b: Any) -> None:
        b.producer_kind("p", schemas=[Ok], schema_version=1, factory=_recorder("bad"))
        b.initial("p", input={"v": value})
        b.termination(quiescence())

    return topo


async def test_values_with_no_canonical_form_never_start_a_producer(tmp_path: Any) -> None:
    for i, value in enumerate([b"raw", object(), 2**53 + 1, {1: "a"}]):
        root = tmp_path / f"run{i}"
        SEEN.clear()
        await Runtime(root).run(_bad(value))
        kinds = [e["kind"] for e in read_record(root)]
        assert "substrate.InputBuildFailed" in kinds, (value, kinds)
        assert "substrate.ProducerStarted" not in kinds, (value, kinds)
        assert "bad" not in SEEN
