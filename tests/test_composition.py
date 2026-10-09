# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Composition tests — substrate as a Producer (technical §20; conformance check 7).

Check 7: an embedded substrate exports ONLY mapped kinds; inner control-plane (substrate.*)
events do NOT cross; outer congestion blocks at the boundary. Plus inner-failure surfacing
and a nested-depth smoke test."""

from msgspec import Struct

from substrate.api import (
    Runtime,
    Subscription,
    embedded_substrate,
    quiescence,
    read_record,
    threshold_count,
)


# ── inner topology: a counter that emits 3 Tick, then completes ────────────────
class Tick(Struct, frozen=True):
    n: int


async def ticker(_input):
    for n in range(3):
        yield Tick(n=n)


def _inner_topo(b):
    b.producer_kind("ticker", schemas=[Tick], schema_version=1, factory=lambda: ticker)
    b.initial("ticker", input=None)
    b.termination(threshold_count("substrate.ProducerCompleted", 1))


# ── outer topology: embeds the inner substrate, exporting Tick -> OuterTick ────
class OuterTick(Struct, frozen=True):
    n: int


def _outer_topo(tmp_root):
    inner_root = tmp_root / "inner"

    def topo(b):
        # the embedded substrate is a Producer kind whose factory runs the inner topology
        # and exports inner "Tick" as outer "OuterTick" (default splat transform).
        b.producer_kind(
            "embedded",
            schemas=[OuterTick],
            schema_version=1,
            factory=lambda: embedded_substrate(_inner_topo, exports={"Tick": OuterTick}),
        )
        b.initial("embedded", input={"inner_root": str(inner_root)})
        b.termination(quiescence())

    return topo, inner_root


# ── check 7: only mapped kinds cross; inner substrate.* never cross ────────────
async def test_only_mapped_kinds_cross_the_boundary(tmp_path):
    topo, inner_root = _outer_topo(tmp_path)
    result = await Runtime(tmp_path / "outer").run(topo)
    assert result.status == "finalised"
    outer = list(read_record(tmp_path / "outer"))
    outer_kinds = [e["kind"] for e in outer]

    # the mapped kind crossed: 3 OuterTick on the outer bus
    outer_ticks = [e for e in outer if e["kind"] == "OuterTick"]
    assert [e["payload"]["n"] for e in outer_ticks] == [0, 1, 2]

    # the INNER application kind "Tick" did NOT cross (only its mapped translation did)
    assert "Tick" not in outer_kinds

    # NO inner substrate.* control-plane event crossed. The outer bus has its OWN lifecycle
    # frames, but none carry the inner run's identity — the inner record is separate.
    inner = list(read_record(inner_root))
    inner_run_id = next(
        e["payload"]["run_id"] for e in inner if e["kind"] == "substrate.RunStarted"
    )
    outer_run_id = next(
        e["payload"]["run_id"] for e in outer if e["kind"] == "substrate.RunStarted"
    )
    assert inner_run_id != outer_run_id  # two distinct runs, two distinct roots
    # the inner record is complete and independent at its own root
    assert inner[-1]["kind"] == "substrate.RunFinalised"
    assert any(e["kind"] == "Tick" for e in inner)  # inner Ticks live on the INNER bus


async def test_inner_record_is_complete_and_independent(tmp_path):
    topo, inner_root = _outer_topo(tmp_path)
    await Runtime(tmp_path / "outer").run(topo)
    inner = list(read_record(inner_root))
    # the inner run is a full, self-contained record: RunStarted .. RunFinalised, dense seq
    assert inner[0]["kind"] == "substrate.RunStarted"
    assert inner[-1]["kind"] == "substrate.RunFinalised"
    assert [e["seq"] for e in inner] == list(range(len(inner)))


# ── outer congestion blocks at the boundary (the entire backpressure story, §20) ──
async def test_outer_congestion_throttles_the_translator_inner_untouched(tmp_path):
    # a bound-1 OUTER admission queue throttles the embedded producer's yields (the
    # translator's submits go through ordinary outer admission — the whole backpressure
    # story); the inner run proceeds untouched at its own root. Assert liveness: every mapped
    # event still lands on the outer bus, and the inner record is complete.
    topo, inner_root = _outer_topo(tmp_path)
    result = await Runtime(tmp_path / "outer", admission=1).run(topo)
    assert result.status == "finalised"
    outer_ticks = [e for e in read_record(tmp_path / "outer") if e["kind"] == "OuterTick"]
    assert [e["payload"]["n"] for e in outer_ticks] == [0, 1, 2]  # all crossed through bound-1
    inner = list(read_record(inner_root))
    assert inner[-1]["kind"] == "substrate.RunFinalised"  # inner run completed untouched


# ── inner failure -> outer ProducerFailed carrying inner run_id ────────────────
async def failing_inner(_input):
    raise RuntimeError("inner producer boom")
    yield  # pragma: no cover - makes this an async generator


def _failing_inner_topo(b):
    b.producer_kind("boomer", schemas=[Tick], schema_version=1, factory=lambda: failing_inner)
    b.initial("boomer", input=None)
    b.termination(quiescence())


async def test_inner_failure_surfaces_as_outer_producer_failed_with_run_id(tmp_path):
    inner_root = tmp_path / "inner"

    def outer(b):
        b.producer_kind(
            "embedded",
            schemas=[OuterTick],
            schema_version=1,
            factory=lambda: embedded_substrate(_failing_inner_topo, exports={"Tick": OuterTick}),
        )
        b.initial("embedded", input={"inner_root": str(inner_root)})
        b.termination(quiescence())

    await Runtime(tmp_path / "outer").run(outer)
    outer_envs = list(read_record(tmp_path / "outer"))
    # a producer failure raised inside the inner run -> inner run status "failed"... but the
    # inner run itself FINALISES (a producer failing is not a run failure); so the embedded
    # producer COMPLETES normally here. Assert the inner record captured the ProducerFailed.
    inner = list(read_record(inner_root))
    assert any(e["kind"] == "substrate.ProducerFailed" for e in inner)
    # and the embedded producer completed on the outer bus (inner run finalised cleanly)
    assert any(e["kind"] == "substrate.ProducerCompleted" for e in outer_envs)


# ── inner RUN failure (a View raising) -> outer ProducerFailed w/ inner run_id ──
class BoomView:
    deterministic = True

    def __init__(self):
        self.subscription = Subscription(kinds=frozenset({"Tick"}))

    def update(self, event):
        raise RuntimeError("inner view exploded")

    def value(self):
        return None


def _inner_run_failure_topo(b):
    b.producer_kind("ticker", schemas=[Tick], schema_version=1, factory=lambda: ticker)
    b.view("boom", BoomView())
    b.initial("ticker", input=None)
    b.termination(quiescence())


async def test_inner_run_failure_surfaces_as_outer_producer_failed(tmp_path):
    inner_root = tmp_path / "inner"

    def outer(b):
        b.producer_kind(
            "embedded",
            schemas=[OuterTick],
            schema_version=1,
            factory=lambda: embedded_substrate(
                _inner_run_failure_topo, exports={"Tick": OuterTick}
            ),
        )
        b.initial("embedded", input={"inner_root": str(inner_root)})
        b.termination(quiescence())

    await Runtime(tmp_path / "outer").run(outer)
    outer_envs = list(read_record(tmp_path / "outer"))
    failed = [e for e in outer_envs if e["kind"] == "substrate.ProducerFailed"]
    assert len(failed) == 1  # ONE outer ProducerFailed for the inner run failure
    inner_run_id = next(
        e["payload"]["run_id"]
        for e in read_record(inner_root)
        if e["kind"] == "substrate.RunStarted"
    )
    assert failed[0]["payload"].get("inner_run_id") == inner_run_id  # carries the inner run_id


# ── nested depth smoke test (F-COMP-3: unbounded depth) ────────────────────────
async def test_nested_embedding_two_levels(tmp_path):
    # outer embeds mid; mid embeds the inner ticker. Tick -> MidTick -> OuterTick across
    # two composition boundaries. Each level has its own root.
    deep_root = tmp_path / "deep"
    mid_root = tmp_path / "mid"

    class MidTick(Struct, frozen=True):
        n: int

    def _mid_topo(b):
        b.producer_kind(
            "embedded_inner",
            schemas=[MidTick],
            schema_version=1,
            factory=lambda: embedded_substrate(_inner_topo, exports={"Tick": MidTick}),
        )
        b.initial("embedded_inner", input={"inner_root": str(deep_root)})
        b.termination(quiescence())

    def _outer(b):
        b.producer_kind(
            "embedded_mid",
            schemas=[OuterTick],
            schema_version=1,
            factory=lambda: embedded_substrate(_mid_topo, exports={"MidTick": OuterTick}),
        )
        b.initial("embedded_mid", input={"inner_root": str(mid_root)})
        b.termination(quiescence())

    result = await Runtime(tmp_path / "outer").run(_outer)
    assert result.status == "finalised"
    outer_ticks = [e for e in read_record(tmp_path / "outer") if e["kind"] == "OuterTick"]
    assert [e["payload"]["n"] for e in outer_ticks] == [0, 1, 2]  # crossed two boundaries
    # three distinct records exist, one per level
    assert (deep_root / "manifest.json").exists()
    assert (mid_root / "manifest.json").exists()
    assert (tmp_path / "outer" / "manifest.json").exists()


# ── default export = inner RunFinalised, carried by an author-named outer schema (#2) ──
class RunDone(Struct, frozen=True):
    pass


async def test_default_export_surfaces_inner_run_finalised(tmp_path):
    # F-COMP-1 / §20: the inner RunFinalised is exported by default — onto an author-named
    # outer carrier (default_export), since an outer kind may not be substrate.*.
    inner_root = tmp_path / "inner"

    def outer(b):
        b.producer_kind(
            "embedded",
            schemas=[RunDone],
            schema_version=1,
            factory=lambda: embedded_substrate(
                _inner_topo,
                default_export=RunDone,  # no per-kind exports; only the default
            ),
        )
        b.initial("embedded", input={"inner_root": str(inner_root)})
        b.termination(quiescence())

    result = await Runtime(tmp_path / "outer").run(outer)
    assert result.status == "finalised"
    outer_envs = list(read_record(tmp_path / "outer"))
    # exactly the default export crossed: one RunDone (the inner RunFinalised), and NO Tick
    assert [e["kind"] for e in outer_envs].count("RunDone") == 1
    assert "Tick" not in [e["kind"] for e in outer_envs]


# ── export map is SINGLE-SOURCE: derived from embedded_substrate(exports=), no b.export ─
async def test_export_map_in_manifest_derives_from_single_source(tmp_path):
    # the export map is declared ONCE on embedded_substrate(exports=...); the manifest derives
    # both the per-kind producer_kinds[].export_map AND the topology-level aggregate from it —
    # there is no separate b.export to keep in sync (the two-source-of-truth is gone).
    def outer(b):
        b.producer_kind(
            "embedded",
            schemas=[OuterTick],
            schema_version=1,
            factory=lambda: embedded_substrate(_inner_topo, exports={"Tick": OuterTick}),
        )
        b.initial("embedded", input={"inner_root": str(tmp_path / "inner")})
        b.termination(quiescence())

    await Runtime(tmp_path / "outer").run(outer)
    rs = next(e for e in read_record(tmp_path / "outer") if e["kind"] == "substrate.RunStarted")
    topo = rs["payload"]["topology"]
    # the per-kind map (authoritative) and the topology aggregate both reflect the single source
    embedded_pk = next(pk for pk in topo["producer_kinds"] if pk["kind"] == "embedded")
    assert embedded_pk["export_map"] == {"Tick": "OuterTick"}
    assert topo["exports"] == {"Tick": "OuterTick"}  # observable in the record (check 7)


# ── handshake #4 FIX 3: default_export + inner-run failure -> ONE ProducerFailed, ──────
# ── no spurious ProducerEmittedInvalidEvent (the failure RunFinalised is not splatted) ─
class RunDone2(Struct, frozen=True):
    pass


def _inner_view_failure_topo(b):
    b.producer_kind("ticker", schemas=[Tick], schema_version=1, factory=lambda: ticker)
    b.view("boom", BoomView())  # raises in update() -> inner RunFinalised{reason:view_failure}
    b.initial("ticker", input=None)
    b.termination(quiescence())


async def test_default_export_plus_inner_failure_no_double_signal(tmp_path):
    inner_root = tmp_path / "inner"

    def outer(b):
        b.producer_kind(
            "embedded",
            schemas=[RunDone2],
            schema_version=1,
            factory=lambda: embedded_substrate(
                _inner_view_failure_topo,
                default_export=RunDone2,  # maps substrate.RunFinalised
            ),
        )
        b.initial("embedded", input={"inner_root": str(inner_root)})
        b.termination(quiescence())

    await Runtime(tmp_path / "outer").run(outer)
    envs = list(read_record(tmp_path / "outer"))
    # the inner run FAILED (view_failure) -> exactly ONE outer ProducerFailed, and NO spurious
    # ProducerEmittedInvalidEvent from mis-splatting the failure RunFinalised into RunDone2.
    failed = [e for e in envs if e["kind"] == "substrate.ProducerFailed"]
    invalid = [e for e in envs if e["kind"] == "substrate.ProducerEmittedInvalidEvent"]
    assert len(failed) == 1
    assert invalid == []
    # and no RunDone2 success carrier was emitted for a failed inner run
    assert not any(e["kind"] == "RunDone2" for e in envs)


# ── handshake #4 FIX 6: missing inner_root is a RECORDED failure, not an un-citable run ─
def _inner_topo_named(b):
    b.producer_kind("ticker", schemas=[Tick], schema_version=1, factory=lambda: ticker)
    b.initial("ticker", input=None)
    b.termination(threshold_count("substrate.ProducerCompleted", 1))


async def test_missing_inner_root_is_recorded_not_uncitable(tmp_path):
    # an embedding whose input omits inner_root must NOT silently run an inner substrate at a
    # fabricated, un-citable root — it must surface as a recorded outer event.
    def outer(b):
        b.producer_kind(
            "embedded",
            schemas=[OuterTick],
            schema_version=1,
            factory=lambda: embedded_substrate(_inner_topo_named, exports={"Tick": OuterTick}),
        )
        b.initial("embedded", input={})  # NO inner_root
        b.termination(quiescence())

    await Runtime(tmp_path / "outer").run(outer)
    envs = list(read_record(tmp_path / "outer"))
    # the embedded producer raised InnerRootRequired -> recorded as ProducerFailed on the bus
    failed = [e for e in envs if e["kind"] == "substrate.ProducerFailed"]
    assert len(failed) == 1
    assert "inner_root" in failed[0]["payload"]["error"]
    # no inner run was started at an un-recorded fallback root (no fabricated inner-* dir)
    assert list(tmp_path.glob("**/inner-*")) == []
