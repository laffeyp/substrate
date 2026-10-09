# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 095: an oversized payload is a Claim Check on the record (technical §3.7), and every
reader that consumes payload contents redeems it the same way.

The record keeps the `{"$blob", "bytes"}` stub (byte-identical replay depends on it). A View sees
the full payload live AND after resume, when the View is rebuilt from the record (Fowler, Event
Sourcing: state rebuilt from the log must equal the live state). Before this sprint the resume fold
handed the View the stub, so a Trigger reading a field of it raised and was quarantined.
"""

from msgspec import Struct

from substrate.api import (
    PerEvent,
    PerKindLatest,
    Runtime,
    Subscription,
    any_of,
    pause_await_input,
    quiescence,
    read_record,
    resolve_blob_payload,
)

BLOB_LEN = 20 * 1024  # > 16 KiB BLOB_THRESHOLD_BYTES


class Big(Struct, frozen=True):
    blob: str


class LiveSaw(Struct, frozen=True):
    n: int


class ResumedSaw(Struct, frozen=True):
    n: int


class Go(Struct, frozen=True):
    ok: bool


async def emit_big(_input):
    yield Big(blob="x" * BLOB_LEN)


async def live_saw(inp):
    yield LiveSaw(n=inp["n"])


async def resumed_saw(inp):
    yield ResumedSaw(n=inp["n"])


def _blob_len(ctx) -> int:
    return len(ctx.views["big"].value()["blob"])  # KeyError on a stub


def topo(b):
    b.producer_kind("emit", schemas=[Big], schema_version=1, factory=lambda: emit_big)
    b.producer_kind("live", schemas=[LiveSaw], schema_version=1, factory=lambda: live_saw)
    b.producer_kind("resumed", schemas=[ResumedSaw], schema_version=1, factory=lambda: resumed_saw)
    b.view("big", PerKindLatest("Big"))
    b.initial("emit", input=None)
    b.trigger(
        "on-big-live",
        subscription=Subscription(kinds=frozenset({"Big"})),
        predicate=lambda ctx: _blob_len(ctx) == BLOB_LEN,
        starts="live",
        input_builder=lambda ctx: {"n": _blob_len(ctx)},
        policy=PerEvent(),
    )
    b.trigger(
        "on-go",
        subscription=Subscription(kinds=frozenset({"Go"})),
        predicate=lambda ctx: _blob_len(ctx) == BLOB_LEN,
        starts="resumed",
        input_builder=lambda ctx: {"n": _blob_len(ctx)},
        policy=PerEvent(),
    )
    b.termination(
        any_of(
            pause_await_input(
                lambda ctx: ctx.counts("LiveSaw") >= 1 and ctx.counts("Go") == 0,
                resume_condition="Go",
            ),
            quiescence(),
        )
    )


def _kinds(root):
    return [e["kind"] for e in read_record(root)]


async def test_view_sees_full_payload_live_and_after_resume(tmp_path):
    root = tmp_path / "run"
    paused = await Runtime(root, persistent=True).run(topo)
    assert paused.status == "paused"
    assert "LiveSaw" in _kinds(root), "live View must see the inline payload"

    resumed = await Runtime(root, persistent=True).resume(topo, resume_event=Go(ok=True))
    kinds = _kinds(root)
    assert "substrate.PredicateQuarantined" not in kinds, "resumed View held a blob stub"
    assert "substrate.InputBuildFailed" not in kinds
    saw = [e for e in read_record(root) if e["kind"] == "ResumedSaw"]
    assert len(saw) == 1 and saw[0]["payload"]["n"] == BLOB_LEN
    assert resumed.status == "finalised"


async def test_record_keeps_the_stub_and_resolve_redeems_it(tmp_path):
    root = tmp_path / "run"
    await Runtime(root, persistent=True).run(topo)
    raw = next(e for e in read_record(root) if e["kind"] == "Big")
    assert set(raw["payload"]) == {"$blob", "bytes"}, "record bytes unchanged: stub on disk"
    assert resolve_blob_payload(raw["payload"], root) == {"blob": "x" * BLOB_LEN}
    resolved = next(e for e in read_record(root, resolve_blobs=True) if e["kind"] == "Big")
    assert resolved["payload"] == {"blob": "x" * BLOB_LEN}
    # a non-stub payload passes through untouched
    assert resolve_blob_payload({"n": 1}, root) == {"n": 1}


async def test_follower_and_view_at_redeem_the_claim_check(tmp_path):
    from substrate.api import attach, view_at

    root = tmp_path / "run"
    await Runtime(root, persistent=True).run(topo)
    raw = attach(root).read_new()
    assert set(next(e for e in raw if e["kind"] == "Big")["payload"]) == {"$blob", "bytes"}
    live = attach(root, resolve_blobs=True).read_new()
    big = next(e for e in live if e["kind"] == "Big")
    assert big["payload"] == {"blob": "x" * BLOB_LEN}
    assert view_at(root, big["seq"], PerKindLatest("Big")) == {"blob": "x" * BLOB_LEN}
